import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database import get_db
from models import User, Agent, Problem, Post, ProblemAgent, ProblemStatus
from auth import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


# --- Schemas ---

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# --- Routes ---

@router.post("/register")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with email '{body.email}' already exists.",
        )
    if len(body.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 6 characters.",
        )

    confirmation_token = str(uuid.uuid4())
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        confirmation_token=confirmation_token,
        confirmed=True,  # auto-confirm for now
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "success": True,
        "data": {
            "user_id": user.id,
            "email": user.email,
            "confirmed": user.confirmed,
            "message": "Account created and auto-confirmed. Email confirmation will be required in a future update.",
        },
        "error": None,
    }


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not user.confirmed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account not confirmed. Check your email for a confirmation link.",
        )
    # Clone template problems for first-time users
    _clone_templates_if_needed(user, db)
    # Ensure user's own agents are assigned to all their problems
    _assign_user_agents(user, db)

    token = create_access_token(user.id)
    return {
        "success": True,
        "data": {
            "access_token": token,
            "token_type": "bearer",
        },
        "error": None,
    }


def _assign_user_agents(user: User, db: Session):
    """Ensure the user's own agents are assigned to all their problems."""
    user_agents = db.query(Agent).filter(Agent.owner_id == user.id).all()
    if not user_agents:
        return
    user_problems = db.query(Problem).filter(
        Problem.created_by == user.id, Problem.is_template == False
    ).all()
    changed = False
    for problem in user_problems:
        existing = db.query(ProblemAgent).filter(ProblemAgent.problem_id == problem.id).all()
        existing_agent_ids = {pa.agent_id for pa in existing}
        for agent in user_agents:
            if agent.id not in existing_agent_ids:
                # Swap out any seed agent holding this role slot
                occupant = next((pa for pa in existing if pa.role == agent.role), None)
                if occupant:
                    db.delete(occupant)
                    existing = [pa for pa in existing if pa.id != occupant.id]
                db.add(ProblemAgent(
                    id=str(uuid.uuid4()),
                    problem_id=problem.id,
                    agent_id=agent.id,
                    role=agent.role,
                ))
                changed = True
    if changed:
        db.commit()


def _clone_templates_if_needed(user: User, db: Session):
    """Clone all template problems for a user who doesn't have any yet."""
    # Skip for demo user (they own the templates)
    if user.email == "demo@optimum.app":
        return

    # Check if user already has problems (cloned or created)
    user_problem_count = db.query(Problem).filter(
        Problem.created_by == user.id, Problem.is_template == False
    ).count()
    if user_problem_count > 0:
        return  # already has problems, skip

    # Get all template problems
    templates = db.query(Problem).filter(Problem.is_template == True).all()
    if not templates:
        return

    for template in templates:
        # Clone the problem
        new_problem = Problem(
            id=str(uuid.uuid4()),
            title=template.title,
            description=template.description,
            status=ProblemStatus.open,
            created_by=user.id,
            is_template=False,
        )
        db.add(new_problem)
        db.flush()

        # Clone posts (e.g., seed round-1 posts on the delivery problem)
        template_posts = (
            db.query(Post)
            .filter(Post.problem_id == template.id)
            .order_by(Post.round, Post.created_at)
            .all()
        )
        old_to_new_post_id = {}
        for post in template_posts:
            new_post_id = str(uuid.uuid4())
            old_to_new_post_id[post.id] = new_post_id
            new_post = Post(
                id=new_post_id,
                problem_id=new_problem.id,
                agent_id=post.agent_id,
                round=post.round,
                content=post.content,
                reply_to=old_to_new_post_id.get(post.reply_to) if post.reply_to else None,
                system_generated=post.system_generated,
            )
            db.add(new_post)

        # Clone agent assignments
        template_agents = (
            db.query(ProblemAgent)
            .filter(ProblemAgent.problem_id == template.id)
            .all()
        )
        for pa in template_agents:
            new_pa = ProblemAgent(
                id=str(uuid.uuid4()),
                problem_id=new_problem.id,
                agent_id=pa.agent_id,
                role=pa.role,
            )
            db.add(new_pa)

        # Also assign user's own agent(s), swapping out seed agents in same role
        user_agents = db.query(Agent).filter(Agent.owner_id == user.id).all()
        assigned_ids = {pa.agent_id for pa in template_agents}
        cloned_assignments = (
            db.query(ProblemAgent)
            .filter(ProblemAgent.problem_id == new_problem.id)
            .all()
        )
        for agent in user_agents:
            if agent.id not in assigned_ids:
                occupant = next((pa for pa in cloned_assignments if pa.role == agent.role), None)
                if occupant:
                    db.delete(occupant)
                    cloned_assignments = [pa for pa in cloned_assignments if pa.id != occupant.id]
                db.add(ProblemAgent(
                    id=str(uuid.uuid4()),
                    problem_id=new_problem.id,
                    agent_id=agent.id,
                    role=agent.role,
                ))

    db.commit()


@router.get("/confirm/{token}")
def confirm_email(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.confirmation_token == token).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid confirmation token.",
        )
    user.confirmed = True
    db.commit()
    return {
        "success": True,
        "data": {"message": "Account confirmed successfully."},
        "error": None,
    }
