import hmac
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password_or_dummy,
)
from app.database.session import get_db
from app.models.models import Role, User, UserLogin
from app.schemas.contracts import LoginRequest, RegisterRequest, TokenResponse, UserOut

logger = logging.getLogger("verba.auth")

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=TokenResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if payload.role == Role.ADMIN:
        # Anyone can pick "admin" in a form, so admin accounts need a server-side secret.
        # If ADMIN_INVITE_CODE isn't configured, admin self-registration is off entirely.
        expected = settings.admin_invite_code
        supplied = payload.admin_invite_code or ""
        if not expected or not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A valid admin invite code is required")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # two simultaneous sign-ups with the same email
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    db.refresh(user)
    token = create_access_token(user_id=user.id, role=user.role.value)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not verify_password_or_dummy(payload.password, user.password_hash if user else None):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")
    token = create_access_token(user_id=user.id, role=user.role.value)
    _record_login(db, user.id)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


def _record_login(db: Session, user_id: int) -> None:
    """Record exactly one successful sign-in. Best-effort: a logging failure must never
    break a successful login. Used by the admin login-activity statistics only — this is
    never incremented by ordinary API requests, just by a successful /auth/login."""
    from app.services.activity_service import today_local

    try:
        db.add(UserLogin(user_id=user_id, login_at=datetime.utcnow(), login_date=today_local()))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not record login for user %s", user_id)


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    """The signed-in user (id, email, full_name, role). Also how the frontend validates a stored token."""
    return user
