"""Synapt AI MCP Connector.

Handles authentication with the Synapt Auth Service, manages JWT bearer tokens,
and interfaces with the Synapt Tristore / Trident MCP endpoint (JSON-RPC / MCP protocol,
Streamable HTTP) to discover and execute the Trident tools.
"""

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import httpx
from dotenv import load_dotenv

logger = logging.getLogger("synapt_connector")

_NETSKOPE_BUNDLE = os.path.expanduser(r"~\certs\combined-ca-bundle.pem")


class SynaptError(RuntimeError):
    """Any Synapt failure (auth, transport, tool error, simulated outage). Callers fall back to local engines."""


def get_ssl_verify() -> Any:
    """Return path to Netskope CA bundle if present, otherwise default system CA verification."""
    if os.path.exists(_NETSKOPE_BUNDLE):
        return _NETSKOPE_BUNDLE
    return True


class SynaptConfig:
    """Configuration loaded from backend/.env."""

    def __init__(self, env_path: Optional[str] = None):
        if env_path:
            load_dotenv(env_path)
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            env_in_current = os.path.join(current_dir, ".env")
            env_in_parent = os.path.join(os.path.dirname(current_dir), ".env")
            if os.path.exists(env_in_current):
                load_dotenv(env_in_current)
            elif os.path.exists(env_in_parent):
                load_dotenv(env_in_parent)
            else:
                load_dotenv()

        self.mcp_url = os.getenv("SYNAPT_MCP_URL", "https://beta.synapt.ai/tristore/mcp/")
        self.auth_base = os.getenv("SYNAPT_AUTH_BASE", "https://beta.synapt.ai/auth_service/api/v1/auth/token")
        self.username = os.getenv("SYNAPT_USERNAME", "")
        self.password = os.getenv("SYNAPT_PASSWORD", "")
        self.provider_id = os.getenv("SYNAPT_PROVIDER_ID", "")

        try:
            self.top_k = int(os.getenv("SYNAPT_TOP_K", "5"))
        except ValueError:
            self.top_k = 5

        try:
            self.graph_hops = int(os.getenv("SYNAPT_GRAPH_HOPS", "2"))
        except ValueError:
            self.graph_hops = 2

    def is_configured(self) -> bool:
        """Returns True if minimum authentication credentials are present."""
        return bool(self.username and self.password)


# Trident MCP tool definitions, matching the live server's input schemas (tools/list).
# Used when the remote tool list cannot be fetched; the live schema always takes precedence.
_PID = {"provider_id": {"type": "string", "description": "Scoped provider ID (defaults to SYNAPT_PROVIDER_ID)"}}

