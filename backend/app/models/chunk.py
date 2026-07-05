from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class EmailChunkRecord(BaseModel):
    """Semantic retrieval chunk for one retained job-related email body."""

    email_id: str = Field(min_length=1)
    chunk_index: int = Field(ge=0)
    content: str = Field(min_length=1, repr=False)
    embedding: tuple[float, ...] = Field(repr=False)

    @field_validator("embedding")
    @classmethod
    def validate_embedding_dimensions(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if len(value) != 1536:
            msg = "email chunk embeddings must have 1536 dimensions"
            raise ValueError(msg)
        return value
