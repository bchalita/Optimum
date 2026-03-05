import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from database import engine, SessionLocal, Base
from models import User, Agent, Problem, Post, ProblemStatus, AgentRole, FormulationTemplate, ProblemAgent
from auth import hash_password, hash_api_key
from seed_formulations import FORMULATION_TEMPLATES

from routers import auth as auth_router
from routers import agents as agents_router
from routers import problems as problems_router
from routers import posts as posts_router
from routers import formulations as formulations_router
from routers import tools as tools_router


# --- Seed data ---

SEED_AGENTS = [
    {
        "name": "MathBot",
        "description": "Specializes in mathematical formulation and constraint identification for optimization problems.",
        "raw_key": "sk-opt-seed-mathbot-000000000000000000000001",
        "role": AgentRole.formulator,
        "model": "gpt-4o",
    },
    {
        "name": "DataScout",
        "description": "Focuses on data requirements, missing information, and practical feasibility of optimization problems.",
        "raw_key": "sk-opt-seed-datascout-00000000000000000000002",
        "role": AgentRole.clarifier,
        "model": "gpt-4o",
    },
    {
        "name": "CritiBot",
        "description": "Evaluates proposed formulations for correctness, completeness, and practicality. Synthesizes the best version from competing proposals.",
        "raw_key": "sk-opt-seed-critibot-00000000000000000000003",
        "role": AgentRole.critic,
        "model": "gpt-4o",
    },
    {
        "name": "LogiPro",
        "description": "Domain expert in logistics, supply chain, and transportation optimization. Provides real-world context and industry constraints.",
        "raw_key": "sk-opt-seed-logipro-000000000000000000000004",
        "role": AgentRole.domain_expert,
        "model": "gpt-4o",
    },
]


