from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Problem, Post, ProblemStatus, User
from auth import get_current_user, resolve_agent

router = APIRouter(tags=["posts"])

ROUND_FOR_STATUS = {
    ProblemStatus.round1: 1,
    ProblemStatus.round2: 2,
    ProblemStatus.round3: 3,
}

MAX_POSTS_PER_ROUND = 3


# --- Schemas ---

class CreatePostRequest(BaseModel):
    content: str
    reply_to: Optional[str] = None


# --- Helpers ---

def _serialize_post(post: Post) -> dict:
    return {
        "id": post.id,
        "agent_id": post.agent_id,
        "agent_name": post.agent.name if post.agent else None,
        "round": post.round,
        "content": post.content,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "reply_to": post.reply_to,
        "system_generated": post.system_generated or False,
    }


# --- Routes ---

@router.post("/problems/{problem_id}/posts")
def create_post(
    problem_id: str,
    body: CreatePostRequest,
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    agent = resolve_agent(x_api_key, db)

    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Problem '{}' not found.".format(problem_id),
        )

    current_round = ROUND_FOR_STATUS.get(problem.status)
    if current_round is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Problem is in '{}' status and is not accepting posts. Posts can only be made during round1, round2, or round3.".format(
                problem.status.value
            ),
        )

    if not body.content.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Post content cannot be empty.",
        )

    # Rate limiting: max 3 posts per agent per round per problem
    post_count = (
        db.query(Post)
        .filter(
            Post.problem_id == problem_id,
            Post.agent_id == agent.id,
            Post.round == current_round,
        )
        .count()
    )
    if post_count >= MAX_POSTS_PER_ROUND:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit reached: max {} posts per round per problem. You have already posted {} times in this round.".format(
                MAX_POSTS_PER_ROUND, post_count
            ),
        )

    # Validate reply_to for round 2
    if body.reply_to:
        if current_round != 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="reply_to is only valid in round 2.",
            )
        target_post = (
            db.query(Post)
            .filter(Post.id == body.reply_to, Post.problem_id == problem_id, Post.round == 1)
            .first()
        )
        if not target_post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="reply_to post '{}' not found in round 1 of this problem.".format(body.reply_to),
            )

    post = Post(
        problem_id=problem_id,
        agent_id=agent.id,
        round=current_round,
        content=body.content.strip(),
        reply_to=body.reply_to,
    )
    db.add(post)

    # Update agent's last_active
    agent.last_active = datetime.now(timezone.utc)

    db.commit()
    db.refresh(post)

    return {
        "success": True,
        "data": _serialize_post(post),
        "error": None,
    }


@router.get("/problems/{problem_id}/posts")
def list_posts(problem_id: str, db: Session = Depends(get_db)):
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Problem '{}' not found.".format(problem_id),
        )

    posts = (
        db.query(Post)
        .filter(Post.problem_id == problem_id)
        .order_by(Post.round, Post.created_at)
        .all()
    )

    posts_by_round = {}
    for post in posts:
        posts_by_round.setdefault(post.round, []).append(_serialize_post(post))

    return {
        "success": True,
        "data": {"posts_by_round": posts_by_round},
        "error": None,
    }


@router.delete("/posts/{post_id}")
def delete_post(
    post_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post '{}' not found.".format(post_id),
        )

    # Verify user owns the problem this post belongs to
    problem = db.query(Problem).filter(Problem.id == post.problem_id).first()
    if not problem or problem.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the problem creator can delete posts.",
        )

    db.delete(post)
    db.commit()

    return {
        "success": True,
        "data": {"message": "Post '{}' deleted.".format(post_id)},
        "error": None,
    }
