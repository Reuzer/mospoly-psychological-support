from pydantic import BaseModel
from datetime import datetime
from uuid import UUID


class ReviewsBase(BaseModel):
    appointment_id: UUID
    time: datetime
    content: str

