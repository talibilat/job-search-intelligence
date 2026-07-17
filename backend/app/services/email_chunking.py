from __future__ import annotations

from typing import Protocol

from app.models.chunk import EmailChunkSource, EmailTextChunk


class ChunkableEmailRepository(Protocol):
    def list_chunkable_retained_emails(
        self,
        *,
        limit: int,
        offset: int = 0,
    ) -> list[EmailChunkSource]: ...


class EmailChunkingService:
    """Build deterministic unembedded chunks from retained job-related email bodies."""

    def __init__(
        self,
        repository: ChunkableEmailRepository,
        *,
        max_chars: int = 1200,
        overlap_chars: int = 200,
    ) -> None:
        if max_chars < 1:
            msg = "max_chars must be at least 1"
            raise ValueError(msg)
        if overlap_chars < 0:
            msg = "overlap_chars must be non-negative"
            raise ValueError(msg)
        if overlap_chars >= max_chars:
            msg = "overlap_chars must be smaller than max_chars"
            raise ValueError(msg)

        self._repository = repository
        self._max_chars = max_chars
        self._overlap_chars = overlap_chars

    def build_chunks(self, *, limit: int, offset: int = 0) -> tuple[EmailTextChunk, ...]:
        if limit < 1:
            msg = "limit must be at least 1"
            raise ValueError(msg)
        if offset < 0:
            msg = "offset must be non-negative"
            raise ValueError(msg)

        chunks: list[EmailTextChunk] = []
        for source in self._repository.list_chunkable_retained_emails(
            limit=limit,
            offset=offset,
        ):
            chunks.extend(
                EmailTextChunk(email_id=source.email_id, chunk_index=index, content=content)
                for index, content in enumerate(self._chunk_text(source.body_text))
            )
        return tuple(chunks)

    def _chunk_text(self, text: str) -> tuple[str, ...]:
        paragraphs = _normalize_paragraphs(text)
        if not paragraphs:
            return ()

        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if len(paragraph) > self._max_chars:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.extend(self._split_long_text(paragraph))
                continue

            candidate = paragraph if not current else f"{current}\n\n{paragraph}"
            if len(candidate) <= self._max_chars:
                current = candidate
                continue

            chunks.append(current)
            overlap = current[-self._overlap_chars :] if self._overlap_chars else ""
            current = f"{overlap}\n\n{paragraph}" if overlap else paragraph
            if len(current) > self._max_chars:
                chunks.extend(self._split_long_text(current))
                current = ""

        if current:
            chunks.append(current)
        return tuple(chunks)

    def _split_long_text(self, text: str) -> tuple[str, ...]:
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + self._max_chars, len(text))
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end == len(text):
                break
            start = end - self._overlap_chars if self._overlap_chars else end
        return tuple(chunks)


def _normalize_paragraphs(text: str) -> tuple[str, ...]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return tuple(paragraph.strip() for paragraph in normalized.split("\n\n") if paragraph.strip())
