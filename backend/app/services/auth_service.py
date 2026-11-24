from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import RegisterRequest, TokenResponse, UserOut


def register_user(db: Session, payload: RegisterRequest) -> User:
    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    if payload.nexconn_user_id and db.scalar(
        select(User).where(User.nexconn_user_id == payload.nexconn_user_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Nexconn user id already linked"
        )

    user = User(
        name=payload.name.strip(),
        email=payload.email,
        password_hash=hash_password(payload.password),
        nexconn_user_id=payload.nexconn_user_id,
    )
    db.add(user)
    db.flush()
    if not user.nexconn_user_id:
        # Stable local Nexconn identity so inbound webhook messages can be mapped.
        user.nexconn_user_id = f"nz{user.id:06d}"
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    return user


def token_for_user(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id),
        user=UserOut.model_validate(user),
    )
