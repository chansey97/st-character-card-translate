from pathlib import Path

from .common import (
    BODY_FIELDS, KEY_FIELDS, is_world_file, json_files, read_json,
    stage_context, text_field_locations, world_entries, write_json,
)


def backfill(
    card_path: Path, translations_dir: Path, output_path: Path, *,
    input_encoding: str = "utf-8-sig",
) -> Path:
    with stage_context("backfill", card_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            return output_path
        card = read_json(card_path, input_encoding)
        for dotted_path, parent, key in text_field_locations(card):
            path = translations_dir / f"{dotted_path}.json"
            with stage_context("backfill", path):
                parent[key] = read_json(path)["text"]
        greetings = card["data"].get("alternate_greetings") or []
        for index in range(len(greetings)):
            path = translations_dir / f"data.alternate_greetings_{index}.json"
            with stage_context("backfill", path):
                greetings[index] = read_json(path)["text"]
        entries = world_entries(card)
        if entries:
            with stage_context("backfill", translations_dir):
                translated = []
                for path in json_files(translations_dir):
                    if is_world_file(path):
                        translated.extend(read_json(path))
                for position, entry in enumerate(entries):
                    translated_entry = translated[position]
                    for key in (*KEY_FIELDS, *BODY_FIELDS):
                        if key in entry:
                            entry[key] = translated_entry[key]
        write_json(output_path, card)
        return output_path
