from pathlib import Path

from .common import (
    BODY_FIELDS, KEY_FIELDS, body_texts, has_text, is_world_file, json_files,
    print_progress, read_background, read_json, stage_context, write_json,
)
from .llm import request_json
from .prompts import translation_prompt
from .schemas import EntriesResponse, GlossarySubset, TextResponse


def translate(
    fields_dir: Path, glossary_subsets_dir: Path, translations_dir: Path, *,
    source_lang: str, target_lang: str, client, model: str,
    background_path: Path | None = None, no_translate_glossary: bool = False,
    delay_between_requests: float = 0.0,
) -> list[Path]:
    with stage_context("translate", fields_dir):
        translations_dir.mkdir(parents=True, exist_ok=True)
        paths = json_files(fields_dir)
    if not paths:
        print_progress("translate", 0, 0)
    outputs = []
    background = None
    for index, path in enumerate(paths, start=1):
        output = translations_dir / path.name
        outputs.append(output)
        skipped = output.exists()
        print_progress("translate", index, len(paths), path, skipped=skipped)
        if skipped:
            continue
        with stage_context("translate", path):
            field = read_json(path)
            subset_path = glossary_subsets_dir / path.name
            with stage_context("translate", subset_path):
                subset = GlossarySubset.model_validate(read_json(subset_path))
            is_world = is_world_file(path)
            has_body = any(has_text(text) for text in body_texts(field, is_world))
            if has_body:
                if background is None:
                    background = read_background(background_path)
                request = {
                    "source_lang": source_lang, "target_lang": target_lang,
                    "background": background,
                }
                if no_translate_glossary:
                    request["do_not_translate_terms"] = list(subset.glossary)
                else:
                    request["glossary"] = subset.glossary
                if is_world:
                    request["entries"] = [
                        {key: entry[key] for key in ("id", *BODY_FIELDS)}
                        for entry in field
                    ]
                else:
                    request["text"] = field["text"]
                response = request_json(
                    client, model, translation_prompt(is_world, no_translate_glossary),
                    request, EntriesResponse if is_world else TextResponse,
                    delay_between_requests,
                )
            if not is_world:
                translated = {"text": response["text"] if has_body else field["text"]}
            else:
                translated_entries = response["entries"] if has_body else field
                if len(translated_entries) != len(field):
                    raise ValueError(
                        f"Expected {len(field)} translations, got {len(translated_entries)}"
                    )
                for position, (entry, translated_entry) in enumerate(
                    zip(field, translated_entries), start=1,
                ):
                    if translated_entry["id"] != entry["id"]:
                        raise ValueError(f"Entry id mismatch at position {position}")
                    for key in BODY_FIELDS:
                        if (entry[key] is None) != (translated_entry[key] is None):
                            raise ValueError(f"Entry {key} null mismatch at position {position}")
                translated = []
                for entry, translated_entry in zip(field, translated_entries):
                    result = {"id": entry["id"], "name": entry["name"]}
                    for key in KEY_FIELDS:
                        keywords = entry[key]
                        if keywords is None or no_translate_glossary:
                            result[key] = keywords
                        else:
                            result[key] = [
                                subset.keywords_glossary[term] if term.strip() else term
                                for term in keywords
                            ]
                    for key in BODY_FIELDS:
                        result[key] = translated_entry[key] if has_text(entry[key]) else entry[key]
                    translated.append(result)
            write_json(output, translated)
    return outputs
