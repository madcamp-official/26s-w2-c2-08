"""Provider-neutral LIVE Question clustering boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ClusteringInput:
    """One immutable student Question selected by a Job watermark."""

    question_id: UUID
    content: str


@dataclass(frozen=True, slots=True)
class ClusterSuggestion:
    """One provider-produced group with a safe representative sentence."""

    representative: str
    question_ids: tuple[UUID, ...]


@runtime_checkable
class QuestionClusteringProvider(Protocol):
    """Classify the supplied inputs without owning persistence or job state."""

    async def cluster(self, inputs: tuple[ClusteringInput, ...]) -> tuple[ClusterSuggestion, ...]:
        """Return a complete, disjoint partition of ``inputs``."""
