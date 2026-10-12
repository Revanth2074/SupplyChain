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
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

logger = logging.getLogger("synapt_connector")

_NETSKOPE_BUNDLE = os.path.expanduser(r"~\certs\combined-ca-bundle.pem")


class SynaptError(RuntimeError):
    """Any Synapt failure (auth, transport, tool error). Synapt is required, so callers surface it."""


def get_ssl_verify() -> Any:
    """Return path to Netskope CA bundle if present, otherwise default system CA verification."""
    # Check if SSL verification should be skipped
    if os.getenv("SKIP_SSL_VERIFY", "").lower() in ("true", "1", "yes"):
        return False
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


class SynaptMCPConnector:
    """Manages authentication and MCP protocol communication with Synapt."""

    def __init__(self, config: Optional[SynaptConfig] = None):
        self.config = config or SynaptConfig()
        self.access_token: Optional[str] = None
        self.token_expiry: float = 0
        self.verify = get_ssl_verify()
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
        if not self._mcp_initialized:
            self.initialize_mcp()
        result = self.send_mcp_request("tools/list", {})
        self._remote_tools = result.get("tools", [])
        return self._remote_tools

    def _expected_props(self, tool_name: str) -> set:
        for t in self.list_remote_tools():
            if t["name"] == tool_name:
                return set(t.get("inputSchema", {}).get("properties", {}).keys())
        return set()

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a Trident tool on the live Synapt MCP server. Returns the tool's text content
        (JSON text for Trident tools). Raises SynaptError when Synapt is not configured or fails."""
        if not self.config.is_configured():
            raise SynaptError("SYNAPT_USERNAME and/or SYNAPT_PASSWORD are not configured in backend/.env.")

        # Inject configured environment parameters only where the live tool schema expects them
        arguments = dict(arguments)
        expected_props = self._expected_props(tool_name)
        if "provider_id" in expected_props and "provider_id" not in arguments and self.config.provider_id:
            arguments["provider_id"] = self.config.provider_id
        if "top_k" in expected_props and "top_k" not in arguments and self.config.top_k:
            arguments["top_k"] = self.config.top_k
        if "graph_hops" in expected_props and "graph_hops" not in arguments and self.config.graph_hops:
            arguments["graph_hops"] = self.config.graph_hops
        if "question" in expected_props and "question" not in arguments and "query" in arguments:
            arguments["question"] = arguments.pop("query")

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
