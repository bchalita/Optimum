"""
Optimum Agent Simulator — runs LLM-powered agents against the Optimum API.

Usage:
    export OPENAI_API_KEY=sk-...
    python simulate.py                          # run all eligible agents for current round
    python simulate.py --agent MathBot          # run only MathBot
    python simulate.py --base-url https://...   # use a different backend URL
    python simulate.py --round-trip             # run agents, then advance round, repeat for all rounds
"""

import argparse
import json
import os
import sys
import time

import requests
from openai import OpenAI

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("OPTIMUM_URL", "http://localhost:8000")

SYNTHESIS_RULE = (
    "IMPORTANT COLLABORATION RULE: You must start every post with a '## Synthesis' "
    "section where you explicitly reference what the other agents said. Name them, "
    "summarize their key points, and explain what you will incorporate or respond to. "
    "Only after this synthesis should you proceed with your own contribution."
)

SEED_AGENTS = {
    "MathBot": {
        "key": "sk-opt-seed-mathbot-000000000000000000000001",
        "role": "formulator",
        "persona": (
            "You are MathBot, an expert in mathematical optimization. "
            "You specialize in formulating optimization problems rigorously: "
            "defining decision variables, writing objective functions, and "
            "identifying constraints. Use LaTeX for ALL math expressions. "
            "Use $...$ for inline math and $$...$$ for display equations. "
            "Example: $x_{ij}$ for inline, $$\\sum_i c_i x_i$$ for display. "
        ) + SYNTHESIS_RULE,
    },
    "DataScout": {
        "key": "sk-opt-seed-datascout-00000000000000000000002",
        "role": "clarifier",
        "persona": (
            "You are DataScout, a data analyst focused on practical feasibility. "
            "You identify missing data, ambiguous requirements, and assumptions "
            "that need validation. You ask the right questions to make problems "
            "solvable. Use $...$ for inline math when referencing variables. "
        ) + SYNTHESIS_RULE,
    },
    "CritiBot": {
        "key": "sk-opt-seed-critibot-00000000000000000000003",
        "role": "critic",
        "persona": (
            "You are CritiBot, a critical evaluator of optimization formulations. "
            "You check formulations for correctness, completeness, and practicality. "
            "You identify missing constraints, incorrect variable types, and "
            "suggest concrete improvements. Be constructive but rigorous. "
            "Use $...$ for inline math and $$...$$ for display math. "
        ) + SYNTHESIS_RULE,
    },
    "LogiPro": {
        "key": "sk-opt-seed-logipro-000000000000000000000004",
        "role": "domain_expert",
        "persona": (
            "You are LogiPro, a logistics and supply chain domain expert. "
            "You provide real-world context: typical cost structures, industry "
            "constraints, practical considerations that pure mathematicians miss. "
            "Ground the discussion in reality. "
            "Use $...$ for inline math when referencing variables. "
        ) + SYNTHESIS_RULE,
    },
}

ROLE_ALLOWED_ROUNDS = {
    "general": {1, 2, 3},
    "clarifier": {1, 2},
    "formulator": {2, 3},
    "critic": {3},
    "domain_expert": {1, 2, 3},
}

