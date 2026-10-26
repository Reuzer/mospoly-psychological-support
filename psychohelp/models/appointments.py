from psychohelp.config.config import Base

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

import enum
import uuid


class AppointmentType(enum.Enum):
    Offline = "Offline"
    Online = "Online"


class AppointmentStatus(enum.Enum):
    awaiting = "awaiting"
    done = "done"
    cancelled = "cancelled"


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        Index(
            "uq_appointments_psychologist_scheduled_active",
            "psychologist_id",
            "scheduled_time",
            unique=True,
            postgresql_where=text("status <> 'cancelled'::appointmentstatus"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    patient_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    
    psychologist_id = Column(
        UUID(as_uuid=True), ForeignKey("psychologists.id", ondelete="CASCADE"), nullable=False
    )
    type = Column(Enum(AppointmentType), nullable=False)
    duration = Column(Integer, nullable=False, default=60)
    reason = Column(Text, nullable=True)
    status = Column(Enum(AppointmentStatus), nullable=False)
    cancel_reason = Column(String(512), nullable=True, comment="Причина отмены")
    cancelled_by = Column(String(20), nullable=True, comment="Кто отменил запись")
    emergency_cancellation = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Отмена психологом из-за ЧС",
    )
    conclusion = Column(String(2048), nullable=True, comment="Комментарий пациенту")
    psychologist_comment = Column(String(2048), nullable=True, comment="Комментарий психологам")
    scheduled_time = Column(DateTime(timezone=True), nullable=False, comment="Время назначенной встречи")
    remind_time = Column(DateTime(timezone=True), nullable=True, comment="Время напоминания")
    last_change_time = Column(DateTime(timezone=True), nullable=False, comment="Время последнего изменения")
    venue = Column(String(128), nullable=False, comment="Место проведения встречи")
    comment = Column(String(512), nullable=True, comment="Комментарий к записи")
    emergency_contact = Column(String(512), nullable=True, comment="Экстренный контакт")

    patient = relationship(
        "User", foreign_keys=[patient_id], back_populates="appointments_as_patient"
    )
    psychologist = relationship(
        "Psychologist", foreign_keys=[psychologist_id], back_populates="appointments"
    )
    review = relationship("Review", back_populates="appointment", uselist=False)
    reschedule_requests = relationship(
        "AppointmentRescheduleRequest",
        back_populates="appointment",
        cascade="all, delete-orphan",
    )

    @property
    def patient_comment(self) -> str | None:
        return self.conclusion
