import os

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Problem, Post, ProblemStatus, User, Agent, ProblemAgent, AgentRole, FormulationTemplate
from auth import get_current_user, get_current_user_optional

router = APIRouter(prefix="/problems", tags=["problems"])

# Valid round transitions
NEXT_STATUS = {
    ProblemStatus.open: ProblemStatus.round1,
    ProblemStatus.round1: ProblemStatus.round2,
    ProblemStatus.round2: ProblemStatus.round3,
    ProblemStatus.round3: ProblemStatus.review,
}

STATUS_ROUND = {
    ProblemStatus.round1: 1,
    ProblemStatus.round2: 2,
    ProblemStatus.round3: 3,
}


# --- Schemas ---

class CreateProblemRequest(BaseModel):
    title: str
    description: str


class FeedbackRequest(BaseModel):
    feedback: str = ""
    approved: bool = False


class AssignAgentRequest(BaseModel):
    agent_id: str
    role: str = ""  # role slot to assign to (clarifier, formulator, critic, domain_expert)


# --- Helpers ---

def _serialize_problem(problem: Problem) -> dict:
    return {
        "id": problem.id,
        "title": problem.title,
        "description": problem.description,
        "status": problem.status.value if problem.status else None,
        "created_at": problem.created_at.isoformat() if problem.created_at else None,
        "created_by": problem.created_by,
        "human_feedback": problem.human_feedback,
    }


def _serialize_post(post: Post) -> dict:
    return {
        "id": post.id,
        "agent_id": post.agent_id,
        "agent_name": post.agent.name if post.agent else None,
        "agent_role": post.agent.role.value if post.agent and post.agent.role else "general",
        "round": post.round,
        "content": post.content,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "reply_to": post.reply_to,
        "system_generated": post.system_generated or False,
    }


def _get_problem_or_404(problem_id: str, db: Session) -> Problem:
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Problem '{problem_id}' not found.",
        )
    return problem


# --- Routes ---

@router.post("")
def create_problem(
    body: CreateProblemRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not body.title.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Title is required.",
        )
    if not body.description.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Description is required.",
        )

    problem = Problem(
        title=body.title.strip(),
        description=body.description.strip(),
        status=ProblemStatus.open,
        created_by=user.id,
    )
    db.add(problem)
    db.commit()
    db.refresh(problem)

    return {
        "success": True,
        "data": _serialize_problem(problem),
        "error": None,
    }


ROLE_DESCRIPTIONS = {
    "clarifier": {
        "name": "Clarifier",
        "description": "Identifies gaps, missing data, and ambiguities in the problem statement.",
        "rounds": [1, 2],
    },
    "formulator": {
        "name": "Formulator",
        "description": "Builds the mathematical formulation — decision variables, objective, and constraints.",
        "rounds": [2, 3],
    },
    "critic": {
        "name": "Critic",
        "description": "Evaluates proposed formulations for correctness, completeness, and practical issues.",
        "rounds": [3],
    },
    "domain_expert": {
        "name": "Domain Expert",
        "description": "Provides real-world context and validates formulations against industry practice.",
        "rounds": [1, 2, 3],
    },
}


@router.get("/roles")
def list_roles():
    return {
        "success": True,
        "data": ROLE_DESCRIPTIONS,
        "error": None,
    }


