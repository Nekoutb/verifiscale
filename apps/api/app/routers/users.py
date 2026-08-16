"""User management endpoints (admin d'organisation).

GET /users — membres de MON organisation uniquement (le superadmin plateforme
voit tout). Un admin client ne doit JAMAIS voir les comptes des autres clients.
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
    admin: Annotated[User, Depends(require_role("ADMIN"))],
):
    q = db.query(User)
    if not getattr(admin, "is_superadmin", False):
        q = q.filter(User.organization_id == admin.organization_id)
    return (
        q.order_by(User.last_login_at.desc().nullslast(), User.created_at.desc())
        .all()
    )
