import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import MembershipRecord, SessionRecord, UserRecord, WorkspaceRecord, get_db


bearer = HTTPBearer(auto_error=False)
PBKDF2_ROUNDS = 210_000


@dataclass(frozen=True)
class AuthContext:
    user: UserRecord
    workspace: WorkspaceRecord
    role: str
    session: SessionRecord


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, expected_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(digest.hex(), expected_hex)
    except (TypeError, ValueError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user_id: str) -> tuple[SessionRecord, str]:
    token = secrets.token_urlsafe(40)
    session = SessionRecord(
        user_id=user_id,
        token_hash=token_hash(token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(session)
    db.flush()
    return session, token


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> AuthContext:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "请先登录", headers={"WWW-Authenticate": "Bearer"})
    session = db.scalar(select(SessionRecord).where(SessionRecord.token_hash == token_hash(credentials.credentials)))
    now = datetime.now(timezone.utc)
    if not session or session.revoked_at or session.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(401, "登录已失效", headers={"WWW-Authenticate": "Bearer"})
    user = db.get(UserRecord, session.user_id)
    membership = db.scalar(select(MembershipRecord).where(MembershipRecord.user_id == session.user_id))
    workspace = db.get(WorkspaceRecord, membership.workspace_id) if membership else None
    if not user or not user.is_active or not membership or not workspace:
        raise HTTPException(403, "账号或工作区不可用")
    return AuthContext(user=user, workspace=workspace, role=membership.role, session=session)
