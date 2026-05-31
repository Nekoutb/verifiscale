"""Admin-only user management endpoints.

GET /users — list all users (with contact info, for prospection follow-up)
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import UserOut
from app.security import require_role


router = APIRouter(prefix="/users", tags=["admin"])


@router.get("", response_model=list[UserOut])
def list_users(
    db: Annotated[Session, Depends(get_db)],
    _admin: Annotated[User, Depends(require_role("ADMIN"))],
):
    """Return all users — admin only. Used for prospection / contact follow-up."""
    return (
        db.query(User)
        .order_by(User.last_login_at.desc().nullslast(), User.created_at.desc())
        .all()
    )
