"""Supervisor scheduling (goals x dependencies x requests) and the agents' own decision loops.
No Synapt or ML calls: tools are replaced with fakes."""
import pytest

from agents import judge as judge_mod
from agents import retrieval as retrieval_mod
from agents.supervisor import MAX_REVISIONS, MAX_ROUTES, decide

CASES = [{"disruption_id": f"DIS-00000{i}", "similarity": 0.8} for i in range(5)]
BASE = {"payload": {"use_graph": True, "judge": True}, "incident": {"disruption_type": "Cyber Attack"}}


def _ready(**over):
    """State with every goal met and a passing report."""
    s = {**BASE, "search": {"results": CASES}, "synapt_round": 1, "graph": {"answer": "ok"}, "cases": CASES,
         "impact": {}, "plan": {}, "recovery": {}, "summary": "brief",
         "fact_check": {"passed": True}, "verdict": {"verdict": "approve", "overall_score": 0.9}}
    s.update(over)
    return s


# ---------------------------------------------------------------- supervisor
def test_classifies_first():
    assert decide({"payload": {}})[0] == ["classifier"]


def test_starts_every_ready_goal_in_parallel():
    nxt, reason, _ = decide(BASE)
    assert nxt == ["hybrid_retriever", "synapt_worker", "impact_analyzer"] and "parallel" in reason


def test_waits_for_dependencies():
    # evidence fusion needs both investigation branches; the planner needs cases and impact
    s = {**BASE, "search": {}, "impact": {}}
    assert decide(s)[0] == ["synapt_worker"]
    s = {**s, "synapt_round": 1}
    assert decide(s)[0] == ["evidence_fusion"]
    assert decide({**s, "cases": CASES})[0] == ["planner"]


def test_finishes_when_all_goals_met_or_judge_off():
    assert decide(_ready())[0] == []
    assert decide(_ready(payload={"use_graph": True, "judge": False}, verdict=None))[0] == []


def test_acts_on_judge_request_and_reopens_dependent_goals():
    req = {"to": "planner", "reset": ["plan", "recovery", "summary", "verdict"], "params": {"plan_hint": {"exclude": ["X"]}},
           "criterion": "consistency", "reason": "consistency scored 2/5"}
    s = _ready(verdict={"verdict": "revise", "overall_score": 0.5},
               messages=[{"agent": "judge", "requests": [req]}])
    nxt, reason, upd = decide(s)
    assert nxt == ["planner"] and "consistency" in reason
    assert upd["plan"] is None and upd["summary"] is None and upd["plan_hint"] == {"exclude": ["X"]}
    assert upd["revision"] == 1 and upd["msg_cursor"] == 1
    # after the planner, the reset goals re-open in dependency order
    after = {**s, **upd, "plan": {}, "messages": s["messages"]}
    assert decide(after)[0] == ["recovery"]


def test_revision_budget_is_respected():
    req = {"to": "planner", "reset": ["plan"], "params": {}, "reason": "x"}
    s = _ready(verdict={"verdict": "revise", "overall_score": 0.5}, revision=MAX_REVISIONS,
               messages=[{"agent": "judge", "requests": [req]}])
    nxt, reason, _ = decide(s)
    assert nxt == [] and "revision budget" in reason


def test_fact_check_backstop_then_moves_on():
    s = _ready(fact_check={"passed": False, "final": ["amount $1 does not match"]}, report_round=1, verdict=None)
    nxt, _, upd = decide(s)
    assert nxt == ["synthesis"] and upd["summary"] is None and upd["report_mode"] == "strict"
    assert decide({**s, "report_round": 2})[0] == ["judge"]


def test_routing_limit_stops_the_loop():
    nxt, reason, _ = decide({**BASE, "routes": MAX_ROUTES})
    assert nxt == [] and "limit" in reason


# ---------------------------------------------------------------- agents decide for themselves
def _case(i, sim):
    return {"disruption_id": f"DIS-{i:06d}", "similarity": sim}


def test_retrieval_agent_widens_its_own_search_until_evidence_is_good(monkeypatch):
    calls = []

    def fake_search(query, filters, top_k, mode, reference):
        calls.append((query, filters, top_k))
        sims = [0.3] if len(calls) == 1 else [0.8, 0.75, 0.7]
        return {"results": [_case(i, s) for i, s in enumerate(sims)], "semantic_source": "synapt"}

    monkeypatch.setattr(retrieval_mod, "hybrid_search", fake_search)
    state = {"payload": {"top_k": 8, "filters": {"industry": ["Electronics"]}}, "incident": {"disruption_type": "Cyber Attack", "industry": "Electronics"},
             "query": "ransomware"}
    out = retrieval_mod.CaseRetrievalAgent()(state)
    assert len(calls) == 2 and calls[1][1] is None and calls[1][2] == 12  # second try: broadened, no filters, more candidates
    assert out["search"]["strategy"] == "broadened" and out["search"]["evidence_ok"]
    msg = out["messages"][0]
    assert msg["status"] == "done" and len(msg["steps"]) == 2 and "weak" in msg["steps"][1]["thought"]


def test_retrieval_agent_keeps_best_evidence_when_goal_cannot_be_met(monkeypatch):
    sims = iter([[0.5, 0.5], [0.2], [0.4]])
    monkeypatch.setattr(retrieval_mod, "hybrid_search",
                        lambda **kw: {"results": [_case(i, s) for i, s in enumerate(next(sims))], "semantic_source": "synapt"})
    out = retrieval_mod.CaseRetrievalAgent()({"payload": {}, "incident": {"disruption_type": "Cyber Attack"}, "query": "x"})
    assert out["search"]["strategy"] == "focused" and out["messages"][0]["status"] == "partial"
    assert out["search"]["attempts"] == ["focused", "broadened", "type-only"]


def test_judge_sends_weakest_criterion_to_the_responsible_agent(monkeypatch):
    scores = {"groundedness": 4, "relevance": 4, "actionability": 4, "completeness": 4, "consistency": 2, "safety": 5}
    monkeypatch.setattr(judge_mod, "audit", lambda *a: {"scores": dict(scores), "verdict": "revise", "method": "rules",
                                                        "issues": [], "strengths": [], "summary": ""})
    state = {"payload": {"judge": True}, "plan": {"primary_strategy": "Customer Delay"}, "summary": "brief",
             "incident": {}, "cases": [], "fact_check": {"passed": True}}
    out = judge_mod.JudgeAgent()(state)
    req = out["messages"][0]["requests"][0]
    assert req["to"] == "planner" and req["criterion"] == "consistency"
    assert req["params"] == {"plan_hint": {"exclude": ["Customer Delay"]}}


@pytest.mark.parametrize("weak,agent", [("groundedness", "synthesis"), ("relevance", "hybrid_retriever"),
                                         ("actionability", "planner"), ("completeness", "recovery")])
def test_judge_remedies_map_to_agents(weak, agent):
    assert judge_mod.REMEDY[weak][0] == agent


def test_strict_rewrite_drops_only_flagged_sentences():
    from agents.synthesis import strict_rewrite
    md = "**Impact** — Loss is $5.0M. Plant restarts in 10 days.\n\n**Plan** — Use an alternative supplier."
    out = strict_rewrite(md, lambda t: ["bad amount"] if "$5.0M" in t else [])
    assert "$5.0M" not in out and "Plant restarts in 10 days." in out and "**Plan**" in out
