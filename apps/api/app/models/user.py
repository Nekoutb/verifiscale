"""Auditor / supervisor accounts."""
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, Boolean, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.brigade import Brigade
    from app.models.audit_case import AuditCase


class UserRole(str, enum.Enum):
    AUDITEUR = "AUDITEUR"
    SUPERVISEUR = "SUPERVISEUR"
    CHEF_BRIGADE = "CHEF_BRIGADE"
    ADMIN = "ADMIN"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False, default=UserRole.AUDITEUR)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Prospection / contact info — captured at first login or set by admin
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    brigade_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brigades.id", ondelete="SET NULL"), nullable=True
    )
    brigade: Mapped["Brigade | None"] = relationship(back_populates="users")

    audit_cases: Mapped[list["AuditCase"]] = relationship(
        back_populates="assignee", foreign_keys="AuditCase.assignee_id"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