ROUND_INSTRUCTIONS = {
    1: (
        "This is Round 1 — Identify Gaps. Read the problem description carefully. "
        "Post what you think is missing or ambiguous. Focus on: missing data, "
        "ambiguous objectives, unclear constraints, assumptions that need validation, "
        "and scale/feasibility concerns. Do NOT write a formulation yet."
    ),
    2: (
        "This is Round 2 — Discuss & Refine. Read all Round 1 posts from other agents. "
        "Respond to specific points: agree with observations and add reasoning, "
        "add new points others missed, flag disagreements with constructive alternatives. "
        "Build on the discussion. Do NOT write a full formulation yet."
    ),
    3: (
        "This is Round 3 — Mathematical Formulation. Use $...$ for inline math and $$...$$ for display math. "
        "Based on all prior discussion, post your contribution.\n\n"
        "If you are a FORMULATOR, write a complete formulation with these EXACT sections:\n"
        "## Decision Variables - list every variable with its LaTeX symbol AND plain English explanation "
        "(e.g., '$x_{ij}$: number of units shipped from warehouse $i$ to customer $j$')\n"
        "## Parameters - list every parameter with LaTeX symbol and English meaning. "
        "IMPORTANT: Every symbol that appears in any expression MUST be defined here or in Decision Variables. "
        "Do NOT use any undefined symbols.\n"
        "## Objective Function - state min/max, write the full expression in $$...$$, "
        "then explain IN ENGLISH what it optimizes\n"
        "## Constraints - number each constraint, write in $$...$$, then explain in English\n"
        "## Data Requirements - list what real-world data is needed\n\n"
        "If you are a CRITIC, DO NOT write your own formulation. Instead, evaluate the FORMULATOR's "
        "formulation posted above. Check for: (1) undefined symbols/parameters, (2) inconsistent variable "
        "indices, (3) missing constraints, (4) mathematical errors, (5) completeness. List specific issues "
        "and suggest concrete fixes.\n\n"
        "If you are a DOMAIN EXPERT, DO NOT write your own formulation or define your own variables. "
        "Instead, REVIEW the FORMULATOR's formulation above and validate it against real-world operations. "
        "Structure your response as: (1) What the formulator got right, (2) What cost structures or "
        "operational constraints are missing or unrealistic, (3) Specific improvements with references to "
        "the formulator's existing variables. Do NOT introduce new variable names."
    ),
}


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_get(path):
    r = requests.get(BASE_URL + path)
    data = r.json()
    if not data["success"]:
        print(f"  [ERROR] GET {path}: {data['error']}")
        return None
    return data["data"]


def api_post_as_agent(path, api_key, body):
    r = requests.post(
        BASE_URL + path,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        json=body,
    )
    data = r.json()
    if not data["success"]:
        print(f"  [ERROR] POST {path}: {data['error']}")
        return None
    return data["data"]


def api_post_auth(path, token, body=None):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(BASE_URL + path, headers=headers, json=body or {})
    data = r.json()
    if not data["success"]:
        print(f"  [ERROR] POST {path}: {data['error']}")
        return None
    return data["data"]


def login():
    r = requests.post(
        BASE_URL + "/auth/login",
        json={"email": "demo@optimum.app", "password": "demo1234"},
    )
    data = r.json()
    if not data["success"]:
        print(f"  [ERROR] Login failed: {data['error']}")
        return None
    return data["data"]["access_token"]


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def generate_post(agent_name, agent_info, problem_summary, current_round):
    client = OpenAI()

    # Build context from prior rounds
    rounds_context = ""
    for rnd_key in ["round_1", "round_2", "round_3"]:
        posts = problem_summary.get("rounds", {}).get(rnd_key, [])
        if posts:
            rounds_context += f"\n### {rnd_key.replace('_', ' ').title()}:\n"
            for p in posts:
                rounds_context += f"**{p['agent']}**: {p['content']}\n\n"

    human_feedback = problem_summary.get("human_feedback")
    feedback_section = ""
    if human_feedback:
        feedback_section = (
            f"\n\n## HUMAN OPERATOR FEEDBACK (IMPORTANT — address this directly):\n"
            f"{human_feedback}"
        )

    system_prompt = (
        f"{agent_info['persona']}\n\n"
        f"You are participating in Optimum, a multi-agent optimization platform. "
        f"Your role is '{agent_info['role']}'. "
        f"{ROUND_INSTRUCTIONS[current_round]}\n\n"
        f"Write a substantive, focused contribution (200-400 words). Use markdown. "
        f"Do NOT repeat what other agents have already said. Build on their work. "
        f"Start with a ## Synthesis section referencing other agents by name."
    )

    user_prompt = (
        f"## Problem: {problem_summary['title']}\n\n"
        f"{problem_summary['description']}"
        f"{feedback_section}\n\n"
        f"## Prior Discussion:{rounds_context if rounds_context else ' None yet.'}\n\n"
        f"Write your Round {current_round} contribution now. "
        f"Remember to start with a ## Synthesis section."
    )

    # More tokens for R3 formulations
    tokens = 2000 if current_round == 3 else 1000

    print(f"  Calling OpenAI for {agent_name} (max {tokens} tokens)...")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=tokens,
        temperature=0.7,
    )

    content = response.choices[0].message.content
    if content is None:
        refusal = getattr(response.choices[0].message, 'refusal', None)
        print(f"  [{agent_name}] Model returned None content. Refusal: {refusal}")
        print(f"  [{agent_name}] Finish reason: {response.choices[0].finish_reason}")
        return ""
    return content.strip()


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def run_agents(problem_id, only_agent=None):
    """Run all eligible agents for the current round of a problem."""
    summary = api_get(f"/problems/{problem_id}/summary")
    if not summary:
        return

    current_round = summary.get("current_round")
    if current_round is None:
        print(f"  Problem is in '{summary['status']}' — not accepting posts.")
        return

    print(f"\n{'='*60}")
    print(f"  Problem: {summary['title']}")
    print(f"  Status: {summary['status']} (Round {current_round})")
    print(f"{'='*60}")

    # Fetch live roles from the API (in case human reassigned them)
    agents_data = api_get("/agents")
    live_roles = {}
    if agents_data:
        for a in agents_data:
            live_roles[a["name"]] = a["role"]

    for agent_name, agent_info in SEED_AGENTS.items():
        if only_agent and agent_name != only_agent:
            continue

        # Use live role from API, fall back to seed default
        role = live_roles.get(agent_name, agent_info["role"])
        allowed = ROLE_ALLOWED_ROUNDS.get(role, {1, 2, 3})

        if current_round not in allowed:
            print(f"\n  [{agent_name}] Role '{role}' cannot post in round {current_round} — skipping.")
            continue

        print(f"\n  [{agent_name}] ({role}) generating round {current_round} post...")

        # Use live role in agent_info for the LLM call
        info_with_live_role = {**agent_info, "role": role}
        content = generate_post(agent_name, info_with_live_role, summary, current_round)

        if not content:
            print(f"  [{agent_name}] LLM returned empty content — skipping.")
            continue

        print(f"  [{agent_name}] Posting ({len(content)} chars)...")
        result = api_post_as_agent(
            f"/problems/{problem_id}/posts",
            agent_info["key"],
            {"content": content},
        )
        if result:
            print(f"  [{agent_name}] Posted successfully: {result['id'][:8]}...")
        else:
            print(f"  [{agent_name}] Post failed.")

        # Small delay between agents
        time.sleep(1)

    print(f"\n  Round {current_round} simulation complete.")


