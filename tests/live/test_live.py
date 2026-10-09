"""Explicit, small real-API runs. Outputs survive both success and failure."""

from datetime import datetime
from pathlib import Path

import pytest

from st_character_card_translate.cli import main
from st_character_card_translate.common import read_json, write_json

pytestmark = pytest.mark.live


@pytest.fixture(scope="session")
def live_run_dir():
    root = Path(__file__).resolve().parents[2] / "test_outputs" / "live"
    run = root / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
    run.mkdir(parents=True)
    return run


@pytest.mark.parametrize("source,target,city,person,text", [
    ("en", "zh-Hans", "Moonshadow City", "Ailin", "The ruler of Moonshadow City is Ailin."),
    ("ja", "en", "月影城", "アイリン", "月影城の統治者はアイリンです。"),
])
def test_real_translation(live_run_dir, source, target, city, person, text):
    case = live_run_dir / f"{source}_to_{target}"
    case.mkdir()
    card = case / "card.json"
    greeting = '<START>\n{{char}}: {{user}}!\n<span class="title">' + text + '</span>\n{{roll:1d6}}\nhttps://example.com'
    write_json(card, {
        "spec": "chara_card_v2", "spec_version": "2.0", "custom_root": {"keep": True},
        "data": {
            "name": city, "alternate_greetings": [greeting],
            "character_book": {"entries": [
                {"id": 42, "name": city, "keys": [city, city], "secondary_keys": [], "content": text},
                {"id": 7, "name": person, "keys": [person], "secondary_keys": [], "content": person},
            ]},
        },
    })
    print(f"\nLive inputs and outputs: {case}", flush=True)
    try:
        assert main([str(card), "--source-lang", source, "--target-lang", target,
                     "--chunk-size", "1", "--output-dir", str(case)]) == 0
        task = case / f"card__{source}_to_{target}"
        result = read_json(task / "deduplicate_keys" / "card.json")
        glossary = read_json(task / "glossary.json")
        assert city in glossary and person in glossary
        assert result["custom_root"] == {"keep": True}
        assert result["data"]["name"] == city
        entries = result["data"]["character_book"]["entries"]
        assert [entry["id"] for entry in entries] == [42, 7]
        assert [entry["name"] for entry in entries] == [city, person]
        assert entries[0]["keys"] == [glossary[city]]
        assert entries[1]["keys"] == [glossary[person]]
        assert all("comment" not in entry for entry in entries)
        translated = result["data"]["alternate_greetings"][0]
        for token in ("<START>", "{{char}}", "{{user}}", "{{roll:1d6}}", '<span class="title">', "</span>", "https://example.com"):
            assert token in translated
    finally:
        print(f"Retained for manual language, terminology and formatting review: {case}", flush=True)
