from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Agent
from auth import generate_api_key, hash_api_key

router = APIRouter(prefix="/agents", tags=["agents"])


# --- Schemas ---

class RegisterAgentRequest(BaseModel):
    name: str
    description: str = ""


# --- Routes ---

@router.post("/register")
def register_agent(body: RegisterAgentRequest, db: Session = Depends(get_db)):
    if not body.name or not body.name.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Agent name is required.",
        )

    raw_key = generate_api_key()
    agent = Agent(
        name=body.name.strip(),
        description=body.description.strip(),
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
            "registered_at": agent.registered_at.isoformat() if agent.registered_at else None,
            "last_active": agent.last_active.isoformat() if agent.last_active else None,
        },
        "error": None,
    }