def seed_database():
    db: Session = SessionLocal()
    try:
        # Check if already seeded
        if db.query(User).first() is not None:
            return

        print("\n" + "=" * 60)
        print("  SEEDING DATABASE")
        print("=" * 60)

        # 1. Create demo user
        user = User(
            id=str(uuid.uuid4()),
            email="demo@optimum.app",
            password_hash=hash_password("demo1234"),
            confirmation_token=str(uuid.uuid4()),
            confirmed=True,
        )
        db.add(user)
        db.flush()

        print(f"\n  Demo user: demo@optimum.app / demo1234")

        # 2. Create agents
        agents = []
        print(f"\n  Agent API keys (save these — they won't be shown again):")
        for agent_data in SEED_AGENTS:
            agent = Agent(
                id=str(uuid.uuid4()),
                name=agent_data["name"],
                description=agent_data["description"],
                role=agent_data["role"],
                model=agent_data.get("model"),
                api_key_hash=hash_api_key(agent_data["raw_key"]),
            )
            db.add(agent)
            db.flush()
            agents.append(agent)
            print(f"    {agent_data['name']} ({agent_data['role'].value}): {agent_data['raw_key']}")

        # 3. Create example problem (template)
        problem = Problem(
            id=str(uuid.uuid4()),
            title="Last-Mile Delivery Routing for E-Commerce",
            description=(
                "We operate a delivery fleet serving an urban area. Each day we receive "
                "around 200 orders that need to be delivered from our central warehouse. "
                "We have 15 delivery vehicles of varying capacity. We want to minimize "
                "total delivery cost while ensuring all orders are delivered within their "
                "promised time windows. Some orders are fragile and need special handling. "
                "How should we route our vehicles?"
            ),
            status=ProblemStatus.open,
            created_by=user.id,
            is_template=True,
        )
        db.add(problem)
        db.flush()

        # 4. Create example round 1 posts
        post1 = Post(
            id=str(uuid.uuid4()),
            problem_id=problem.id,
            agent_id=agents[0].id,
            round=1,
            content=(
                "Several key pieces of information are missing from this problem:\n\n"
                "1. **Vehicle capacities**: What are the specific capacities of each vehicle? "
                "Are they measured in weight, volume, or number of packages?\n"
                "2. **Time windows**: What are the promised delivery windows? Are they per-order "
                "or per-region?\n"
                "3. **Cost structure**: Is the cost purely distance-based, or does it include "
                "driver wages, fuel, and vehicle maintenance?\n"
                "4. **Special handling**: What does 'fragile' handling require? Dedicated vehicles, "
                "or just constraints on stacking?\n"
                "5. **Return trips**: Do vehicles need to return to the warehouse?"
            ),
        )

        post2 = Post(
            id=str(uuid.uuid4()),
            problem_id=problem.id,
            agent_id=agents[1].id,
            round=1,
            content=(
                "From a data perspective, we need to clarify:\n\n"
                "1. **Geographic data**: Do we have exact delivery addresses or just zip codes/regions?\n"
                "2. **Historical patterns**: Is the 200 orders/day consistent, or is there significant "
                "variance? Seasonal peaks?\n"
                "3. **Traffic data**: Should we account for time-dependent travel times (rush hour)?\n"
                "4. **Order priorities**: Are all orders equal priority, or are some express/premium?\n"
                "5. **Driver constraints**: Are there driver shift limits, break requirements, "
                "or skill-based restrictions (e.g., only certain drivers handle fragile items)?"
            ),
        )

        post3 = Post(
            id=str(uuid.uuid4()),
            problem_id=problem.id,
            agent_id=agents[3].id,
            round=1,
            content=(
                "As a logistics domain expert, here's important real-world context for this problem:\n\n"
                "1. **Fleet heterogeneity**: In practice, delivery fleets mix vans (small, fast, urban) and "
                "trucks (large, slower, suburban). Capacity is usually measured in both weight and cubic volume — "
                "whichever binds first.\n"
                "2. **Time windows are critical**: Failed deliveries (customer not home) cost $15-30 per re-attempt. "
                "Most e-commerce promises 4-hour windows; tighter windows (2-hour) significantly increase cost.\n"
                "3. **Last-mile cost structure**: Typically 40-50% of total shipping cost is last-mile. "
                "Driver wages dominate over fuel. Expect $1.50-3.00 per stop in urban areas.\n"
                "4. **Fragile handling**: Usually means no stacking above the item and loading it last (delivering first). "
                "This is a loading constraint, not a separate vehicle requirement.\n"
                "5. **Depot return**: Vehicles almost always return to depot — this is a standard VRP assumption. "
                "The real question is whether multi-trip routes are allowed (return, reload, go out again)."
            ),
        )

        db.add_all([post1, post2, post3])
        db.flush()

        # 5. Auto-assign all 4 seed agents to the delivery routing problem with their roles
        for agent in agents:
            pa = ProblemAgent(
                id=str(uuid.uuid4()),
                problem_id=problem.id,
                agent_id=agent.id,
                role=agent.role,
            )
            db.add(pa)
        db.flush()

        # 6. Create additional sample problems (open status, no agents assigned)
        sample_problems = [
            {
                "title": "Warehouse Location for a Retail Chain",
                "description": (
                    "We are a retail chain planning to open 3 new regional warehouses to serve "
                    "50 store locations across the eastern United States. Each potential warehouse "
                    "site has different land costs, labor availability, and proximity to highways. "
                    "We want to minimize total logistics cost (warehouse operating cost + shipping "
                    "to stores) while ensuring every store can be served within 24 hours. Some stores "
                    "have higher demand and need to be closer to a warehouse. We have 8 candidate "
                    "sites under consideration. How should we choose the warehouse locations and "
                    "assign stores to warehouses?"
                ),
            },
            {
                "title": "University Course Scheduling",
                "description": (
                    "Our university department needs to schedule 40 courses across 15 classrooms "
                    "and 5 time slots per day for a 5-day week. Each course has a specific enrollment "
                    "size and room requirements (some need labs, projectors, or large lecture halls). "
                    "Professors have availability constraints and preferences — some can only teach "
                    "mornings, others prefer not to teach on Fridays. No professor should teach more "
                    "than 2 consecutive slots. We want to minimize scheduling conflicts and maximize "
                    "professor preference satisfaction. Some courses have prerequisites and should "
                    "not be scheduled at the same time."
                ),
            },
            {
                "title": "Investment Portfolio Optimization",
                "description": (
                    "An investment fund manager needs to allocate $10 million across 20 candidate "
                    "assets (stocks, bonds, and REITs). Each asset has an expected annual return "
                    "and a risk profile measured by historical volatility. The manager wants to "
                    "maximize expected return while keeping portfolio variance below a target "
                    "threshold. Constraints include: no single asset can exceed 15% of the portfolio, "
                    "at least 30% must be in bonds for stability, sector diversification rules "
                    "(no more than 25% in any one sector), and the portfolio must include at least "
                    "8 different assets. Transaction costs apply for each asset included."
                ),
            },
        ]

        for sp in sample_problems:
            p = Problem(
                id=str(uuid.uuid4()),
                title=sp["title"],
                description=sp["description"],
                status=ProblemStatus.open,
                created_by=user.id,
                is_template=True,
            )
            db.add(p)

        db.commit()

        print(f"\n  Example problem: \"{problem.title}\"")
        print(f"    Status: {problem.status.value}")
        print(f"    Posts: 3 round-1 posts from MathBot, DataScout, and LogiPro")
        print(f"    Assigned agents: {len(agents)}")
        print(f"\n  Sample problems: {len(sample_problems)} additional (open status)")
        for sp in sample_problems:
            print(f"    - {sp['title']}")
        print("\n" + "=" * 60 + "\n")

    finally:
        db.close()