def round_trip(problem_id):
    """Run agents for each remaining round, advancing between rounds."""
    token = login()
    if not token:
        print("Cannot login as demo user — needed for advancing rounds.")
        return

    for _ in range(3):  # max 3 rounds
        summary = api_get(f"/problems/{problem_id}/summary")
        if not summary:
            return

        current_round = summary.get("current_round")
        if current_round is None:
            print(f"\n  Problem is in '{summary['status']}' — round trip complete.")
            return

        run_agents(problem_id)

        # Advance to next round
        print(f"\n  Advancing round...")
        result = api_post_auth(f"/problems/{problem_id}/advance", token)
        if result:
            print(f"  Advanced to: {result.get('status', '?')}")
        else:
            print("  Could not advance — stopping.")
            return

        time.sleep(1)

    print("\n  Round trip finished. Problem should now be in 'review' status.")


def main():
    parser = argparse.ArgumentParser(description="Optimum Agent Simulator")
    parser.add_argument("--base-url", default=None, help="Backend URL")
    parser.add_argument("--agent", default=None, help="Run only this agent (e.g., MathBot)")
    parser.add_argument("--problem", default=None, help="Problem ID (defaults to first problem)")
    parser.add_argument("--round-trip", action="store_true", help="Run all rounds automatically")
    args = parser.parse_args()

    global BASE_URL
    if args.base_url:
        BASE_URL = args.base_url.rstrip("/")

    # Check for OpenAI key
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: Set OPENAI_API_KEY environment variable.")
        print("  export OPENAI_API_KEY=sk-...")
        sys.exit(1)

    print(f"Optimum Agent Simulator")
    print(f"Backend: {BASE_URL}")

    # Find problem
    if args.problem:
        problem_id = args.problem
    else:
        problems = api_get("/problems")
        if not problems:
            print("No problems found.")
            sys.exit(1)
        # Pick the first non-closed problem
        active = [p for p in problems if p["status"] not in ("closed", "open")]
        if not active:
            active = problems
        problem_id = active[0]["id"]

    if args.round_trip:
        round_trip(problem_id)
    else:
        run_agents(problem_id, only_agent=args.agent)


if __name__ == "__main__":
    main()
