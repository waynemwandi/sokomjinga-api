# app/api/profile.py
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import models
from app.db.session import get_db

router = APIRouter(prefix="/profile", tags=["profile"])

E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")  # ITU E.164: max 15 digits after '+'
USERNAME_RE = re.compile(r"^[a-z0-9_]{3,24}$")


class ProfileOut(BaseModel):
    user_id: str
    phone_e164: str | None
    phone_verified: bool
    username: str | None = None
    avatar_url: str | None = None
    bio: str | None = None


class PhoneIn(BaseModel):
    phone_e164: str


class ProfileIn(BaseModel):
    username: str | None = None
    phone_e164: str | None = None
    bio: str | None = None


def _profile_out(prof: models.UserProfile) -> ProfileOut:
    return ProfileOut(
        user_id=prof.user_id,
        phone_e164=prof.phone_e164,
        phone_verified=bool(prof.phone_verified_at),
        username=prof.username,
        avatar_url=prof.avatar_url,
        bio=prof.bio,
    )


@router.get("/me", response_model=ProfileOut)
def get_profile(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prof = db.get(models.UserProfile, current_user.id)
    if not prof:
        prof = models.UserProfile(user_id=current_user.id)
        db.add(prof)
        db.commit()
        db.refresh(prof)
    return _profile_out(prof)


@router.put("/phone", response_model=ProfileOut)
def set_phone(
    body: PhoneIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    phone = body.phone_e164.strip()
    if not E164_RE.match(phone):
        raise HTTPException(
            status_code=400, detail="Phone must be E.164 (e.g., +2547XXXXXXXX)"
        )

    # Ensure not taken by someone else
    existing = (
        db.query(models.UserProfile)
        .filter(
            models.UserProfile.phone_e164 == phone,
            models.UserProfile.user_id != current_user.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Phone already in use")

    prof = db.get(models.UserProfile, current_user.id)
    if not prof:
        prof = models.UserProfile(user_id=current_user.id)
        db.add(prof)

    prof.phone_e164 = phone
    prof.phone_verified_at = None  # reset verification
    db.commit()
    db.refresh(prof)
    return _profile_out(prof)


@router.put("/me", response_model=ProfileOut)
def update_profile(
    body: ProfileIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prof = db.get(models.UserProfile, current_user.id)
    if not prof:
        prof = models.UserProfile(user_id=current_user.id)
        db.add(prof)

    if body.username is not None:
        username = body.username.strip().lower().lstrip("@")
        if not USERNAME_RE.match(username):
            raise HTTPException(
                status_code=400,
                detail="Username must be 3-24 characters using letters, numbers, or underscore",
            )

        existing = (
            db.query(models.UserProfile)
            .filter(
                models.UserProfile.username == username,
                models.UserProfile.user_id != current_user.id,
            )
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Username already in use")

        prof.username = username

    if body.phone_e164 is not None:
        phone = body.phone_e164.strip()
        if not E164_RE.match(phone):
            raise HTTPException(
                status_code=400, detail="Phone must be E.164 (e.g., +2547XXXXXXXX)"
            )

        existing = (
            db.query(models.UserProfile)
            .filter(
                models.UserProfile.phone_e164 == phone,
                models.UserProfile.user_id != current_user.id,
            )
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Phone already in use")

        if prof.phone_e164 != phone:
            prof.phone_e164 = phone
            prof.phone_verified_at = None

    if body.bio is not None:
        bio = body.bio.strip()
        if len(bio) > 280:
            raise HTTPException(
                status_code=400, detail="Public profile must be 280 characters or less"
            )
        prof.bio = bio or None

    db.commit()
    db.refresh(prof)
    return _profile_out(prof)