TRIDENT_TOOLS_DEFINITIONS = [
    {
        "name": "trident_get_schema",
        "description": "Get the graph schema: node types, edge types, counts and sample property names. Call this FIRST.",
        "parameters": {"type": "object", "properties": {**_PID}, "required": ["provider_id"]},
    },
    {
        "name": "trident_get_stats",
        "description": ("Quick overview of a provider's graph: counts of nodes, chunks, entities, concepts, propositions, "
                        "procedures, counts_by_label, provider_kind and has_ticket_store."),
        "parameters": {"type": "object", "properties": {**_PID}, "required": ["provider_id"]},
    },
    {
        "name": "trident_search",
        "description": "Semantic search across graph nodes (entities, concepts, procedures, steps). Returns node_id for get_node/traverse.",
        "parameters": {"type": "object", "properties": {
            **_PID, "query": {"type": "string"}, "node_type": {"type": "string"}, "top_k": {"type": "integer"}},
            "required": ["provider_id", "query"]},
    },
    {
        "name": "trident_find_exact",
        "description": "Find a node by its exact label or name (case-insensitive).",
        "parameters": {"type": "object", "properties": {
            **_PID, "name": {"type": "string"}, "node_type": {"type": "string"}}, "required": ["provider_id", "name"]},
    },
    {
        "name": "trident_cypher",
        "description": ("Run a read-only Cypher query against Neo4j. The query MUST include {provider_id: $provider_id}. "
                        "This app only sends fixed, provider-pinned templates (the tool is not tenant-scoped server-side)."),
        "parameters": {"type": "object", "properties": {**_PID, "query": {"type": "string"}},
                       "required": ["provider_id", "query"]},
    },
    {
        "name": "trident_get_node",
        "description": "Get a node's properties and meaningful connections.",
        "parameters": {"type": "object", "properties": {
            **_PID, "node_id": {"type": "string"}, "include_chunks": {"type": "boolean"}, "depth": {"type": "integer"}},
            "required": ["provider_id", "node_id"]},
    },
    {
        "name": "trident_traverse",
        "description": "Walk the graph from a node following edge types and filtering node types.",
        "parameters": {"type": "object", "properties": {
            **_PID, "node_id": {"type": "string"}, "edge_types": {"type": "array", "items": {"type": "string"}},
            "node_types": {"type": "array", "items": {"type": "string"}}, "direction": {"type": "string"},
            "depth": {"type": "integer"}}, "required": ["provider_id", "node_id"]},
    },
    {
        "name": "trident_get_chunks",
        "description": "Semantic search over raw document text. Returns the actual content from ingested documents.",
        "parameters": {"type": "object", "properties": {
            **_PID, "query": {"type": "string"}, "top_k": {"type": "integer"}}, "required": ["provider_id", "query"]},
    },
    {
        "name": "trident_get_procedures",
        "description": "Structured procedures (SOPs) with ordered steps, optionally filtered by a query.",
        "parameters": {"type": "object", "properties": {**_PID, "query": {"type": "string"}}, "required": ["provider_id"]},
    },
    {
        "name": "trident_query",
        "description": ("Retrieval-augmented query against a provider's knowledge base: grounded answer, confidence, source "
                        "chunks, procedures, reasoning subgraph and quality signals."),
        "parameters": {"type": "object", "properties": {
            **_PID, "question": {"type": "string"}, "top_k": {"type": "integer"}, "graph_hops": {"type": "integer"},
            "user_id": {"type": "string"}, "task_id": {"type": "string"}, "ticket_mode": {"type": "string"},
            "tickets": {"type": "array"}, "label_fields": {"type": "array"}}, "required": ["provider_id", "question"]},
    },
    {
        "name": "trident_label_ticket",
        "description": "Predict label values for a ticket from similar already-labelled tickets (ticket store providers).",
        "parameters": {"type": "object", "properties": {
            **_PID, "ticket": {"type": "string", "description": "Ticket as a JSON string"},
            "fields": {"type": "string", "description": "Comma-separated label fields"}},
            "required": ["provider_id", "ticket"]},
    },
    {
        "name": "trident_episodes",
        "description": "Episodic memory: mined incident patterns and past episodes for a provider.",
        "parameters": {"type": "object", "properties": {
            **_PID, "query": {"type": "string"}, "episode_id": {"type": "string"}, "top_k": {"type": "integer"},
            "include_events": {"type": "boolean"}}, "required": ["provider_id"]},
    },
    {
        "name": "trident_create_entity",
        "description": "Create a new entity in the knowledge graph.",
        "parameters": {"type": "object", "properties": {
            **_PID, "label": {"type": "string"}, "entity_type": {"type": "string"}, "description": {"type": "string"}},
            "required": ["provider_id", "label", "entity_type"]},
    },
    {
        "name": "trident_create_concept",
        "description": "Create a new concept (definition/term) in the knowledge graph.",
        "parameters": {"type": "object", "properties": {
            **_PID, "name": {"type": "string"}, "definition": {"type": "string"}, "aliases": {"type": "array"}},
            "required": ["provider_id", "name", "definition"]},
    },
    {
        "name": "trident_create_relationship",
        "description": "Create a relationship (edge) between two existing entities or concepts.",
        "parameters": {"type": "object", "properties": {
            **_PID, "source_label": {"type": "string"}, "edge_type": {"type": "string"},
            "target_label": {"type": "string"}, "description": {"type": "string"}, "confidence": {"type": "number"}},
            "required": ["provider_id", "source_label", "edge_type", "target_label"]},
    },
    {
        "name": "trident_feedback",
        "description": "Record a verdict on a trident_query answer (feedback_id = the query_id it returned).",
        "parameters": {"type": "object", "properties": {
            "feedback_id": {"type": "string"}, "caller_type": {"type": "string"}, "verdict": {"type": "string"},
            "post_action": {"type": "string"}, "score": {"type": "number"}, "reason": {"type": "string"}},
            "required": ["feedback_id", "caller_type", "verdict"]},
    },
    {
        "name": "trident_ingest",
        "description": ("Ingest external content into a provider's knowledge base. Connector types: 'content', 'url', "
                        "'scraper', 'rest_api', 'database', 'jira'. Extraction mode: comprehensive | balanced | precise."),
        "parameters": {"type": "object", "properties": {
            **_PID, "connector_type": {"type": "string"}, "content": {"type": "string"}, "filename": {"type": "string"},
            "document_type": {"type": "string"}, "extraction_mode": {"type": "string"}, "url": {"type": "string"},
            "has_ttl": {"type": "boolean"}, "ttl_days": {"type": "integer"}},
            "required": ["provider_id", "connector_type"]},
    },
]


