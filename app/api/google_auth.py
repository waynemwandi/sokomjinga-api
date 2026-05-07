# app/api/google_auth.py

from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.db.models import User, UserProfile, log_auth_event

router = APIRouter(prefix="/auth/google", tags=["auth"])


@router.get("/start", include_in_schema=False)
async def google_start():
    s = get_settings()
    params = {
        "client_id": s.GOOGLE_CLIENT_ID,
        "redirect_uri": s.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",  # ensures refresh_token on first grant
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(url, status_code=302)


@router.get("/callback", include_in_schema=False)
async def google_callback(code: str | None = None, error: str | None = None):
    s = get_settings()
    if error:  # user closed/denied consent
        return RedirectResponse(
            f"{s.BASE_FRONTEND_URL}/login?err=google_denied", status_code=302
        )
    # normal path
    return RedirectResponse(
        f"{s.BASE_FRONTEND_URL}/login/oauth?code={code}", status_code=302
    )


@router.get("/exchange")
async def google_exchange(code: str, db: Session = Depends(get_db)):
    s = get_settings()
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": s.GOOGLE_CLIENT_ID,
        "client_secret": s.GOOGLE_CLIENT_SECRET,
        "redirect_uri": s.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient(timeout=20) as client:
        tok = await client.post(token_url, data=data)
    if tok.status_code != 200:
        return JSONResponse(
            status_code=tok.status_code,
            content={"error": "token_exchange_failed", "detail": tok.text},
        )

    payload = tok.json()
    id_jwt = payload.get("id_token")
    if not id_jwt:
        return JSONResponse(status_code=400, content={"error": "missing_id_token"})

    # Verify Google ID token against your client_id
    req = google_requests.Request()
    idinfo = google_id_token.verify_oauth2_token(id_jwt, req, s.GOOGLE_CLIENT_ID)
    email = idinfo.get("email")
    name = idinfo.get("name") or email.split("@")[0]
    sub = idinfo.get("sub")  # Google's user id

    if not email:
        return JSONResponse(status_code=400, content={"error": "no_email_from_google"})

    # --- Upsert user (prefer google_sub, then email) ---
    picture = idinfo.get("picture")  # may be None

    # 1. Try find profile by google_sub
    prof = db.query(UserProfile).filter(UserProfile.google_sub == sub).one_or_none()

    if prof:
        user = db.query(User).filter(User.id == prof.user_id).one()
    else:
        # 2. Fallback by email
        user = db.query(User).filter(User.email == email).one_or_none()

    if not user:
        # New account
        user = User(
            email=email,
            password_hash=hash_password(sub),  # placeholder; Google-only sign-in
            name=name,
        )
        db.add(user)
        db.flush()  # get user.id

        prof = UserProfile(user_id=user.id)
        db.add(prof)
    else:
        # Ensure profile exists
        prof = db.query(UserProfile).filter(
            UserProfile.user_id == user.id
        ).one_or_none() or UserProfile(user_id=user.id)
        db.add(prof)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive"
        )

    # Mark Google provenance
    prof.auth_provider = "google"
    prof.google_sub = sub
    if picture:
        prof.avatar_url = picture

    log_auth_event(db, user.id, "login", "google")
    db.commit()

    db.refresh(user)

    # Issue your app's access + refresh JWT
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
    }
