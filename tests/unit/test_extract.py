import json
from pathlib import Path

import pytest

from st_character_card_translate.common import StageError, entry_filename, read_json
from st_character_card_translate.phase_extract_fields import extract_fields


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "gb18030"])
def test_input_encoding_and_output_format(tmp_path, encoding):
    card = tmp_path / "card.json"
    value = "月影城\r\n  Ailin\n"
    card.write_text(json.dumps({"data": {"description": value}}, ensure_ascii=False), encoding=encoding)
    paths = extract_fields(card, tmp_path / "fields", input_encoding=encoding)
    assert read_json(paths[0]) == {"text": value}
    raw = paths[0].read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw
    assert "月影城".encode() in raw
    assert b'\n  "text": ' in raw


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig"])
def test_default_decoder_accepts_both_utf8_forms(tmp_path, encoding):
    card = tmp_path / "card.json"
    card.write_text('{"data": {"description": "test"}}', encoding=encoding)
    assert read_json(extract_fields(card, tmp_path / "fields")[0]) == {"text": "test"}


def test_chunking_and_greetings_use_positions(tmp_path, save_json):
    greetings = [f"Greeting {index}" for index in range(11)]
    greetings[3:5] = ["", " \r\n\t"]
    card = save_json(tmp_path / "card.json", {"data": {
        "alternate_greetings": greetings,
        "character_book": {"entries": [
            {"id": 42, "keys": [], "content": "one"},
            {"id": 7, "name": None, "secondary_keys": None, "comment": ""},
            {"id": 105, "content": " \n"},
        ]},
    }})
    for size in (1, 2, 10):
        directory = tmp_path / f"fields-{size}"
        paths = extract_fields(card, directory, chunk_size=size)
        for index, greeting in enumerate(greetings):
            assert read_json(directory / f"data.alternate_greetings_{index}.json") == {"text": greeting}
        chunks = sorted(path for path in paths if "entries_" in path.name)
        assert len(chunks) == (3 + size - 1) // size
        entries = [entry for path in chunks for entry in read_json(path)]
        assert [entry["id"] for entry in entries] == [42, 7, 105]
        assert all(list(entry) == ["id", "name", "keys", "secondary_keys", "content", "comment"] for entry in entries)
        assert entries[0]["comment"] is None
        assert entries[0]["keys"] == []
        assert entries[1]["comment"] == ""
    assert (tmp_path / "fields-2" / "data.character_book.entries_000003_000003.json").exists()


def test_entry_number_width():
    assert entry_filename(1, 10, 71) == "data.character_book.entries_000001_000010.json"
    assert entry_filename(999999, 1000000, 1000000) == "data.character_book.entries_0999999_1000000.json"


@pytest.mark.parametrize("data", [
    {}, {"alternate_greetings": []}, {"character_book": {"entries": []}},
    {"alternate_greetings": None, "character_book": None},
])
def test_empty_arrays_and_absent_fields(tmp_path, save_json, data):
    card = save_json(tmp_path / "card.json", {"data": data})
    fields = tmp_path / "fields"
    assert extract_fields(card, fields) == []
    assert fields.is_dir()


def test_null_empty_and_blank_remain_distinct(tmp_path, save_json):
    card = save_json(tmp_path / "card.json", {"data": {
        "description": None, "personality": "", "scenario": " \t",
    }})
    paths = extract_fields(card, tmp_path / "fields")
    assert [read_json(path)["text"] for path in paths] == [None, "", " \t"]


@pytest.mark.parametrize("card", [
    {}, [], {"data": []}, {"data": {}, "spec": "chara_card_v3"},
    {"data": {}, "spec_version": "1.0"}, {"data": {}, "spec_version": "3.0"},
])
def test_rejects_other_card_versions(tmp_path, save_json, card):
    path = save_json(tmp_path / "card.json", card)
    with pytest.raises(StageError, match="extract"):
        extract_fields(path, tmp_path / "fields")


@pytest.mark.parametrize("key", ["keys", "secondary_keys"])
@pytest.mark.parametrize("term", ["/Ailin/i", "/foo/", "/a.b/gim", "//"])
def test_rejects_regex_before_writing_any_fields(tmp_path, save_json, key, term):
    card = save_json(tmp_path / "card.json", {"data": {
        "description": "ordinary text",
        "character_book": {"entries": [{"id": 7, key: [term]}]},
    }})
    fields = tmp_path / "fields"
    existing = save_json(fields / "manual.json", {"edited": True})
    before = existing.read_bytes()
    with pytest.raises(StageError, match=f"position 1, {key}"):
        extract_fields(card, fields)
    assert list(fields.iterdir()) == [existing]
    assert existing.read_bytes() == before


def test_regex_in_body_and_partial_keyword_are_allowed(tmp_path, save_json):
    card = save_json(tmp_path / "card.json", {"data": {
        "description": "Example: /Ailin/i",
        "character_book": {"entries": [{"id": 1, "keys": ["use /pattern/i", "https://example.com"]}]},
    }})
    assert len(extract_fields(card, tmp_path / "fields")) == 2


def test_existing_output_is_not_read_or_overwritten(tmp_path, save_json):
    card = save_json(tmp_path / "card.json", {"data": {"description": "source"}})
    existing = save_json(tmp_path / "fields" / "data.description.json", {})
    existing.write_text("not json", encoding="utf-8")
    assert extract_fields(card, existing.parent) == [existing]
    assert existing.read_text() == "not json"


def test_real_example_shape(tmp_path):
    card = Path(__file__).resolve().parents[2] / "examples" / "main_the-shining-stone-3ab47f90d0c6_json.json"
    paths = extract_fields(card, tmp_path / "fields")
    world = [path for path in paths if "entries_" in path.name]
    greetings = [path for path in paths if "alternate_greetings_" in path.name]
    assert len(world) == 8
    assert world[-1].name == "data.character_book.entries_000071_000071.json"
    assert sum(len(read_json(path)) for path in world) == 71
    assert [path.name for path in greetings] == ["data.alternate_greetings_0.json", "data.alternate_greetings_1.json"]