class SynaptMCPConnector:
    """Manages authentication and MCP protocol communication with Synapt."""

    def __init__(self, config: Optional[SynaptConfig] = None):
        self.config = config or SynaptConfig()
        self.access_token: Optional[str] = None
        self.token_expiry: float = 0
        self.verify = get_ssl_verify()
        self._custom_tools: Dict[str, Dict[str, Any]] = {}
        self._mcp_initialized: bool = False
        self._request_id: int = 1
        self._session_id: Optional[str] = None     # Mcp-Session-Id issued by the server on initialize
        self._remote_tools: Optional[List[Dict[str, Any]]] = None  # tools/list, fetched once
        self._lock = threading.RLock()
        self._http = httpx.Client(verify=self.verify, timeout=120.0, follow_redirects=True)

    def authenticate(self, force: bool = False) -> str:
        """Authenticate with Synapt Auth Service and retrieve Bearer token."""
        if not force and self.access_token and time.time() < self.token_expiry:
            return self.access_token

        if not self.config.is_configured():
            raise SynaptError(
                "SYNAPT_USERNAME and/or SYNAPT_PASSWORD are not configured in your .env file.\n"
                "Please add your credentials to backend/.env to connect to Synapt."
            )

        username = self.config.username
        password = self.config.password

        # 1. Try JSON payload (FastAPI / OAuth2 standard with email/username)
        json_payload = {"email": username, "username": username, "password": password}
        resp = self._http.post(self.config.auth_base, json=json_payload, timeout=20.0)

        # 2. If 400 or 422, try form-encoded data
        if resp.status_code in (400, 422):
            form_payload = {"username": username, "password": password, "grant_type": "password"}
            resp = self._http.post(self.config.auth_base, data=form_payload, timeout=20.0)

        if resp.status_code != 200:
            raise SynaptError(f"Synapt authentication failed (HTTP {resp.status_code}): {resp.text[:300]}")

        data = resp.json()
        token = (data.get("access_token") or data.get("token")
                 or (data.get("data") or {}).get("access_token") or (data.get("data") or {}).get("token"))
        if not token:
            raise SynaptError(f"Unexpected token response structure from Synapt: {list(data)}")

        self.access_token = token
        expires_in = data.get("expires_in", 3600)
        self.token_expiry = time.time() + float(expires_in) - 60
        return self.access_token

    def _next_id(self) -> int:
        with self._lock:
            self._request_id += 1
            return self._request_id

    def _headers(self, token: str) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def send_mcp_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send a standard JSON-RPC 2.0 MCP request to the Synapt MCP endpoint."""
        token = self.authenticate()
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": self._next_id(), "method": method}
        if params is not None:
            payload["params"] = params

        resp = self._http.post(self.config.mcp_url, headers=self._headers(token), json=payload)
        if resp.status_code == 401:
            token = self.authenticate(force=True)
            resp = self._http.post(self.config.mcp_url, headers=self._headers(token), json=payload)
        if resp.status_code == 404 and self._session_id and method != "initialize":
            # session expired on the server: handshake again, then retry once
            self._session_id, self._mcp_initialized = None, False
            self.initialize_mcp()
            resp = self._http.post(self.config.mcp_url, headers=self._headers(token), json=payload)

        if resp.status_code != 200:
            raise SynaptError(f"Synapt MCP request error (HTTP {resp.status_code}): {resp.text[:300]}")

        sid = resp.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid

        data = None
        for line in resp.text.splitlines():
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:].strip())
                    break
                except Exception:
                    pass
        if data is None:
            data = resp.json() if resp.text.strip() else {}

        if "error" in data:
            raise SynaptError(f"Synapt MCP JSON-RPC Error: {data['error']}")

        return data.get("result", {}) or {}

    def initialize_mcp(self) -> Dict[str, Any]:
        """Perform MCP handshake (initialize + notifications/initialized)."""
        with self._lock:
            if self._mcp_initialized:
                return {}

            init_params = {
                "protocolVersion": "2025-03-26",
                "capabilities": {"roots": {"listChanged": True}, "sampling": {}},
                "clientInfo": {"name": "supplychain-disruption-assistant", "version": "1.0.0"},
            }
            result = self.send_mcp_request("initialize", init_params)
            self._mcp_initialized = True

            try:
                token = self.authenticate()
                self._http.post(self.config.mcp_url, headers=self._headers(token), timeout=5.0,
                                json={"jsonrpc": "2.0", "method": "notifications/initialized"})
            except Exception as e:  # noqa: BLE001
                logger.debug(f"notifications/initialized note: {e}")

            return result

    def list_remote_tools(self, refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch the tools exposed by the Synapt MCP server (cached after the first call)."""
        if self._remote_tools is not None and not refresh:
            return self._remote_tools
        try:
            if not self._mcp_initialized:
                self.initialize_mcp()
            result = self.send_mcp_request("tools/list", {})
            self._remote_tools = result.get("tools", [])
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not fetch remote MCP tools (falling back to Trident definitions): {e}")
            return []
        return self._remote_tools

    def register_custom_tool(
        self,
        name: str,
        handler: Callable[..., Any],
        description: str,
        parameters: Dict[str, Any]
    ) -> None:
        """Allow registering local or user-defined tools to be callable by the agent."""
        self._custom_tools[name] = {"handler": handler, "description": description, "parameters": parameters}

    def get_all_tools_for_llm(self) -> List[Dict[str, Any]]:
        """Convert the Trident tools + custom tools to OpenAI function format."""
        openai_tools: List[Dict[str, Any]] = []

        # 1. If configured and connected, fetch dynamically from remote server
        remote_tools = self.list_remote_tools() if self.config.is_configured() else []

        if remote_tools:
            for tool in remote_tools:
                schema = tool.get("inputSchema", {"type": "object", "properties": {}})
                openai_tools.append({"type": "function", "function": {
                    "name": tool["name"],
                    "description": tool.get("description", f"Synapt platform tool: {tool['name']}"),
                    "parameters": schema}})
        else:
            for tool_def in TRIDENT_TOOLS_DEFINITIONS:
                openai_tools.append({"type": "function", "function": {
                    "name": tool_def["name"], "description": tool_def["description"],
                    "parameters": tool_def["parameters"]}})

        # 2. Registered custom tools
        for name, tool_info in self._custom_tools.items():
            openai_tools.append({"type": "function", "function": {
                "name": name, "description": tool_info["description"], "parameters": tool_info["parameters"]}})

        return openai_tools

    def _expected_props(self, tool_name: str) -> set:
        for t in self.list_remote_tools():
            if t["name"] == tool_name:
                return set(t.get("inputSchema", {}).get("properties", {}).keys())
        for td in TRIDENT_TOOLS_DEFINITIONS:
            if td["name"] == tool_name:
                return set(td["parameters"]["properties"].keys())
        return set()

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool either on the remote Synapt MCP server, custom handler, or simulated mock.
        Returns the tool's text content (JSON text for Trident tools)."""
        # 1. Custom tool handlers
        if tool_name in self._custom_tools:
            handler = self._custom_tools[tool_name]["handler"]
            return handler(**arguments)

        # Fallback Lab: a switched-off dependency fails here, exactly like a real outage
        # (only inside the app; standalone scripts such as test_connection.py have no switches)
        try:
            from services import faults
        except ImportError:
            faults = None
        if faults is not None:
            try:
                faults.check_synapt(tool_name)
            except faults.SimulatedOutage as e:
                raise SynaptError(str(e)) from e

        # 2. Automatically inject configured environment parameters only if expected by schema
        arguments = dict(arguments)
        expected_props = self._expected_props(tool_name) if self.config.is_configured() else set()
        if "provider_id" in expected_props and "provider_id" not in arguments and self.config.provider_id:
            arguments["provider_id"] = self.config.provider_id
        if "top_k" in expected_props and "top_k" not in arguments and self.config.top_k:
            arguments["top_k"] = self.config.top_k
        if "graph_hops" in expected_props and "graph_hops" not in arguments and self.config.graph_hops:
            arguments["graph_hops"] = self.config.graph_hops
        if "question" in expected_props and "question" not in arguments and "query" in arguments:
            arguments["question"] = arguments.pop("query")

        # 3. If credentials are not yet entered, provide informative mock responses
        if not self.config.is_configured():
            return self._simulate_trident_tool(tool_name, arguments)

        # 4. Live execution on remote Synapt MCP server
        if not self._mcp_initialized:
            self.initialize_mcp()

        result = self.send_mcp_request("tools/call", {"name": tool_name, "arguments": arguments})
        content = result.get("content", [])
        if result.get("isError"):
            texts = [c.get("text", "") for c in content if isinstance(c, dict)]
            raise SynaptError(f"tool {tool_name} error: {' '.join(texts)[:300]}")
        if isinstance(content, list):
            texts = [c.get("text", "") for c in content if isinstance(c, dict) and "text" in c]
            if texts:
                return "\n".join(texts)
        return json.dumps(result.get("structuredContent") or result, indent=2)

    def _simulate_trident_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Provides simulated tool feedback when live credentials have not yet been provided.
        (The app's agents never use this: they check is_configured() and fall back to local engines.)"""
        prov = self.config.provider_id or "<provider_id>"
        note = "Simulated output. Enter SYNAPT_USERNAME and SYNAPT_PASSWORD in backend/.env for live data."
        if tool_name == "trident_get_schema":
            return json.dumps({
                "provider_id": prov,
                "node_types": ["Entity", "Concept", "Procedure", "Step", "Proposition", "Document", "Chunk"],
                "edge_types": ["RELATED_TO", "PART_OF", "DEPENDS_ON", "USES", "HAS_STEP", "REFERENCES"],
                "note": note}, indent=2)

        if tool_name == "trident_get_stats":
            return json.dumps({"provider_id": prov, "node_count": 0, "chunk_count": 0, "procedure_count": 0,
                               "has_ticket_store": False, "note": note}, indent=2)

        if tool_name in ("trident_search", "trident_find_exact", "trident_query", "trident_cypher", "trident_get_chunks"):
            q = arguments.get("query") or arguments.get("question") or arguments.get("name") or "query"
            return (
                f"[Trident Tool '{tool_name}' result for: '{q}']\n"
                f"- Provider: {prov}\n"
                f"- Status: Ready to query live Synapt MCP server once credentials are entered.\n"
                f"- Input parameters received: {json.dumps(arguments)}"
            )

        return (
            f"[Trident Tool '{tool_name}' executed]\n"
            f"Parameters: {json.dumps(arguments)}\n"
            "Live server execution will run automatically when SYNAPT_USERNAME and SYNAPT_PASSWORD are set in backend/.env."
        )
