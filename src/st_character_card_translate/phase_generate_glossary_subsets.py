from pathlib import Path

from pydantic import TypeAdapter

from .common import (
    body_texts, is_world_file, json_files, nonblank_keywords,
    print_progress, read_json, stage_context, write_json,
)


def generate_glossary_subsets(
    fields_dir: Path, glossary_path: Path, glossary_subsets_dir: Path,
) -> list[Path]:
    with stage_context("subsets", fields_dir):
        glossary_subsets_dir.mkdir(parents=True, exist_ok=True)
        paths = json_files(fields_dir)
    if not paths:
        print_progress("subsets", 0, 0)
    outputs = []
    glossary = None
    for index, path in enumerate(paths, start=1):
        output = glossary_subsets_dir / path.name
        outputs.append(output)
        skipped = output.exists()
        print_progress("subsets", index, len(paths), path, skipped=skipped)
        if skipped:
            continue
        with stage_context("subsets", path):
            if glossary is None:
                with stage_context("subsets", glossary_path):
                    glossary = TypeAdapter(dict[str, str]).validate_python(
                        read_json(glossary_path), strict=True,
                    )
            field = read_json(path)
            is_world = is_world_file(path)
            texts = [text.casefold() for text in body_texts(field, is_world)]
            matched = {
                source for source in glossary
                if source.strip() and any(source.casefold() in text for text in texts)
            }
            keywords = nonblank_keywords(field) if is_world else []
            write_json(output, {
                "glossary": {source: glossary[source] for source in sorted(matched)},
                "keywords_glossary": {
                    source: glossary[source] for source in sorted(set(keywords))
                },
            })
    return outputs
