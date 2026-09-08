import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import AUTH_COOKIE_NAME, get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.models.user import User, UserStatus
from app.schemas.auth import CurrentUserResponse, LoginRequest, TokenResponse
from app.services.audit import write_audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# In-memory IP-based login rate limiter
# ---------------------------------------------------------------------------
# Stores {ip: (attempt_count, window_start_time)}.
# Resets automatically on application restart (intentional – no persistence).
# ---------------------------------------------------------------------------

_login_attempts: dict[str, tuple[int, float]] = {}


def _get_client_ip(request: Request) -> str:
    """Extract the real client IP, respecting X-Forwarded-For behind a proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(ip: str) -> None:
    """Raise HTTP 429 if *ip* exceeded the allowed login attempts."""
    settings = get_settings()
    max_attempts = settings.login_ip_rate_limit_max_attempts
    window = settings.login_ip_rate_limit_window_seconds
    now = time.monotonic()

    count, window_start = _login_attempts.get(ip, (0, now))

    # Window expired – reset.
    if now - window_start >= window:
        count, window_start = 0, now

    if count >= max_attempts:
        logger.warning("Login rate limit exceeded for IP %s (%d attempts in %ds)", ip, count, window)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )

    _login_attempts[ip] = (count + 1, window_start)


def _clear_rate_limit(ip: str) -> None:
    """Remove the rate-limit counter for *ip* (called after successful login)."""
    _login_attempts.pop(ip, None)


def _reset_rate_limiter_state() -> None:
    """Clear all rate-limit entries. Useful for testing."""
    _login_attempts.clear()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def set_auth_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
        path="/",
    )


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    client_ip = _get_client_ip(request)

    # Rate-limit check – runs before any credential verification.
    _check_rate_limit(client_ip)

    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or user.status != UserStatus.ACTIVE or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    # Successful login – clear the IP counter.
    _clear_rate_limit(client_ip)

    write_audit(db, actor=user, action="login", target_type="user", target_id=user.id)
    db.commit()
    token = create_access_token(str(user.id), user.auth_version)
    # Browsers authenticate with the HttpOnly cookie; the body token remains
    # for API scripts and the transition period.
    set_auth_cookie(response, token)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=CurrentUserResponse)
def me(user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(id=user.id, username=user.username, display_name=user.display_name, role=user.role.value)


@router.post("/logout")
def logout(response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    user.auth_version += 1
    write_audit(db, actor=user, action="logout", target_type="user", target_id=user.id)
    db.commit()
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")
    return {"ok": True}