@router.get("")
def list_problems(
    user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if user:
        # Logged in: show user's own problems (clones + created)
        # Demo user sees templates directly; others see their clones
        if user.email == "demo@optimum.app":
            problems = (
                db.query(Problem)
                .filter(Problem.created_by == user.id)
                .order_by(Problem.created_at.desc())
                .all()
            )
        else:
            problems = (
                db.query(Problem)
                .filter(Problem.created_by == user.id, Problem.is_template == False)
                .order_by(Problem.created_at.desc())
                .all()
            )
    else:
        # Anonymous: show templates as preview
        problems = (
            db.query(Problem)
            .filter(Problem.is_template == True)
            .order_by(Problem.created_at.desc())
            .all()
        )
    return {
        "success": True,
        "data": [_serialize_problem(p) for p in problems],
        "error": None,
    }


@router.get("/{problem_id}")
def get_problem(problem_id: str, db: Session = Depends(get_db)):
    problem = _get_problem_or_404(problem_id, db)
    posts = (
        db.query(Post)
        .filter(Post.problem_id == problem_id)
        .order_by(Post.round, Post.created_at)
        .all()
    )

    posts_by_round: dict[int, list] = {}
    for post in posts:
        posts_by_round.setdefault(post.round, []).append(_serialize_post(post))

    return {
        "success": True,
        "data": {
            **_serialize_problem(problem),
            "posts_by_round": posts_by_round,
        },
        "error": None,
    }


@router.get("/{problem_id}/summary")
def get_problem_summary(problem_id: str, db: Session = Depends(get_db)):
    problem = _get_problem_or_404(problem_id, db)
    posts = (
        db.query(Post)
        .filter(Post.problem_id == problem_id)
        .order_by(Post.round, Post.created_at)
        .all()
    )

    rounds = {}
    for post in posts:
        round_key = f"round_{post.round}"
        rounds.setdefault(round_key, []).append(
            {
                "agent": post.agent.name if post.agent else "unknown",
                "role": post.agent.role.value if post.agent and post.agent.role else "general",
                "content": post.content,
                "reply_to": post.reply_to,
            }
        )

    current_round = STATUS_ROUND.get(problem.status)

    return {
        "success": True,
        "data": {
            "id": problem.id,
            "title": problem.title,
            "description": problem.description,
            "status": problem.status.value if problem.status else None,
            "current_round": current_round,
            "human_feedback": problem.human_feedback,
            "rounds": rounds,
        },
        "error": None,
    }


@router.post("/{problem_id}/advance")
def advance_round(
    problem_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    problem = _get_problem_or_404(problem_id, db)

    if problem.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the problem creator can advance the round.",
        )

    next_status = NEXT_STATUS.get(problem.status)
    if next_status is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot advance from status '{problem.status.value}'. Problem is in '{problem.status.value}' state.",
        )

    problem.status = next_status
    db.commit()
    db.refresh(problem)

    return {
        "success": True,
        "data": {
            "message": f"Problem advanced to '{next_status.value}'.",
            **_serialize_problem(problem),
        },
        "error": None,
    }


@router.post("/{problem_id}/feedback")
def submit_feedback(
    problem_id: str,
    body: FeedbackRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    problem = _get_problem_or_404(problem_id, db)

    if problem.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the problem creator can submit feedback.",
        )

    if problem.status != ProblemStatus.review:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Feedback can only be submitted when the problem is in 'review' status. Current status: '{problem.status.value}'.",
        )

    problem.human_feedback = body.feedback

    if body.approved:
        problem.status = ProblemStatus.closed
    else:
        # Send back to round 3 for revision
        problem.status = ProblemStatus.round3

    db.commit()
    db.refresh(problem)

    return {
        "success": True,
        "data": {
            "message": "Formulation approved and problem closed." if body.approved else "Feedback recorded. Problem sent back to round 3 for revision.",
            **_serialize_problem(problem),
        },
        "error": None,
    }


@router.post("/{problem_id}/reset")
def reset_problem(
    problem_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    problem = _get_problem_or_404(problem_id, db)

    if problem.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the problem creator can reset the problem.",
        )

    # Delete all posts
    db.query(Post).filter(Post.problem_id == problem.id).delete()
    problem.status = ProblemStatus.round1
    problem.human_feedback = None
    db.commit()
    db.refresh(problem)

    return {
        "success": True,
        "data": {
            "message": "Problem reset to round 1. All posts deleted.",
            **_serialize_problem(problem),
        },
        "error": None,
    }


# --- Agent assignment endpoints ---

def _serialize_agent(agent: Agent) -> dict:
    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "role": agent.role.value if agent.role else "general",
        "model": agent.model,
    }


@router.post("/{problem_id}/agents")
def assign_agent(
    problem_id: str,
    body: AssignAgentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    problem = _get_problem_or_404(problem_id, db)

    if problem.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the problem creator can assign agents.",
        )

    agent = db.query(Agent).filter(Agent.id == body.agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{body.agent_id}' not found.",
        )

    # Determine role: explicit > agent's default
    assign_role = agent.role
    if body.role:
        try:
            assign_role = AgentRole(body.role)
        except ValueError:
            valid = [r.value for r in AgentRole]
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid role '{body.role}'. Valid roles: {valid}",
            )

    # Check if this role slot is already filled
    existing_role = (
        db.query(ProblemAgent)
        .filter(ProblemAgent.problem_id == problem_id, ProblemAgent.role == assign_role)
        .first()
    )
    if existing_role:
        existing_name = existing_role.agent.name if existing_role.agent else "unknown"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Role '{assign_role.value}' is already filled by '{existing_name}'. Remove them first.",
        )

    # Check if agent is already assigned (any role)
    existing_agent = (
        db.query(ProblemAgent)
        .filter(ProblemAgent.problem_id == problem_id, ProblemAgent.agent_id == body.agent_id)
        .first()
    )
    if existing_agent:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent '{agent.name}' is already assigned to this problem as '{existing_agent.role.value}'.",
        )

    pa = ProblemAgent(problem_id=problem_id, agent_id=body.agent_id, role=assign_role)
    db.add(pa)
    db.commit()

    return {
        "success": True,
        "data": {**_serialize_agent(agent), "assigned_role": assign_role.value},
        "error": None,
    }


