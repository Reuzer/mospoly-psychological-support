from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
import enum

from psychohelp.config.config import Base


class UniversityStatus(str, enum.Enum):
    STUDENT = "студент"
    POSTGRADUATE = "аспирант"
    TEACHER = "преподаватель"
    STAFF = "сотрудник"


class ApplicationStatus(str, enum.Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    AWAITING_USER_CONFIRMATION = "awaiting_user_confirmation"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class CancelInitiator(str, enum.Enum):
    USER = "user"
    PSYCHOLOGIST = "psychologist"
    MANAGER = "manager"
    SYSTEM = "system"


class MeetingType(str, enum.Enum):
    OFFLINE = "offline"
    ONLINE = "online"


class Application(Base):
    __tablename__ = "applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    problem_description = Column(Text, nullable=False)
    preferred_campus = Column(String(128), nullable=True)
    university_status = Column(String(50), nullable=False)

    status = Column(String(50), default=ApplicationStatus.NEW.value, nullable=False, index=True)
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    psychologist_id = Column(UUID(as_uuid=True), ForeignKey("psychologists.id", ondelete="SET NULL"), nullable=True)
    meeting_type = Column(String(20), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    location_address = Column(Text, nullable=True)
    meeting_url = Column(String(512), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    processing_started_at = Column(DateTime(timezone=True), nullable=True)
    confirmation_requested_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    expired_at = Column(DateTime(timezone=True), nullable=True)

    reject_reason = Column(Text, nullable=True)
    cancel_reason = Column(Text, nullable=True)
    cancel_initiator = Column(String(20), nullable=True)
    internal_comment = Column(Text, nullable=True)

    appointment_id = Column(UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True)

    version = Column(Integer, default=1, nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    assigned_to_user = relationship("User", foreign_keys=[assigned_to])
    psychologist = relationship("Psychologist", foreign_keys=[psychologist_id])
    appointment = relationship(
        "Appointment",
        foreign_keys=[appointment_id],
        overlaps="application",
    )