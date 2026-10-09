import re
from pathlib import Path

from .common import (
    ENTRY_FIELDS, KEY_FIELDS, entry_filename, print_progress, read_json, stage_context,
    text_field_locations, world_entries, write_json,
)


def extract_fields(
    card_path: Path, fields_dir: Path, *,
    chunk_size: int = 10, input_encoding: str = "utf-8-sig",
) -> list[Path]:
    with stage_context("extract", card_path):
        fields_dir.mkdir(parents=True, exist_ok=True)
        if type(chunk_size) is not int or chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")
        card = read_json(card_path, input_encoding)
        if not isinstance(card, dict) or not isinstance(card.get("data"), dict):
            raise ValueError("Expected a V2-style card with a data object")
        if "spec" in card and card["spec"] != "chara_card_v2":
            raise ValueError(f"Unsupported card spec: {card['spec']!r}")
        if "spec_version" in card and card["spec_version"] != "2.0":
            raise ValueError(f"Unsupported card spec_version: {card['spec_version']!r}")
        entries = world_entries(card)
        # Validate every keyword before generating any files from this card.
        for position, entry in enumerate(entries, start=1):
            for key in KEY_FIELDS:
                for term in entry.get(key) or []:
                    if re.fullmatch(r"/.*?/[A-Za-z]*", term, flags=re.DOTALL):
                        raise ValueError(
                            f"Unsupported regex keyword at entries position {position}, "
                            f"{key}: {term!r}"
                        )

        text_fields = list(text_field_locations(card))
        greetings = card["data"].get("alternate_greetings") or []
        chunk_starts = range(0, len(entries), chunk_size)
        total = len(text_fields) + len(greetings) + len(chunk_starts)
        if not total:
            print_progress("extract", 0, 0)
        outputs = []

        def save(name, value):
            path = fields_dir / name
            outputs.append(path)
            skipped = path.exists()
            print_progress("extract", len(outputs), total, path, skipped=skipped)
            if not skipped:
                write_json(path, value)

        for dotted_path, parent, key in text_fields:
            save(f"{dotted_path}.json", {"text": parent[key]})
        for index, greeting in enumerate(greetings):
            save(f"data.alternate_greetings_{index}.json", {"text": greeting})
        for start in chunk_starts:
            end = min(start + chunk_size, len(entries))
            path = fields_dir / entry_filename(start + 1, end, len(entries))
            outputs.append(path)
            skipped = path.exists()
            print_progress("extract", len(outputs), total, path, skipped=skipped)
            if skipped:
                continue
            chunk = [
                {key: entry["id"] if key == "id" else entry.get(key) for key in ENTRY_FIELDS}
                for entry in entries[start:end]
            ]
            write_json(path, chunk)
        return outputs