@router.delete("/{problem_id}/agents/{agent_id}")
def unassign_agent(
    problem_id: str,
    agent_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    problem = _get_problem_or_404(problem_id, db)

    if problem.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the problem creator can remove agents.",
        )

    pa = (
        db.query(ProblemAgent)
        .filter(ProblemAgent.problem_id == problem_id, ProblemAgent.agent_id == agent_id)
        .first()
    )
    if not pa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent is not assigned to this problem.",
        )

    db.delete(pa)
    db.commit()

    return {
        "success": True,
        "data": {"message": "Agent removed from problem."},
        "error": None,
    }


@router.get("/{problem_id}/agents")
def list_problem_agents(
    problem_id: str,
    db: Session = Depends(get_db),
):
    _get_problem_or_404(problem_id, db)

    assignments = (
        db.query(ProblemAgent)
        .filter(ProblemAgent.problem_id == problem_id)
        .all()
    )

    agents = []
    for pa in assignments:
        if pa.agent:
            agents.append({**_serialize_agent(pa.agent), "assigned_role": pa.role.value if pa.role else pa.agent.role.value})

    return {
        "success": True,
        "data": agents,
        "error": None,
    }


# --- Run round (server-side LLM agent execution) ---

ROLE_ALLOWED_ROUNDS = {
    AgentRole.general: {1, 2, 3},
    AgentRole.clarifier: {1, 2},
    AgentRole.formulator: {2, 3},
    AgentRole.critic: {3},
    AgentRole.domain_expert: {1, 2, 3},
}

ROLE_PERSONAS = {
    AgentRole.formulator: (
        "You are an expert in mathematical optimization. "
        "You build rigorous formulations with decision variables, objectives, and constraints."
    ),
    AgentRole.clarifier: (
        "You are a data analyst focused on practical feasibility. "
        "You identify missing data, ambiguous objectives, and unclear constraints."
    ),
    AgentRole.critic: (
        "You are a critical evaluator of optimization formulations. "
        "You check for correctness, completeness, and practical issues."
    ),
    AgentRole.domain_expert: (
        "You are a domain expert who provides real-world context. "
        "You validate formulations against industry practice and flag unrealistic assumptions."
    ),
    AgentRole.general: (
        "You are a general optimization assistant. "
        "You contribute analysis, formulations, or critiques as needed."
    ),
}

ROUND_INSTRUCTIONS = {
    1: "Round 1 — Identify Gaps. Post what is missing or ambiguous. Do NOT formulate yet.",
    2: "Round 2 — Discuss & Refine. Respond to specific points from other agents. Build consensus.",
    3: (
        "Round 3 — Formulation & Evaluation. Use LaTeX ($$...$$ for display, $...$ for inline) for ALL math.\n\n"
        "If you are a FORMULATOR, write a complete structured formulation with these EXACT sections:\n"
        "## Decision Variables - list every variable with LaTeX symbol AND English explanation.\n"
        "## Parameters - list every parameter with LaTeX symbol and English meaning.\n"
        "## Objective Function - state min/max, write full expression in $$...$$, explain in English.\n"
        "## Constraints - number each, write in $$...$$, explain in English what it enforces.\n"
        "## Data Requirements - list what real-world data is needed.\n\n"
        "If you are a CRITIC, evaluate the FORMULATOR's formulation. Check: (1) undefined symbols, "
        "(2) inconsistent indices, (3) missing constraints, (4) math errors, (5) completeness.\n\n"
        "If you are a DOMAIN EXPERT, validate the formulation against real-world operations."
    ),
}


def _build_rounds_context(posts_by_round: dict) -> str:
    context = ""
    for rnd in [1, 2, 3]:
        posts = posts_by_round.get(str(rnd), [])
        if posts:
            context += f"\n### Round {rnd}:\n"
            for p in posts:
                name = p.agent.name if p.agent else "Unknown"
                context += f"**{name}**: {p.content}\n\n"
    return context


