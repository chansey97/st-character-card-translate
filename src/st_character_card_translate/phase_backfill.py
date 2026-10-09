from pathlib import Path

from .common import (
    BODY_FIELDS, KEY_FIELDS, is_world_file, json_files, print_progress, read_json,
    stage_context, text_field_locations, world_entries, write_json,
)


def backfill(
    card_path: Path, translations_dir: Path, output_path: Path, *,
    input_encoding: str = "utf-8-sig",
) -> Path:
    with stage_context("backfill", card_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            print_progress("backfill", 1, 1, output_path, skipped=True)
            return output_path
        card = read_json(card_path, input_encoding)
        text_fields = list(text_field_locations(card))
        greetings = card["data"].get("alternate_greetings") or []
        entries = world_entries(card)
        with stage_context("backfill", translations_dir):
            world_paths = [path for path in json_files(translations_dir) if is_world_file(path)] if entries else []
        total = len(text_fields) + len(greetings) + len(world_paths) + 1
        for index, (dotted_path, parent, key) in enumerate(text_fields, start=1):
            path = translations_dir / f"{dotted_path}.json"
            print_progress("backfill", index, total, path)
            with stage_context("backfill", path):
                parent[key] = read_json(path)["text"]
        for index in range(len(greetings)):
            path = translations_dir / f"data.alternate_greetings_{index}.json"
            print_progress("backfill", len(text_fields) + index + 1, total, path)
            with stage_context("backfill", path):
                greetings[index] = read_json(path)["text"]
        if entries:
            with stage_context("backfill", translations_dir):
                translated = []
                for index, path in enumerate(world_paths, start=len(text_fields) + len(greetings) + 1):
                    print_progress("backfill", index, total, path)
                    translated.extend(read_json(path))
                for position, entry in enumerate(entries):
                    translated_entry = translated[position]
                    for key in (*KEY_FIELDS, *BODY_FIELDS):
                        if key in entry:
                            entry[key] = translated_entry[key]
        print_progress("backfill", total, total, output_path)
        write_json(output_path, card)
        return output_path
