#!/usr/bin/env python3
"""
Test connection and authentication to the Synapt AI MCP endpoint.
Steps: authenticate -> MCP handshake -> list tools -> provider stats -> semantic retrieval check
(including whether Synapt's PII masking has replaced region names with [LOCATION_x] tokens).

Run from backend/:  python synapt/test_connection.py
"""
import json
import os
import sys

# Ensure this directory is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synapt_connector import SynaptConfig, SynaptMCPConnector  # noqa: E402


def main():
    print("[*] Testing Synapt MCP Connection...")
    config = SynaptConfig()
    print(f"[*] MCP URL: {config.mcp_url}")
    print(f"[*] Auth Base: {config.auth_base}")
    print(f"[*] Username: {config.username}")
    print(f"[*] Provider ID: {config.provider_id}")

    connector = SynaptMCPConnector(config)

    # 1. Test Auth
    print("\n[-] Step 1: Authenticating with Synapt Auth Service...")
    try:
        token = connector.authenticate()
        print(f"[OK] Authentication Successful! Token retrieved (Length: {len(token)} chars)")
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] Authentication Failed: {e}")
        return

    # 2. Test MCP Handshake
    print("\n[-] Step 2: Initializing MCP Protocol...")
    try:
        init_res = connector.initialize_mcp()
        server = (init_res or {}).get("serverInfo", {})
        print(f"[OK] MCP Initialized! Server: {server.get('name', '?')} {server.get('version', '')}")
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] MCP Initialization Failed: {e}")
        return

    # 3. Test Tools List
    print("\n[-] Step 3: Fetching Remote MCP Tools...")
    try:
        tools = connector.list_remote_tools()
        print(f"[OK] Found {len(tools)} remote tools:")
        for t in tools:
            print(f"  - {t.get('name')}: {t.get('description', '')[:80]}...")
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] Tool discovery failed: {e}")

    # 4. Test provider stats
    print(f"\n[-] Step 4: Calling trident_get_stats for provider '{config.provider_id}'...")
    try:
        stats = connector.call_tool("trident_get_stats", {"provider_id": config.provider_id})
        print(f"[OK] trident_get_stats response:\n{stats[:1200] if isinstance(stats, str) else stats}")
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] trident_get_stats failed: {e}")

    # 5. Semantic retrieval + region masking check
    print("\n[-] Step 5: trident_get_chunks retrieval and region-masking check...")
    try:
        raw = connector.call_tool("trident_get_chunks", {"provider_id": config.provider_id,
                                                         "query": "Supplier region profile Europe", "top_k": 3})
        hits = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(hits, dict):
            hits = json.loads(hits["result"]) if isinstance(hits.get("result"), str) else hits.get("chunks", [])
        for h in hits if isinstance(hits, list) else []:
            t = h.get("text", "")
            print("  --", h.get("source_file"), "| masked" if "[LOCATION_" in t else "| clear", "|",
                  t[:140].replace("\n", " "))
        print("[OK] Retrieval working")
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] trident_get_chunks failed: {e}")


if __name__ == '__main__':
    main()
