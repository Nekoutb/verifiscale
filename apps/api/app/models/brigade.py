"""Brigade = unit of DGI auditors (e.g. DGE, CIME Yaoundé, CDI Douala)."""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.audit_case import AuditCase


class Brigade(Base):
    __tablename__ = "brigades"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)

    users: Mapped[list["User"]] = relationship(back_populates="brigade")
    audit_cases: Mapped[list["AuditCase"]] = relationship(back_populates="brigade")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