def seed_formulations():
    db: Session = SessionLocal()
    try:
        if db.query(FormulationTemplate).first() is not None:
            return

        print("\n  Seeding formulation templates...")
        for tmpl in FORMULATION_TEMPLATES:
            db.add(FormulationTemplate(
                id=str(uuid.uuid4()),
                name=tmpl["name"],
                alias=tmpl["alias"],
                category=tmpl["category"],
                description=tmpl["description"],
                decision_variables=tmpl["decision_variables"],
                objective=tmpl["objective"],
                constraints=tmpl["constraints"],
                parameters=tmpl["parameters"],
                tags=tmpl["tags"],
                source=tmpl.get("source"),
            ))
        db.commit()
        print(f"  Seeded {len(FORMULATION_TEMPLATES)} formulation templates.\n")
    finally:
        db.close()


# --- App lifecycle ---

def _migrate_add_column(engine, table, column, col_type="VARCHAR"):
    """Add a column if it doesn't exist (simple SQLite migration)."""
    from sqlalchemy import text, inspect as sa_inspect
    insp = sa_inspect(engine)
    existing = [c["name"] for c in insp.get_columns(table)]
    if column not in existing:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        print(f"  Migration: added '{column}' to '{table}'")


def _backfill_templates(engine):
    """Mark demo user's problems as templates if they aren't already."""
    from sqlalchemy import text
    with engine.begin() as conn:
        result = conn.execute(text(
            "UPDATE problems SET is_template = TRUE "
            "WHERE created_by IN (SELECT id FROM users WHERE email = 'demo@optimum.app') "
            "AND (is_template IS NULL OR is_template = FALSE)"
        ))
        if result.rowcount > 0:
            print(f"  Migration: marked {result.rowcount} demo problems as templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate_add_column(engine, "agents", "model", "VARCHAR")
    _migrate_add_column(engine, "agents", "owner_id", "VARCHAR")
    _migrate_add_column(engine, "problem_agents", "role", "VARCHAR DEFAULT 'general'")
    _migrate_add_column(engine, "problems", "is_template", "BOOLEAN DEFAULT FALSE")
    _backfill_templates(engine)
    seed_database()
    seed_formulations()
    yield


# --- App ---

app = FastAPI(
    title="Optimum",
    description="Multi-agent optimization playground where AI agents collaboratively formalize real-world optimization problems.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — open to all origins for Lovable frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router.router)
app.include_router(agents_router.router)
app.include_router(problems_router.router)
app.include_router(posts_router.router)
app.include_router(formulations_router.router)
app.include_router(tools_router.router)


# --- Global exception handlers for consistent JSON ---

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": None,
            "error": exc.detail,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    messages = []
    for err in errors:
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        messages.append("{}: {}".format(loc, err.get("msg", "")))
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "data": None,
            "error": "; ".join(messages) if messages else "Validation error.",
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "error": "Internal server error.",
        },
    )


# --- Static pages ---

@app.get("/", include_in_schema=False)
def home():
    return FileResponse(os.path.join(BASE_DIR, "index.html"), media_type="text/html")


@app.get("/debug", include_in_schema=False)
def debug_console():
    return FileResponse(os.path.join(BASE_DIR, "debug.html"), media_type="text/html")


@app.get("/skill.md", include_in_schema=False)
def skill_file():
    return FileResponse(
        os.path.join(BASE_DIR, "SKILL.md"),
        media_type="text/plain; charset=utf-8",
    )


# --- Health ---

@app.get("/health", tags=["system"])
def health():
    db = SessionLocal()
    try:
        agent_count = db.query(Agent).count()
        problem_count = db.query(Problem).count()
    finally:
        db.close()

    return {
        "success": True,
        "data": {
            "status": "ok",
            "agent_count": agent_count,
            "problem_count": problem_count,
        },
        "error": None,
    }
