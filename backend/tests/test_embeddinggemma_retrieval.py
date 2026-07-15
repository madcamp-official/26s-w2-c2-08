"""Unit coverage for the fixed EmbeddingGemma retrieval input contract."""

import pytest

from tbd.models.knowledge import KNOWLEDGE_EMBEDDING_DIMENSION
from tbd.services.knowledge import (
    EMBEDDINGGEMMA_DOCUMENT_PURPOSE,
    EMBEDDINGGEMMA_PROMPT_VERSION,
    EMBEDDINGGEMMA_QUERY_PURPOSE,
    format_embeddinggemma_document,
    format_embeddinggemma_query,
)

pytestmark = pytest.mark.unit


def test_embeddinggemma_retrieval_uses_fixed_dimension_and_asymmetric_prefixes() -> None:
    """Document excerpts and user queries must not share one ambiguous prompt form."""

    assert KNOWLEDGE_EMBEDDING_DIMENSION == 768
    assert EMBEDDINGGEMMA_PROMPT_VERSION == "embeddinggemma-retrieval-v1"
    assert EMBEDDINGGEMMA_DOCUMENT_PURPOSE == "embeddinggemma-retrieval-document-v1"
    assert EMBEDDINGGEMMA_QUERY_PURPOSE == "embeddinggemma-retrieval-query-v1"
    assert (
        format_embeddinggemma_document(title=" 네트워크 개론 ", content="  TCP   혼잡 제어  ")
        == "title: 네트워크 개론 | text: TCP 혼잡 제어"
    )
    assert (
        format_embeddinggemma_document(title=None, content="PDF 본문")
        == "title: none | text: PDF 본문"
    )
    assert format_embeddinggemma_query("  혼잡   제어가 뭐야? ") == (
        "task: search result | query: 혼잡 제어가 뭐야?"
    )


@pytest.mark.parametrize("title,content", [("제목", "   "), ("", "")])
def test_embeddinggemma_document_rejects_empty_source_text(title: str, content: str) -> None:
    """A malformed source cannot accidentally become a title-only vector."""

    with pytest.raises(ValueError, match="non-empty"):
        format_embeddinggemma_document(title=title, content=content)


def test_embeddinggemma_query_rejects_whitespace_only_input() -> None:
    """Retrieval retains the existing non-empty query precondition after prefixing."""

    with pytest.raises(ValueError, match="non-empty"):
        format_embeddinggemma_query("  \n\t ")
