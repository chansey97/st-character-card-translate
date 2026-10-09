from pathlib import Path

from pydantic import TypeAdapter

from .common import json_files, print_progress, read_json, stage_context, write_json
from .schemas import Entity


def build_glossary(entities_dir: Path, glossary_path: Path) -> Path:
    with stage_context("glossary", glossary_path):
        glossary_path.parent.mkdir(parents=True, exist_ok=True)
        if glossary_path.exists():
            print_progress("glossary", 1, 1, glossary_path, skipped=True)
            return glossary_path
        paths = json_files(entities_dir)
        total = len(paths) + 1
        candidates = {}
        for index, path in enumerate(paths, start=1):
            print_progress("glossary", index, total, path)
            with stage_context("glossary", path):
                entities = TypeAdapter(list[Entity]).validate_python(read_json(path))
                for entity in entities:
                    score = (
                        entity.entity_confidence + entity.type_confidence
                        + entity.translation_confidence
                    ) / 3
                    if entity.source not in candidates or score > candidates[entity.source][0]:
                        candidates[entity.source] = (score, entity.translation)
        print_progress("glossary", total, total, glossary_path)
        write_json(glossary_path, {
            source: candidates[source][1] for source in sorted(candidates)
        })
        return glossary_path