def _call_llm(agent_name: str, system_prompt: str, user_prompt: str, model: str = "gpt-4o", max_tokens: int = 800) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY not set on server.",
        )
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    is_reasoning = any(r in model for r in ["o1", "o3", "5.2", "5-2"])
    create_kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    if is_reasoning:
        create_kwargs["max_completion_tokens"] = max_tokens
    else:
        create_kwargs["max_tokens"] = max_tokens
        create_kwargs["temperature"] = 0.7
    response = client.chat.completions.create(**create_kwargs)
    return response.choices[0].message.content.strip()


@router.post("/{problem_id}/run-round")
def run_round(
    problem_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    problem = _get_problem_or_404(problem_id, db)

    if problem.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the problem creator can run agents.",
        )

    current_round = STATUS_ROUND.get(problem.status)
    if current_round is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Problem is in '{problem.status.value}' status — not in an active round.",
        )

    # Get assigned agents
    assignments = (
        db.query(ProblemAgent)
        .filter(ProblemAgent.problem_id == problem_id)
        .all()
    )

    # Auto-assign if no agents assigned: pick random agents to fill all 4 role slots
    if not assignments:
        import random
        all_agents = db.query(Agent).all()
        if not all_agents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No agents registered on the platform.",
            )
        needed_roles = [AgentRole.clarifier, AgentRole.formulator, AgentRole.critic, AgentRole.domain_expert]
        available = list(all_agents)
        random.shuffle(available)
        for role in needed_roles:
            if not available:
                break
            agent = available.pop(0)
            pa = ProblemAgent(problem_id=problem_id, agent_id=agent.id, role=role)
            db.add(pa)
        db.flush()
        assignments = (
            db.query(ProblemAgent)
            .filter(ProblemAgent.problem_id == problem_id)
            .all()
        )

    # Get existing posts for context
    all_posts = (
        db.query(Post)
        .filter(Post.problem_id == problem_id)
        .order_by(Post.round, Post.created_at)
        .all()
    )
    posts_by_round: dict[str, list] = {}
    for p in all_posts:
        posts_by_round.setdefault(str(p.round), []).append(p)

    rounds_context = _build_rounds_context(posts_by_round)
    human_feedback = ""
    if problem.human_feedback:
        human_feedback = f"\n\n## HUMAN OPERATOR FEEDBACK (address this directly):\n{problem.human_feedback}"

    results = []
    for pa in assignments:
        agent = pa.agent
        if not agent:
            continue
        role = pa.role  # use the problem-specific assigned role
        allowed = ROLE_ALLOWED_ROUNDS.get(role, {1, 2, 3})
        if current_round not in allowed:
            results.append({"agent": agent.name, "role": role.value, "status": "skipped", "reason": f"role '{role.value}' not active in round {current_round}"})
            continue

        # Check rate limit
        existing_count = (
            db.query(Post)
            .filter(Post.problem_id == problem_id, Post.agent_id == agent.id, Post.round == current_round)
            .count()
        )
        if existing_count >= 3:
            results.append({"agent": agent.name, "role": role.value, "status": "skipped", "reason": "rate limit (3 posts)"})
            continue

        persona = ROLE_PERSONAS.get(role, ROLE_PERSONAS[AgentRole.general])
        sys_prompt = (
            f"You are {agent.name}. {agent.description or ''}\n\n"
            f"{persona}\n\n"
            f"Your assigned role on this problem is '{role.value}'. {ROUND_INSTRUCTIONS[current_round]}\n\n"
            "COLLABORATION RULE: Start every post with a '## Synthesis' section referencing other agents by name.\n"
            "Use LaTeX: $...$ for inline math, $$...$$ for display math.\n"
            "Write 200-400 words. Use markdown. Do NOT repeat others. Build on their work."
        )
        usr_prompt = (
            f"## Problem: {problem.title}\n\n{problem.description}"
            f"{human_feedback}\n\n"
            f"## Prior Discussion:{rounds_context or ' None yet.'}\n\n"
            f"Write your Round {current_round} contribution."
        )

        try:
            content = _call_llm(agent.name, sys_prompt, usr_prompt, model=agent.model or "gpt-4o")
            post = Post(
                problem_id=problem_id,
                agent_id=agent.id,
                round=current_round,
                content=content,
            )
            db.add(post)
            db.flush()
            results.append({"agent": agent.name, "role": role.value, "status": "posted"})
        except Exception as e:
            results.append({"agent": agent.name, "role": role.value, "status": "error", "reason": str(e)})

    db.commit()

    return {
        "success": True,
        "data": {
            "round": current_round,
            "results": results,
        },
        "error": None,
    }


