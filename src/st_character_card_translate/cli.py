"""Command-line validation and inclusive seven-stage orchestration."""

import argparse
import io
import math
import re
import sys
from contextlib import ExitStack
from pathlib import Path

from openai import OpenAI

from .config import APP_NAME, ConfigError, load_config
from .phase_backfill import backfill
from .phase_build_glossary import build_glossary
from .phase_deduplicate_keys import deduplicate_keys
from .phase_discover_entities import discover_entities
from .phase_extract_fields import extract_fields
from .phase_generate_glossary_subsets import generate_glossary_subsets
from .phase_translate import translate

STAGES = ("extract", "discover", "glossary", "subsets", "translate", "backfill", "deduplicate_keys")


def _positive_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive integer") from None
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _delay(value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a nonnegative finite number") from None
    if number < 0 or not math.isfinite(number):
        raise argparse.ArgumentTypeError("must be a nonnegative finite number")
    return number


def _language(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9-]+", value):
        raise argparse.ArgumentTypeError("use only ASCII letters, digits and hyphens")
    return value


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP_NAME, description="Translate a SillyTavern V2-style JSON character card.",
    )
    parser.add_argument("input_json", type=Path, metavar="INPUT_JSON")
    parser.add_argument("--source-lang", required=True, type=_language, metavar="LANG")
    parser.add_argument("--target-lang", default="zh-Hans", type=_language, metavar="LANG")
    parser.add_argument("--background", type=Path, metavar="PATH")
    parser.add_argument("--output-dir", type=Path, default=Path.cwd(), metavar="PATH")
    parser.add_argument("--config-file", type=Path, metavar="PATH")
    parser.add_argument("--input-encoding", default="utf-8-sig", metavar="NAME")
    parser.add_argument("--chunk-size", default=10, type=_positive_integer, metavar="N")
    parser.add_argument("--no-translate-glossary", action="store_true")
    parser.add_argument("--delay-between-requests", default=0.0, type=_delay, metavar="SECONDS")
    parser.add_argument("--from-stage", default=STAGES[0], choices=STAGES)
    parser.add_argument("--to-stage", default=STAGES[-1], choices=STAGES)
    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows pipes can default to an encoding that cannot represent card paths.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors=stream.errors)

    parser = make_parser()
    args = parser.parse_args(argv)
    start, end = STAGES.index(args.from_stage), STAGES.index(args.to_stage)
    if start > end:
        parser.error("--from-stage must not be later than --to-stage")
    try:
        config = load_config(args.config_file)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    task_dir = args.output_dir / f"{args.input_json.stem}__{args.source_lang}_to_{args.target_lang}"
    fields = task_dir / "fields"
    entities = task_dir / "entities"
    glossary = task_dir / "glossary.json"
    subsets = task_dir / "glossary_subsets"
    translations = task_dir / "translations"
    backfilled = task_dir / "backfill" / args.input_json.name
    final = task_dir / "deduplicate_keys" / args.input_json.name
    client = None
    stage = args.from_stage
    try:
        with ExitStack() as stack:
            for stage in STAGES[start:end + 1]:
                print(f"[{stage}] {task_dir}", flush=True)
                if stage in ("discover", "translate") and client is None:
                    client = stack.enter_context(OpenAI(
                        base_url=config.base_url, api_key=config.api_key,
                        max_retries=config.max_retries,
                    ))
                if stage == "extract":
                    extract_fields(
                        args.input_json, fields, chunk_size=args.chunk_size,
                        input_encoding=args.input_encoding,
                    )
                elif stage == "discover":
                    discover_entities(
                        fields, entities, source_lang=args.source_lang, target_lang=args.target_lang,
                        client=client, model=config.model, background_path=args.background,
                        delay_between_requests=args.delay_between_requests,
                    )
                elif stage == "glossary":
                    build_glossary(entities, glossary)
                elif stage == "subsets":
                    generate_glossary_subsets(fields, glossary, subsets)
                elif stage == "translate":
                    translate(
                        fields, subsets, translations,
                        source_lang=args.source_lang, target_lang=args.target_lang,
                        client=client, model=config.model, background_path=args.background,
                        no_translate_glossary=args.no_translate_glossary,
                        delay_between_requests=args.delay_between_requests,
                    )
                elif stage == "backfill":
                    backfill(
                        args.input_json, translations, backfilled,
                        input_encoding=args.input_encoding,
                    )
                else:
                    deduplicate_keys(backfilled, final)
    except Exception as exc:
        print(f"[{stage}] {task_dir}: {exc}", file=sys.stderr)
        return 1
    print(f"Completed: {final if args.to_stage == STAGES[-1] else task_dir}")
    return 0
