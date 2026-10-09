"""Shared file and field operations; no stage orchestration."""

import json
from contextlib import contextmanager
from pathlib import Path

TEXT_FIELDS = (
    "data.description",
    "data.personality",
    "data.first_mes",
    "data.mes_example",
    "data.scenario",
    "data.creator_notes",
    "data.system_prompt",
    "data.post_history_instructions",
    "data.character_book.description",
)
ENTRY_FIELDS = ("id", "name", "keys", "secondary_keys", "content", "comment")
BODY_FIELDS = ("content", "comment")
KEY_FIELDS = ("keys", "secondary_keys")
ENTRIES_PREFIX = "data.character_book.entries_"


class StageError(RuntimeError):
    pass


@contextmanager
def stage_context(stage: str, path: Path):
    try:
        yield
    except StageError:
        raise
    except Exception as exc:
        raise StageError(f"{stage}: {path}: {exc}") from exc


def read_json(path: Path, encoding: str = "utf-8"):
    try:
        return json.loads(path.read_text(encoding=encoding))
    except (OSError, ValueError, LookupError) as exc:
        raise ValueError(f"{path}: {exc}") from exc


def write_json(path: Path, value) -> None:
    try:
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path}: {exc}") from exc


def json_files(directory: Path) -> list[Path]:
    # iterdir raises for a missing upstream directory, while an empty one is valid.
    return sorted(path for path in directory.iterdir() if path.suffix == ".json")


def text_field_locations(card: dict):
    """Yield existing target fields and their mutable parent objects."""
    for dotted_path in TEXT_FIELDS:
        parent = card
        parts = dotted_path.split(".")
        for part in parts[:-1]:
            parent = parent.get(part)
            if parent is None:
                break
        if parent is not None and parts[-1] in parent:
            yield dotted_path, parent, parts[-1]


def world_entries(card: dict) -> list:
    book = card["data"].get("character_book")
    return (book.get("entries") or []) if book is not None else []


def is_world_file(path: Path) -> bool:
    return path.name.startswith(ENTRIES_PREFIX)


def entry_filename(start: int, end: int, total: int) -> str:
    width = max(6, len(str(total)))
    return f"{ENTRIES_PREFIX}{start:0{width}d}_{end:0{width}d}.json"


def has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def body_texts(field, is_world: bool) -> list[str]:
    values = (
        [entry[key] for entry in field for key in BODY_FIELDS]
        if is_world
        else [field["text"]]
    )
    return [value for value in values if value is not None]


def nonblank_keywords(entries: list[dict]) -> list[str]:
    return list(dict.fromkeys(
        term
        for entry in entries
        for key in KEY_FIELDS
        for term in (entry[key] or [])
        if term.strip()
    ))


def read_background(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path}: {exc}") from exc
