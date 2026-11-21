from psychohelp.config.config import Base

from sqlalchemy import CheckConstraint, Column, Integer, String, Text, text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

import uuid


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("note_version >= 0", name="ck_users_note_version_nonnegative"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    first_name = Column(String(50), nullable=False)
    middle_name = Column(String(50), nullable=True)
    last_name = Column(String(50), nullable=False)
    phone_number = Column(String(20), nullable=False)
    email = Column(String(64), unique=True, nullable=False)
    social_media = Column(String(50), nullable=True)
    password = Column(String(64), nullable=False)
    study_group = Column(String(50), nullable=True)
    avatar = Column(String(100), nullable=True)
    # Общая заметка психологов не включается в схемы профиля пользователя.
    note = Column(Text, nullable=True, comment="Общая заметка психологов о пациенте")
    note_version = Column(
        Integer, nullable=False, default=0, server_default=text("0"),
        comment="Версия общей заметки психологов",
    )

    roles = relationship("Role", secondary="users_roles", back_populates="users")
    appointments_as_patient = relationship(
        "Appointment", foreign_keys="[Appointment.patient_id]", back_populates="patient"
    )
    psychologist_info = relationship("Psychologist", back_populates="user", uselist=False)
