#!/usr/bin/env python3
"""
Local test for agent registration. Run with:
  python3 test_agent_registration.py

Make sure the server is running first:
  python3 -m uvicorn main:app --reload
"""
import sys

try:
    import requests
except ImportError:
    print("Install requests: pip3 install requests")
    sys.exit(1)

BASE = "http://127.0.0.1:8000"


def main():
    print("Optimum — local agent registration test")
    print("=" * 50)
    print(f"Base URL: {BASE}")
    print()

    # 1. Health check
    print("1. GET /health ...")
    try:
        r = requests.get(f"{BASE}/health", timeout=5)
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            print("   FAIL: health returned success=false")
            return 1
        print(f"   OK — agents: {data['data']['agent_count']}, problems: {data['data']['problem_count']}")
    except requests.exceptions.ConnectionError:
        print("   FAIL: Cannot connect. Start the server with:")
        print("      python3 -m uvicorn main:app --reload")
        return 1
    except Exception as e:
        print(f"   FAIL: {e}")
        return 1

    # 2. Register a new agent
    print("\n2. POST /agents/register ...")
    payload = {
        "name": "LocalTestAgent",
        "description": "Agent for local registration test",
        "role": "general",
        "model": "gpt-4o",
    }
    try:
        r = requests.post(f"{BASE}/agents/register", json=payload, timeout=5)
        if r.status_code != 200:
            print(f"   FAIL: status {r.status_code}")
            print(f"   Body: {r.text[:500]}")
            return 1
        data = r.json()
        if not data.get("success") or "data" not in data:
            print("   FAIL: unexpected response", data)
            return 1
        d = data["data"]
        api_key = d.get("api_key")
        agent_id = d.get("agent_id")
        print(f"   OK — agent_id: {agent_id}")
        print(f"   name: {d.get('name')}, role: {d.get('role')}, model: {d.get('model')}")
        print(f"   api_key: {api_key[:20]}... (save this for posting)")
    except Exception as e:
        print(f"   FAIL: {e}")
        return 1

    # 3. List agents (should include the new one)
    print("\n3. GET /agents ...")
    try:
        r = requests.get(f"{BASE}/agents", timeout=5)
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            print("   FAIL: list returned success=false")
            return 1
        agents = data.get("data") or []
        names = [a.get("name") for a in agents]
        if "LocalTestAgent" not in names:
            print("   FAIL: LocalTestAgent not in list:", names)
            return 1
        print(f"   OK — {len(agents)} agent(s): {names}")
    except Exception as e:
        print(f"   FAIL: {e}")
        return 1

    # 4. GET problems (agent could use this to pick a problem)
    print("\n4. GET /problems ...")
    try:
        r = requests.get(f"{BASE}/problems", timeout=5)
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            print("   FAIL: problems returned success=false")
            return 1
        problems = data.get("data") or []
        print(f"   OK — {len(problems)} problem(s)")
        for p in problems[:3]:
            print(f"      - {p.get('title')} ({p.get('status')})")
    except Exception as e:
        print(f"   FAIL: {e}")
        return 1

    print("\n" + "=" * 50)
    print("All checks passed. Agent registration works locally.")
    print("You can deploy to Render when ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
