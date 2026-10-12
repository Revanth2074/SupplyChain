from agents.supervisor import MAX_ROUTES, decide

CASES = [{"disruption_id": f"DIS-00000{i}", "similarity": 0.8} for i in range(5)]
BASE = {"payload": {"use_graph": True, "judge": True}, "incident": {"disruption_type": "Cyber Attack"}}


def _ready(**over):
    """State with every agent done and a passing report."""
    s = {**BASE, "search": {"results": CASES}, "synapt_round": 1, "graph": {"answer": "ok"}, "cases": CASES,
         "retrieval_round": 1, "impact": {}, "plan": {}, "recovery": {}, "summary": "brief",
         "fact_check": {"passed": True}, "verdict": {"verdict": "approve", "overall_score": 0.9}}
    s.update(over)
    return s


def test_classifies_first():
    nxt, _, _ = decide({"payload": {}})
    assert nxt == ["classifier"]


def test_investigates_in_parallel():
    nxt, _, _ = decide(BASE)
    assert nxt == ["hybrid_retriever", "synapt_worker"]


def test_fuses_evidence_after_investigation():
    nxt, _, _ = decide({**BASE, "search": {}, "synapt_round": 1, "graph": {"answer": "x"}})
    assert nxt == ["evidence_fusion"]


def test_broadens_weak_evidence_once_then_moves_on():
    weak = [{"disruption_id": "DIS-000001", "similarity": 0.3}]
    s = {**BASE, "search": {}, "synapt_round": 1, "graph": {"answer": "x"}, "cases": weak, "retrieval_round": 1}
    nxt, reason, upd = decide(s)
    assert nxt == ["hybrid_retriever"] and upd["retrieval_plan"] == {"broaden": True} and upd["cases"] is None
    assert "weak" in reason
    nxt, _, _ = decide({**s, "retrieval_round": 2})
    assert nxt == ["impact_analyzer"]


def test_reasks_synapt_when_graph_has_no_answer():
    s = {**BASE, "search": {}, "synapt_round": 1, "graph": {"answer": ""}, "cases": CASES, "retrieval_round": 1}
    nxt, _, upd = decide(s)
    assert nxt == ["synapt_worker"] and upd == {"cases": None}
    nxt, _, _ = decide({**s, "synapt_round": 2})
    assert nxt == ["impact_analyzer"]


def test_no_graph_retry_when_graph_rag_is_off():
    s = {**BASE, "payload": {"use_graph": False, "judge": True}, "search": {}, "synapt_round": 1, "graph": None,
         "cases": CASES, "retrieval_round": 1}
    assert decide(s)[0] == ["impact_analyzer"]


def test_rewrites_briefing_when_fact_check_fails():
    s = _ready(fact_check={"passed": False, "final": ["amount $1 does not match"]}, report_round=1, verdict=None)
    nxt, _, upd = decide(s)
    assert nxt == ["synthesis"] and upd == {"summary": None}
    assert decide({**s, "report_round": 2})[0] == ["judge"]


def test_revision_round_when_judge_says_revise():
    s = _ready(verdict={"verdict": "revise", "overall_score": 0.5})
    nxt, _, upd = decide(s)
    assert nxt == ["hybrid_retriever"] and upd["revision"] == 1 and upd["plan"] is None and upd["verdict"] is None
    assert decide({**s, "revision": 1})[0] == []


def test_finishes_when_approved_or_judge_off():
    assert decide(_ready())[0] == []
    assert decide(_ready(payload={"use_graph": True, "judge": False}, verdict=None))[0] == []


def test_routing_limit_stops_the_loop():
    nxt, reason, _ = decide({**BASE, "routes": MAX_ROUTES})
    assert nxt == [] and "limit" in reason


def test_strict_rewrite_drops_only_flagged_sentences():
    from agents.synthesis import strict_rewrite
    md = "**Impact** — Loss is $5.0M. Plant restarts in 10 days.\n\n**Plan** — Use an alternative supplier."
    out = strict_rewrite(md, lambda t: ["bad amount"] if "$5.0M" in t else [])
    assert "$5.0M" not in out and "Plant restarts in 10 days." in out and "**Plan**" in out
