"""Synchronous, non-persistent help for turning a student draft into a Question."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from tbd.providers.ai import (
    AIProviderError,
    LLMGenerationRequest,
    LLMMessage,
    LLMProvider,
    ProviderInvalidResponseError,
)
from tbd.repositories.questions import QuestionRepository
from tbd.schemas.questions import QuestionDraftResponse
from tbd.services.questions import QuestionNotFoundError, QuestionService

QUESTION_DRAFT_HELP_PROMPT_VERSION = "question-draft-help-v1"
QUESTION_DRAFT_HELP_TIMEOUT = timedelta(seconds=5)


@dataclass
class QuestionDraftValidationError(Exception):
    """The normalized draft cannot be sent to the provider."""

    reason: str
    actual_length: int


class QuestionDraftProviderError(Exception):
    """A safe provider error for the HTTP boundary without raw provider details."""


class QuestionDraftService:
    """Authorize and refine one draft without creating a Question or AIJob."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        repository: QuestionRepository | None = None,
    ) -> None:
        self._provider = provider
        self._repository = repository or QuestionRepository()

    async def suggest(
        self,
        session: AsyncSession,
        *,
        session_id: UUID,
        user_id: UUID,
        draft: str,
    ) -> QuestionDraftResponse:
        normalized_draft = self.normalize_draft(draft)
        lecture_session = await self._repository.get_session(session, session_id)
        if lecture_session is None:
            raise QuestionNotFoundError
        QuestionService._require_live_student(
            role=await self._repository.member_role(
                session,
                course_id=lecture_session.course_id,
                user_id=user_id,
            ),
            status=lecture_session.status,
        )

        try:
            result = await self._provider.generate(
                LLMGenerationRequest(
                    purpose="QUESTION_DRAFT_HELP",
                    prompt_version=QUESTION_DRAFT_HELP_PROMPT_VERSION,
                    messages=(
                        LLMMessage(
                            role="system",
                            content=(
                                "Rewrite the student's draft as one concise, respectful Korean "
                                "lecture question. Return only the candidate question."
                            ),
                        ),
                        LLMMessage(role="user", content=normalized_draft),
                    ),
                ),
                timeout=QUESTION_DRAFT_HELP_TIMEOUT,
            )
            suggestion = self.normalize_suggestion(result.content)
        except AIProviderError as exc:
            raise QuestionDraftProviderError from exc
        return QuestionDraftResponse(suggestions=[suggestion])

    @staticmethod
    def normalize_draft(draft: str) -> str:
        normalized = unicodedata.normalize("NFC", draft.strip())
        length = len(normalized)
        if length == 0:
            raise QuestionDraftValidationError("EMPTY_AFTER_NORMALIZATION", length)
        if length > 500:
            raise QuestionDraftValidationError("MAX_LENGTH_EXCEEDED", length)
        return normalized

    @staticmethod
    def normalize_suggestion(suggestion: str) -> str:
        normalized = unicodedata.normalize("NFC", suggestion.strip())
        if not normalized or len(normalized) > 300:
            raise ProviderInvalidResponseError
        return normalized