# --- Compile final formulation ---

COMPILE_SYSTEM_PROMPT = """You are a professor of Operations Research producing the FINAL, VALIDATED mathematical formulation for an optimization problem.

You will receive:
1. Agent contributions from 3 discussion rounds
2. Reference formulations from a template library showing CORRECT standard patterns for the relevant problem type

Your job: synthesize all inputs into ONE complete, solver-ready formulation.

STEP 1 — PROBLEM TYPE IDENTIFICATION:
First, identify what standard optimization problem type the English description maps to (e.g., VRP, VRPTW, CVRP, facility location, job-shop scheduling, knapsack, set covering, assignment, network flow, etc.). State this explicitly.

STEP 2 — USE THE REFERENCE TEMPLATES:
The reference formulations show the CORRECT, STANDARD structure for this problem type. They come from textbook sources. Your formulation MUST include ALL the standard constraints shown in the matching reference template. These are not optional — they are the minimum requirements for a valid formulation of this problem type.

If the English problem adds requirements beyond the base template (e.g., time windows on top of VRP, or special handling constraints), extend the template with additional variables and constraints for those features. But NEVER drop standard constraints from the template.

STEP 3 — QUALITY RULES:
1. Every symbol in ANY expression MUST be defined in Sets, Decision Variables, or Parameters. ZERO undefined symbols.
2. Variable indices must be consistent throughout. The same letter always means the same thing.
3. The formulation must be implementable in a solver (Gurobi, CPLEX, etc.) — linearize any nonlinear terms (max, min, abs) using auxiliary variables and big-M.
4. Do not mix contradictory modeling choices (e.g., hard constraint T_i <= b_i AND soft penalty for lateness max(0, T_i - b_i) — pick one).
5. Every parameter declared must appear in at least one expression. Every variable must appear in at least one constraint or the objective.
6. Use $...$ for inline math and $$...$$ for display math.

OUTPUT FORMAT:

## Problem Type
State the identified problem type and why.

## Sets and Indices
Define all sets and index conventions with clear notation.

## Decision Variables
For each: "$symbol$: English description, type (binary/continuous/integer), domain."

## Parameters (Given Data)
For each: "$symbol$: English description, units."

## Objective Function
$$expression$$
**In plain English:** What this optimizes.

## Constraints
For each:
**Constraint N: Name**
$$expression$$
*English:* What real-world requirement this enforces and why it's needed.

## Data Requirements
What data must be collected.

## Assumptions
Key modeling assumptions."""


def _search_templates(description: str, db: Session) -> list:
    """Search formulation template library for relevant references."""
    keywords = [
        "routing", "vehicle", "delivery", "scheduling", "facility",
        "assignment", "network", "flow", "knapsack", "covering",
        "transport", "location", "portfolio", "investment",
    ]
    desc_lower = description.lower()
    matched = [k for k in keywords if k in desc_lower]

    templates = []
    seen_ids = set()
    for kw in matched[:3]:
        query = kw.lower()
        all_templates = db.query(FormulationTemplate).all()
        for t in all_templates:
            if t.id in seen_ids:
                continue
            searchable = " ".join([
                t.name.lower(), t.alias.lower(), t.category.lower(),
                t.description.lower(), " ".join(tag.lower() for tag in (t.tags or [])),
            ])
            if query in searchable:
                templates.append(t)
                seen_ids.add(t.id)

    return templates[:2]


def _format_template_reference(t) -> str:
    ref = f"### Reference: {t.name} ({t.alias})\n"
    ref += f"**Category:** {t.category}\n"
    ref += f"**Description:** {t.description}\n\n"
    ref += "**Decision Variables:**\n"
    for v in (t.decision_variables or []):
        ref += f"- ${v['name']}$: {v['description']} ({v.get('type', '')})\n"
    ref += f"\n**Objective:** {t.objective.get('type', '')} {t.objective.get('expression', '')}\n"
    ref += f"{t.objective.get('description', '')}\n\n"
    ref += "**Constraints:**\n"
    for c in (t.constraints or []):
        ref += f"- **{c.get('name', '')}**: {c.get('expression', '')} — {c.get('description', '')}\n"
    ref += "\n**Parameters:**\n"
    for p in (t.parameters or []):
        ref += f"- ${p['name']}$: {p['description']}\n"
    if t.source:
        ref += f"\n**Source:** {t.source}\n"
    return ref


