from typing import Annotated, Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, field_validator, model_validator
from psychohelp.models.psy_tests import QuestionType, TestType


MAX_QUESTION_OPTIONS = 100
EstimatedDuration = Annotated[int, Field(gt=0, le=2_147_483_647, strict=True)]


class PsyTestQuestionOptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, StringConstraints(
        strip_whitespace=True, min_length=1, max_length=1000, pattern=r"^[^\x00]+$",
    )]


class PsyTestQuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000, pattern=r"^[^\x00]+$")]
    type: QuestionType = QuestionType.TEXT
    options: list[PsyTestQuestionOptionInput] = Field(
        default_factory=list, max_length=MAX_QUESTION_OPTIONS,
        description="Для вопросов с выбором требуется минимум два варианта.",
    )

    @model_validator(mode="after")
    def validate_options(self):
        if self.type == QuestionType.TEXT:
            if self.options:
                raise ValueError("Текстовый вопрос не содержит вариантов ответа")
        elif len(self.options) < 2:
            raise ValueError("Для вопроса с выбором нужны как минимум два варианта")
        return self


class PsyTestCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    image: Optional[str] = Field(None, max_length=1024)
    type: TestType  # Обязательное поле при создании
    url: HttpUrl | None = None
    estimated_duration_minutes: EstimatedDuration | None = None
    questions: list[PsyTestQuestionInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_type(self):
        if self.type == TestType.MEDICAL:
            if not self.questions or self.url is not None:
                raise ValueError("Для медицинского теста нужны вопросы, внешний URL запрещён")
        elif self.url is None or self.questions:
            raise ValueError("Для развлекательного теста нужен внешний URL, вопросы запрещены")
        return self


class PsyTestUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=1)
    image: Optional[str] = Field(None, max_length=1024)
    type: Optional[TestType] = None
    url: HttpUrl | None = None
    estimated_duration_minutes: EstimatedDuration | None = None


class PsyTestResponse(BaseModel):
    id: UUID
    title: str
    description: str
    image: Optional[str] = None
    type: TestType
    url: str | None = None
    estimated_duration_minutes: int | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class PsyTestListItem(PsyTestResponse):
    questions_count: int


class PsyTestQuestionOptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    text: str


class PsyTestQuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int
    text: str
    image: str | None
    type: QuestionType
    options: list[PsyTestQuestionOptionResponse]


class PsyTestTextAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=10000, pattern=r"^[^\x00]+$")

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Ответ должен содержать текст")
        return value


class PsyTestChoiceAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_ids: list[UUID] = Field(
        min_length=1, max_length=MAX_QUESTION_OPTIONS,
        description="UUID вариантов вопроса. Для одиночного выбора передайте один UUID.",
    )

    @field_validator("option_ids")
    @classmethod
    def validate_unique_options(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Варианты ответа не должны повторяться")
        return value


PsyTestAnswerRequest = PsyTestTextAnswerRequest | PsyTestChoiceAnswerRequest


class _PsyTestSavedAnswer(BaseModel):
    question: PsyTestQuestionResponse
    answered_at: datetime


class PsyTestSavedTextAnswer(_PsyTestSavedAnswer):
    answer: str


class PsyTestSavedChoiceAnswer(_PsyTestSavedAnswer):
    option_ids: list[UUID]


class PsyTestAttemptSummary(BaseModel):
    id: UUID
    user_id: UUID
    test_id: UUID
    test_title: str
    started_at: datetime
    completed_at: datetime | None


class PsyTestAttemptResponse(PsyTestAttemptSummary):
    answers: list[PsyTestSavedTextAnswer | PsyTestSavedChoiceAnswer]
    next_question: PsyTestQuestionResponse | None
