import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from psychohelp.config.config import Base


class PsychologistStatusType(enum.Enum):
    vacation = "vacation"
    sick = "sick"


class PsychologistStatus(Base):
    __tablename__ = "psychologist_statuses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pid = Column(UUID(as_uuid=True), 
                ForeignKey("psychologists.user_id", ondelete="CASCADE"),
                nullable=False, 
                index=True
    )
    status = Column(
        Enum(PsychologistStatusType, name="psychologist_status_enum"),
        nullable=False,
    )
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)

    psychologist = relationship("Psychologist", back_populates="statuses")