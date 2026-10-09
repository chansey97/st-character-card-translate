from pathlib import Path

from .common import KEY_FIELDS, print_progress, read_json, stage_context, world_entries, write_json


def deduplicate_keys(card_path: Path, output_path: Path) -> Path:
    with stage_context("deduplicate_keys", card_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        skipped = output_path.exists()
        print_progress("deduplicate_keys", 1, 1, output_path, skipped=skipped)
        if skipped:
            return output_path
        card = read_json(card_path)
        for entry in world_entries(card):
            for key in KEY_FIELDS:
                if key in entry and entry[key] is not None:
                    entry[key] = list(dict.fromkeys(entry[key]))
        write_json(output_path, card)
        return output_path
