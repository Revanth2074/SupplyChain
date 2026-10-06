"""Lightweight Synapt MCP client (Streamable HTTP, JSON-RPC 2.0).

Handles: token auth (email/password -> bearer), MCP session init, tools/list,
tools/call, SSE or JSON responses, automatic re-auth on 401.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import httpx

from .config import settings

log = logging.getLogger("synapt")


class SynaptError(RuntimeError):
    pass


class SynaptMCPClient:
    def __init__(self) -> None:
        self.url = settings.SYNAPT_MCP_URL
        self._token: str | None = None
        self._token_ts: float = 0
        self._session_id: str | None = None
        self._req_id = 0
        self._tools: list[dict] | None = None
        self._http = httpx.Client(timeout=120, follow_redirects=True)
        self._lock = threading.RLock()

    # ---------------- auth ----------------
    def _authenticate(self) -> str:
        if not settings.SYNAPT_USERNAME or not settings.SYNAPT_PASSWORD:
            raise SynaptError("Synapt credentials not configured")
        base = settings.SYNAPT_AUTH_BASE
        creds = {"email": settings.SYNAPT_USERNAME, "password": settings.SYNAPT_PASSWORD}
        attempts = [
            ("json", creds),
            ("json", {"username": settings.SYNAPT_USERNAME, "password": settings.SYNAPT_PASSWORD}),
            ("form", {"username": settings.SYNAPT_USERNAME, "password": settings.SYNAPT_PASSWORD}),
        ]
        last = ""
        for kind, body in attempts:
            try:
                r = (self._http.post(base, json=body) if kind == "json"
                     else self._http.post(base, data=body))
            except httpx.HTTPError as e:
                last = str(e)
                continue
            if r.status_code < 300:
                data = r.json()
                tok = (data.get("access_token") or data.get("token")
                       or (data.get("data") or {}).get("access_token")
                       or (data.get("data") or {}).get("token"))
                if tok:
                    self._token, self._token_ts = tok, time.time()
                    self._session_id = None
                    return tok
                last = f"no token field in response: {list(data)}"
            else:
                last = f"{r.status_code} {r.text[:200]}"
        raise SynaptError(f"Synapt auth failed: {last}")

    def _headers(self) -> dict:
        if not self._token or time.time() - self._token_ts > 50 * 60:
            self._authenticate()
        h = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h

    # ---------------- transport ----------------
    @staticmethod
    def _parse(resp: httpx.Response) -> dict:
        ctype = resp.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            result = None
            for line in resp.text.splitlines():
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload:
                        try:
                            msg = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        if "result" in msg or "error" in msg:
                            result = msg
            return result or {}
        if not resp.text.strip():
            return {}
        return resp.json()

    def _rpc(self, method: str, params: dict | None = None, notify: bool = False, _retry=True) -> Any:
        body: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        if not notify:
            self._req_id += 1
            body["id"] = self._req_id
        r = self._http.post(self.url, headers=self._headers(), json=body)
        if r.status_code in (401, 403) and _retry:
            self._token = None
            self._session_id = None
            if method != "initialize":
                self._initialize()
            return self._rpc(method, params, notify, _retry=False)
        if r.status_code == 404 and self._session_id and _retry:
            self._session_id = None
            self._initialize()
            return self._rpc(method, params, notify, _retry=False)
        if r.status_code >= 400:
            raise SynaptError(f"MCP {method} -> {r.status_code}: {r.text[:300]}")
        sid = r.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid
        if notify:
            return None
        msg = self._parse(r)
        if "error" in msg:
            raise SynaptError(f"MCP {method} error: {msg['error']}")
        return msg.get("result")

    def _initialize(self) -> None:
        self._rpc("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "supplychain-assistant", "version": "1.0"},
        })
        try:
            self._rpc("notifications/initialized", notify=True)
        except SynaptError:
            pass

    def _ensure(self) -> None:
        if not self._session_id:
            with self._lock:
                if not self._session_id:
                    self._initialize()

    # ---------------- public ----------------
    def list_tools(self, refresh: bool = False) -> list[dict]:
        if self._tools is None or refresh:
            self._ensure()
            self._tools = (self._rpc("tools/list", {}) or {}).get("tools", [])
        return self._tools

    def call_tool(self, name: str, arguments: dict) -> Any:
        self._ensure()
        res = self._rpc("tools/call", {"name": name, "arguments": arguments}) or {}
        if res.get("isError"):
            raise SynaptError(f"tool {name} error: {res.get('content')}")
        if "structuredContent" in res and res["structuredContent"]:
            return res["structuredContent"]
        texts = [c.get("text", "") for c in res.get("content", []) if c.get("type") == "text"]
        joined = "\n".join(texts)
        try:
            return json.loads(joined)
        except (json.JSONDecodeError, TypeError):
            return joined


_client: SynaptMCPClient | None = None


def get_client() -> SynaptMCPClient:
    global _client
    if _client is None:
        _client = SynaptMCPClient()
    return _client
