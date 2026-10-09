"""Strict response schemas shared by real and fake clients."""

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Entity(StrictModel):
    source: str
    context: str
    reasoning: str
    type: str
    subtype: str
    translation: str
    entity_confidence: float = Field(ge=0, le=1)
    type_confidence: float = Field(ge=0, le=1)
    translation_confidence: float = Field(ge=0, le=1)


class EntitiesResponse(StrictModel):
    entities: list[Entity]


class TextResponse(StrictModel):
    text: str


class TranslatedEntry(StrictModel):
    id: int
    content: str | None
    comment: str | None


class EntriesResponse(StrictModel):
    entries: list[TranslatedEntry]


class GlossarySubset(StrictModel):
    glossary: dict[str, str]
    keywords_glossary: dict[str, str]
