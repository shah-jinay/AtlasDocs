"""Generation provider interface (blueprint sections 4.1, 13.2).

`MockGenerationProvider` is a genuine extractive baseline -- it returns the
single most relevant retrieved passage as the answer, always citing exactly
the source it drew from -- not a stub that fakes an LLM. It exists so the
vertical slice is answerable end-to-end with zero API keys; swap in
`AnthropicGenerationProvider` (ANTHROPIC_API_KEY + GENERATION_PROVIDER=
anthropic) for real synthesis quality, which is what the evaluation
harness (evaluation/run_eval.py) should ultimately score.
"""
import json
import logging
import re
from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings, get_settings
from app.rag.prompt import SYSTEM_PROMPT, SourceBlock

logger = logging.getLogger(__name__)

INSUFFICIENT_EVIDENCE_MESSAGE = (
    "I don't have enough evidence in the provided sources to answer this question."
)


@dataclass(frozen=True)
class CitationClaim:
    source_id: str
    claim: str


@dataclass(frozen=True)
class GenerationResult:
    answer: str
    citations: list[CitationClaim]
    insufficient_evidence: bool


class GenerationProvider(Protocol):
    model_name: str

    def generate(self, *, system_prompt: str, user_message: str) -> GenerationResult: ...


class MockGenerationProvider:
    model_name = "mock-extractive-v1"

    def generate(self, *, system_prompt: str, user_message: str) -> GenerationResult:
        # Reverse-engineer the source blocks from the packed context so this
        # provider has no dependency on the retrieval layer's types.
        matches = re.findall(
            r"\[SOURCE (S\d+)\][^\[]*?text: (.*?)(?=\n\[SOURCE|\Z)", user_message, re.DOTALL
        )
        if not matches:
            return GenerationResult(
                answer=INSUFFICIENT_EVIDENCE_MESSAGE, citations=[], insufficient_evidence=True
            )
        top_id, top_text = matches[0]
        excerpt = " ".join(top_text.split())[:400]
        answer = (
            f"Based on the most relevant retrieved passage ({top_id}): {excerpt}"
            if len(excerpt) < len(" ".join(top_text.split()))
            else f"Based on the most relevant retrieved passage ({top_id}): {excerpt}..."
        )
        return GenerationResult(
            answer=answer,
            citations=[CitationClaim(source_id=top_id, claim=excerpt[:200])],
            insufficient_evidence=False,
        )


class AnthropicGenerationProvider:
    def __init__(self, *, api_key: str, model: str):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self.model_name = model

    def generate(self, *, system_prompt: str, user_message: str) -> GenerationResult:
        response = self._client.messages.create(
            model=self.model_name,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return _parse_structured_response(text)


def _parse_structured_response(text: str) -> GenerationResult:
    """Parse the {"answer": ..., "citations": [...]} contract (section
    13.2). Tolerant of leading/trailing prose around the JSON object since
    not every model obeys "return nothing else" perfectly.
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        logger.warning("generation response was not JSON; treating as unstructured answer")
        return GenerationResult(answer=text.strip(), citations=[], insufficient_evidence=False)
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("generation response JSON failed to parse")
        return GenerationResult(answer=text.strip(), citations=[], insufficient_evidence=False)

    citations = [
        CitationClaim(source_id=c.get("source_id", ""), claim=c.get("claim", ""))
        for c in payload.get("citations", [])
        if c.get("source_id")
    ]
    answer = payload.get("answer", "").strip()
    return GenerationResult(
        answer=answer or INSUFFICIENT_EVIDENCE_MESSAGE,
        citations=citations,
        insufficient_evidence=not citations and not answer,
    )


def get_generation_provider(settings: Settings | None = None) -> GenerationProvider:
    settings = settings or get_settings()
    if settings.generation_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError("GENERATION_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
        return AnthropicGenerationProvider(api_key=settings.anthropic_api_key, model=settings.generation_model)
    return MockGenerationProvider()


__all__ = [
    "CitationClaim",
    "GenerationResult",
    "GenerationProvider",
    "MockGenerationProvider",
    "AnthropicGenerationProvider",
    "get_generation_provider",
    "SYSTEM_PROMPT",
    "SourceBlock",
]
