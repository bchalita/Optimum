from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Agent, AgentRole, User, Post
from auth import generate_api_key, hash_api_key, get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


# --- Schemas ---

class RegisterAgentRequest(BaseModel):
    name: str
    description: str = ""
    role: str = "general"
    model: str = ""


class UpdateRoleRequest(BaseModel):
    role: str


# --- Routes ---

@router.post("/register")
def register_agent(body: RegisterAgentRequest, db: Session = Depends(get_db)):
    if not body.name or not body.name.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Agent name is required.",
        )

    # Validate role
    role_value = body.role.strip().lower()
    valid_roles = [r.value for r in AgentRole]
    if role_value not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid role '{}'. Must be one of: {}".format(role_value, ", ".join(valid_roles)),
        )

    raw_key = generate_api_key()
    agent = Agent(
        name=body.name.strip(),
        description=body.description.strip(),
        role=AgentRole(role_value),
        model=body.model.strip() if body.model else None,
        api_key_hash=hash_api_key(raw_key),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    return {
        "success": True,
        "data": {
            "agent_id": agent.id,
            "name": agent.name,
            "role": agent.role.value,
            "model": agent.model or "",
            "api_key": raw_key,
            "message": "Save this key — it will not be shown again.",
        },
        "error": None,
    }


@router.get("")
def list_agents(db: Session = Depends(get_db)):
    agents = db.query(Agent).order_by(Agent.registered_at.desc()).all()
    return {
        "success": True,
        "data": [
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "role": a.role.value if a.role else "general",
                "model": a.model or "",
                "registered_at": a.registered_at.isoformat() if a.registered_at else None,
                "last_active": a.last_active.isoformat() if a.last_active else None,
            }
            for a in agents
        ],
        "error": None,
    }


@router.get("/{agent_id}")
def get_agent(agent_id: str, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found.",
        )
    return {
        "success": True,
        "data": {
            "id": agent.id,
            "name": agent.name,
            "description": agent.description,
            "role": agent.role.value if agent.role else "general",
            "model": agent.model or "",
            "registered_at": agent.registered_at.isoformat() if agent.registered_at else None,
            "last_active": agent.last_active.isoformat() if agent.last_active else None,
        },
        "error": None,
    }


@router.patch("/{agent_id}/role")
def update_agent_role(
    agent_id: str,
    body: UpdateRoleRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent '{}' not found.".format(agent_id),
        )

    role_value = body.role.strip().lower()
    valid_roles = [r.value for r in AgentRole]
    if role_value not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid role '{}'. Must be one of: {}".format(role_value, ", ".join(valid_roles)),
        )

    agent.role = AgentRole(role_value)
    db.commit()
    db.refresh(agent)

    return {
        "success": True,
        "data": {
            "id": agent.id,
            "name": agent.name,
            "role": agent.role.value,
            "message": "Role updated to '{}'.".format(agent.role.value),
        },
        "error": None,
    }


@router.delete("/{agent_id}")
def delete_agent(
    agent_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove an agent from the platform. Operator only (authenticated user)."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found.",
        )
    db.query(Post).filter(Post.agent_id == agent_id).delete()
    db.delete(agent)
    db.commit()
    return {
        "success": True,
        "data": {"message": f"Agent '{agent.name}' removed."},
        "error": None,
    }
