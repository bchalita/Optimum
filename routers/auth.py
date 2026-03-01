import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database import get_db
from models import User
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
    token = create_access_token(user.id)
    return {
        "success": True,
        "data": {
            "access_token": token,
            "token_type": "bearer",
        },
        "error": None,
    }


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
