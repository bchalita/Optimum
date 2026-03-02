from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Problem, Post, ProblemStatus, User
from auth import get_current_user

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


@router.get("")
def list_problems(db: Session = Depends(get_db)):
    problems = db.query(Problem).order_by(Problem.created_at.desc()).all()
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
