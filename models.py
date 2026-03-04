import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    Integer,
    Text,
    Enum,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import relationship

from database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentRole(str, enum.Enum):
    general = "general"
    clarifier = "clarifier"
    formulator = "formulator"
    critic = "critic"
    domain_expert = "domain_expert"


class ProblemStatus(str, enum.Enum):
    open = "open"
    round1 = "round1"
    round2 = "round2"
    round3 = "round3"
    review = "review"
    closed = "closed"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    confirmation_token = Column(String, nullable=True)
    confirmed = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

    problems = relationship("Problem", back_populates="creator")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    role = Column(Enum(AgentRole), default=AgentRole.general, nullable=False)
    model = Column(String, nullable=True)
    api_key_hash = Column(String, nullable=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=True)
    registered_at = Column(DateTime, default=utcnow)
    last_active = Column(DateTime, default=utcnow)

    posts = relationship("Post", back_populates="agent")
    owner = relationship("User")


class Problem(Base):
    __tablename__ = "problems"

    id = Column(String, primary_key=True, default=generate_uuid)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(Enum(ProblemStatus), default=ProblemStatus.open, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    human_feedback = Column(Text, nullable=True)

    creator = relationship("User", back_populates="problems")
    posts = relationship("Post", back_populates="problem", cascade="all, delete-orphan")
    assigned_agents = relationship("ProblemAgent", back_populates="problem", cascade="all, delete-orphan")


class ProblemAgent(Base):
    __tablename__ = "problem_agents"

    id = Column(String, primary_key=True, default=generate_uuid)
    problem_id = Column(String, ForeignKey("problems.id"), nullable=False)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False)
    role = Column(Enum(AgentRole), nullable=False)
    assigned_at = Column(DateTime, default=utcnow)

    problem = relationship("Problem", back_populates="assigned_agents")
    agent = relationship("Agent")


class Post(Base):
    __tablename__ = "posts"

    id = Column(String, primary_key=True, default=generate_uuid)
    problem_id = Column(String, ForeignKey("problems.id"), nullable=False)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False)
    round = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    reply_to = Column(String, nullable=True)
    system_generated = Column(Boolean, default=False)

    problem = relationship("Problem", back_populates="posts")
    agent = relationship("Agent", back_populates="posts")


class FormulationTemplate(Base):
    __tablename__ = "formulation_templates"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    alias = Column(String, nullable=False)
    category = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    decision_variables = Column(JSON, nullable=False)
    objective = Column(JSON, nullable=False)
    constraints = Column(JSON, nullable=False)
    parameters = Column(JSON, nullable=False)
    tags = Column(JSON, nullable=False)
    source = Column(String, nullable=True)
