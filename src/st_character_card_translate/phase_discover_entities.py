from pathlib import Path

from .common import (
    body_texts, has_text, is_world_file, json_files, nonblank_keywords,
    print_progress, read_background, read_json, stage_context, write_json,
)
from .llm import request_json
from .prompts import discovery_prompt
from .schemas import EntitiesResponse


def discover_entities(
    fields_dir: Path, entities_dir: Path, *, source_lang: str, target_lang: str,
    client, model: str, background_path: Path | None = None,
    delay_between_requests: float = 0.0,
) -> list[Path]:
    with stage_context("discover", fields_dir):
        entities_dir.mkdir(parents=True, exist_ok=True)
        paths = json_files(fields_dir)
    if not paths:
        print_progress("discover", 0, 0)
    outputs = []
    background = None
    for index, path in enumerate(paths, start=1):
        output = entities_dir / path.name
        outputs.append(output)
        skipped = output.exists()
        print_progress("discover", index, len(paths), path, skipped=skipped)
        if skipped:
            continue
        with stage_context("discover", path):
            field = read_json(path)
            is_world = is_world_file(path)
            forced_terms = nonblank_keywords(field) if is_world else []
            if not forced_terms and not any(has_text(text) for text in body_texts(field, is_world)):
                write_json(output, [])
                continue
            if background is None:
                background = read_background(background_path)
            request = {
                "source_lang": source_lang, "target_lang": target_lang,
                "background": background,
            }
            if is_world:
                request["forced_terms"] = forced_terms
                request["entries"] = [
                    {key: entry[key] for key in ("id", "name", "content", "comment")}
                    for entry in field
                ]
            else:
                request["text"] = field["text"]
            entities = request_json(
                client, model, discovery_prompt(is_world), request,
                EntitiesResponse, delay_between_requests,
            )["entities"]
            sources = {entity["source"] for entity in entities}
            missing = [term for term in forced_terms if term not in sources]
            if missing:
                raise ValueError(f"Missing forced terms: {missing!r}")
            forced_set = set(forced_terms)
            for entity in entities:
                if entity["source"] in forced_set:
                    entity["entity_confidence"] = 1.0
            write_json(output, entities)
    return outputs
