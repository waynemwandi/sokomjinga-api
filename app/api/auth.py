# app/api/auth.py
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, constr
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db import models
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


# ---- Schemas
class SignupIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )  # Prevent extra fields in input during signup
    email: EmailStr
    password: constr(min_length=8)
    name: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str | None = None


class UserOut(BaseModel):
    id: str
    email: EmailStr
    name: str | None = None
    created_at: datetime
    is_admin: bool


class RefreshIn(BaseModel):
    refresh_token: str


# ---- Endpoints
@router.post("/signup", response_model=UserOut, status_code=201)
def signup(payload: SignupIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = models.User(
        **{
            "email": email,
            "password_hash": hash_password(payload.password),
            "name": payload.name,
        }
    )
    db.add(user)
    db.flush()  # get user.id without finishing the txn
    models.log_auth_event(db, user.id, "signup", "password")

    # ensure a profile exists and mark provider
    if not db.query(models.UserProfile).filter_by(user_id=user.id).first():
        db.add(models.UserProfile(user_id=user.id, auth_provider="password"))

    db.commit()
    db.refresh(user)
    return UserOut(
        id=user.id, email=user.email, name=user.name, created_at=user.created_at
    )


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    # `user.id` is str (not Optional), so no type error now
    models.log_auth_event(db, user.id, "login", "password")
    db.commit()

    return TokenOut(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", response_model=UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return UserOut(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        created_at=current_user.created_at,
        is_admin=current_user.is_admin,
    )


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn):
    data = decode_token(body.refresh_token)
    if not data or data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return TokenOut(access_token=create_access_token(data["sub"]))
