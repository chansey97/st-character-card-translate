from copy import deepcopy

import pytest

from st_character_card_translate.common import StageError, read_json
from st_character_card_translate.phase_backfill import backfill
from st_character_card_translate.phase_deduplicate_keys import deduplicate_keys


def test_position_backfill_preserves_all_other_data(tmp_path, save_json):
    original = {
        "spec": "chara_card_v2", "spec_version": "2.0", "root_extension": [1, 2],
        "description": "legacy field unchanged",
        "data": {
            "name": "Name", "description": "description", "extension": {"unknown": True},
            "alternate_greetings": [f"greeting {index}" for index in range(11)],
            "character_book": {
                "name": "Book", "description": "book description", "recursive_scanning": True,
                "entries": [
                    {"id": 42, "name": "Name 42", "keys": ["A"], "content": "first", "custom": [42]},
                    {"id": 7, "name": None, "secondary_keys": None, "content": "second", "comment": "", "enabled": False},
                    {"id": 105, "keys": [], "secondary_keys": ["B"], "content": None, "constant": True},
                ],
            },
        },
    }
    card = save_json(tmp_path / "card.json", original)
    translations = tmp_path / "translations"
    save_json(translations / "data.description.json", {"text": "描述"})
    save_json(translations / "data.character_book.description.json", {"text": "世界书描述"})
    for index in reversed(range(11)):
        save_json(translations / f"data.alternate_greetings_{index}.json", {"text": f"开场白{index}"})
    # Deliberately reorder ids: backfill consumes positions and never repairs ids.
    save_json(translations / "data.character_book.entries_000003_000003.json", [
        {"id": -1, "name": "ignored", "keys": [], "secondary_keys": ["乙"], "content": None, "comment": None},
    ])
    save_json(translations / "data.character_book.entries_000001_000002.json", [
        {"id": 7, "name": "ignored", "keys": ["甲"], "secondary_keys": None, "content": "第一", "comment": None},
        {"id": 42, "name": "ignored", "keys": None, "secondary_keys": None, "content": "第二", "comment": ""},
    ])
    expected = deepcopy(original)
    expected["data"]["description"] = "描述"
    expected["data"]["alternate_greetings"] = [f"开场白{index}" for index in range(11)]
    book = expected["data"]["character_book"]
    book["description"] = "世界书描述"
    book["entries"][0].update(keys=["甲"], content="第一")
    book["entries"][1]["content"] = "第二"
    book["entries"][2]["secondary_keys"] = ["乙"]
    output = backfill(card, translations, tmp_path / "backfill" / "card.json")
    assert read_json(output) == expected
    assert read_json(card) == original


@pytest.mark.parametrize("failure", ["missing_text", "missing_greeting", "too_few_entries", "missing_entry_field"])
def test_missing_data_never_writes_partial_card(tmp_path, save_json, failure):
    data = {}
    translations = tmp_path / "translations"
    translations.mkdir()
    if failure == "missing_text":
        data["description"] = "source"
    elif failure == "missing_greeting":
        data["alternate_greetings"] = ["a", "b"]
        save_json(translations / "data.alternate_greetings_0.json", {"text": "甲"})
    else:
        data["character_book"] = {"entries": [{"id": 42, "content": "source"}]}
        value = [] if failure == "too_few_entries" else [{"id": 42}]
        save_json(translations / "data.character_book.entries_000001_000001.json", value)
    card = save_json(tmp_path / "card.json", {"data": data})
    output = tmp_path / "backfill" / "card.json"
    with pytest.raises(StageError, match="backfill"):
        backfill(card, translations, output)
    assert not output.exists()


def test_backfill_does_not_recheck_or_reject_extra_entries(tmp_path, save_json):
    card = save_json(tmp_path / "card.json", {"data": {"character_book": {"entries": [{"id": 42, "content": "source"}]}}})
    save_json(tmp_path / "translations" / "data.character_book.entries_000001_000001.json", [
        {"id": 7, "content": "first position"}, {"id": 42, "content": "unused"},
    ])
    output = backfill(card, tmp_path / "translations", tmp_path / "out.json")
    assert read_json(output)["data"]["character_book"]["entries"] == [{"id": 42, "content": "first position"}]


def test_deduplicate_exact_stable_and_local_to_each_array(tmp_path, save_json):
    original = {"data": {"character_book": {"entries": [
        {"id": 42, "name": "same", "keys": ["丘陵巨人", "巨人", "巨人", "Giant", "giant", "", "", " ", " "],
         "secondary_keys": ["巨人", "巨人"], "content": "unchanged"},
        {"id": 7, "keys": ["巨人", "巨人"], "secondary_keys": None},
        {"id": 105, "keys": []},
    ]}}}
    card = save_json(tmp_path / "backfill" / "card.json", original)
    before = card.read_bytes()
    output = deduplicate_keys(card, tmp_path / "deduplicate_keys" / "card.json")
    expected = deepcopy(original)
    expected["data"]["character_book"]["entries"][0]["keys"] = ["丘陵巨人", "巨人", "Giant", "giant", "", " "]
    expected["data"]["character_book"]["entries"][0]["secondary_keys"] = ["巨人"]
    expected["data"]["character_book"]["entries"][1]["keys"] = ["巨人"]
    assert read_json(output) == expected
    assert card.read_bytes() == before


def test_card_outputs_are_reused_without_any_inputs(tmp_path):
    output = tmp_path / "manual.json"
    output.write_text("manual contents", encoding="utf-8")
    assert backfill(tmp_path / "missing.json", tmp_path / "missing", output) == output
    assert deduplicate_keys(tmp_path / "missing.json", output) == output
    assert output.read_text() == "manual contents"
