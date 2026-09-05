"""Shared FastAPI dependencies: current user, role guard, rate limit."""

from __future__ import annotations

import time
from collections import defaultdict, deque

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mastery.common.security import decode_access_token
from mastery.db.base import User
from mastery.db.session import get_db

bearer = HTTPBearer(auto_error=True)

_RATE_LIMIT = 120  # requests
_RATE_WINDOW = 60  # seconds
_hits: dict[str, deque[float]] = defaultdict(deque)


async def rate_limit(request: Request) -> None:
    """Fixed-window limiter keyed by client IP.

    In-process on purpose: it is a safety net for a single-instance deployment. Move the
    counter into Redis before running more than one replica.
    """
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = _hits[ip]
    while window and window[0] < now - _RATE_WINDOW:
        window.popleft()
    if len(window) >= _RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded"
        )
    window.append(now)


async def current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_access_token(creds.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def require_instructor(user: User = Depends(current_user)) -> User:
    if user.role != "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Instructor role required"
        )
    return user