COMPILE_LIMIT_PER_USER = 2   # max compiles per user per day
COMPILE_LIMIT_GLOBAL = 15    # max compiles across all users per day

# In-memory rate tracking — resets on server restart (fine for class project)
_compile_tracker: dict = {"date": "", "global": 0, "users": {}}


def _check_compile_limits(user_id: str):
    """Check per-user and global daily compile limits. Raises HTTPException if exceeded."""
    from datetime import date
    today = date.today().isoformat()

    # Reset counters on new day
    if _compile_tracker["date"] != today:
        _compile_tracker["date"] = today
        _compile_tracker["global"] = 0
        _compile_tracker["users"] = {}

    user_count = _compile_tracker["users"].get(user_id, 0)

    if user_count >= COMPILE_LIMIT_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"You've used your {COMPILE_LIMIT_PER_USER} daily compilations. "
                "The final formulation uses an advanced reasoning model which is resource-intensive. "
                "You can still use the individual Round 3 formulations from your agents — "
                "those are already high-quality contributions you can work with directly."
            ),
        )

    if _compile_tracker["global"] >= COMPILE_LIMIT_GLOBAL:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"The platform has reached its daily compilation limit ({COMPILE_LIMIT_GLOBAL} total). "
                "This resets at midnight. In the meantime, you can use the individual Round 3 "
                "formulations from your agents — the formulator's post contains a complete "
                "mathematical formulation you can work with directly."
            ),
        )


def _record_compile(user_id: str):
    """Record a successful compile for rate tracking."""
    _compile_tracker["global"] += 1
    _compile_tracker["users"][user_id] = _compile_tracker["users"].get(user_id, 0) + 1


@router.post("/{problem_id}/compile")
def compile_formulation(
    problem_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compile all round contributions into a final formulation using a strong model."""
    # Check rate limits before doing anything expensive
    _check_compile_limits(user.id)

    problem = _get_problem_or_404(problem_id, db)

    if problem.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the problem creator can compile the formulation.",
        )

    # Must have round 3 posts
    r3_posts = (
        db.query(Post)
        .filter(Post.problem_id == problem_id, Post.round == 3)
        .count()
    )
    if r3_posts == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Round 3 formulations yet. Complete Round 3 before compiling.",
        )

    # Gather all posts
    all_posts = (
        db.query(Post)
        .filter(Post.problem_id == problem_id)
        .order_by(Post.round, Post.created_at)
        .all()
    )
    rounds_context = ""
    for rnd in [1, 2, 3]:
        posts = [p for p in all_posts if p.round == rnd]
        if posts:
            rounds_context += f"\n### Round {rnd}:\n"
            for p in posts:
                name = p.agent.name if p.agent else "Unknown"
                role = p.agent.role.value if p.agent and p.agent.role else "agent"
                rounds_context += f"**{name}** ({role}):\n{p.content}\n\n"

    # Search template library
    templates = _search_templates(problem.description, db)
    template_context = ""
    if templates:
        template_context = "\n\n## REFERENCE FORMULATIONS FROM TEMPLATE LIBRARY\n"
        template_context += "Use these as structural guides. They show the CORRECT standard formulation patterns for this problem type. Your output MUST include all standard constraints shown here, adapted to the specific problem.\n\n"
        for t in templates:
            template_context += _format_template_reference(t) + "\n---\n"

    human_feedback = ""
    if problem.human_feedback:
        human_feedback = f"\n## Human Operator Feedback:\n{problem.human_feedback}\n"

    user_prompt = (
        f"## Problem: {problem.title}\n\n{problem.description}"
        f"{human_feedback}\n\n"
        f"## All Agent Contributions:\n{rounds_context}"
        f"{template_context}\n\n"
        "Produce the FINAL consolidated formulation. First identify the problem type. "
        "Then use the reference templates as your structural foundation — include ALL "
        "standard constraints from the matching template. Extend with additional constraints "
        "for problem-specific requirements. Define every symbol. The formulation must be solver-ready."
    )

    content = _call_llm(
        agent_name="Consolidator",
        system_prompt=COMPILE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        model="gpt-5.2",
        max_tokens=16000,
    )

    # Record successful compile for rate limiting
    _record_compile(user.id)

    remaining = COMPILE_LIMIT_PER_USER - _compile_tracker["users"].get(user.id, 0)

    return {
        "success": True,
        "data": {
            "formulation": content,
            "templates_used": [t.alias for t in templates],
            "compiles_remaining_today": remaining,
        },
        "error": None,
    }
