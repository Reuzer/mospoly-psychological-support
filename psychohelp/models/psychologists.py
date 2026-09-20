from psychohelp.config.config import Base
from psychohelp.models.psychologist_statuses import PsychologistStatus 

from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

import uuid


class Psychologist(Base):
    __tablename__ = "psychologists"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    experience = Column(String(64), nullable=False)
    qualification = Column(String(128), nullable=False)
    consult_areas = Column(String(128), nullable=False)
    description = Column(String(256), nullable=False)
    office = Column(String(128), nullable=False)
    education = Column(String(127), nullable=False)
    short_description = Column(String(2047), nullable=False)
    photo = Column(String(127), nullable=True)

    user = relationship("User", back_populates="psychologist_info")
    appointments = relationship("Appointment", back_populates="psychologist")
    statuses = relationship("PsychologistStatus", back_populates="psychologist")
