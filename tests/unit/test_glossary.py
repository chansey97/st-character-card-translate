import pytest

from st_character_card_translate.common import StageError, read_json
from st_character_card_translate.phase_build_glossary import build_glossary
from st_character_card_translate.phase_generate_glossary_subsets import generate_glossary_subsets

WORLD = "data.character_book.entries_000001_000002.json"


def test_glossary_average_score_ties_case_and_sorted_keys(tmp_path, save_json, entity):
    save_json(tmp_path / "entities" / "b.json", [
        entity("Ailin", "winner", entity_confidence=0.9, type_confidence=0.9, translation_confidence=0.9),
        entity("Rose", "later tie"), entity("Rose", "later within file"),
    ])
    save_json(tmp_path / "entities" / "a.json", [
        entity("Ailin", "loser", entity_confidence=1, type_confidence=0, translation_confidence=0),
        entity("rose", "lowercase"), entity("Rose", "first tie"),
    ])
    output = build_glossary(tmp_path / "entities", tmp_path / "glossary.json")
    assert read_json(output) == {"Ailin": "winner", "Rose": "first tie", "rose": "lowercase"}
    assert list(read_json(output)) == ["Ailin", "Rose", "rose"]


def test_glossary_empty_and_only_existing_entities(tmp_path, save_json):
    save_json(tmp_path / "entities" / "only.json", [])
    assert read_json(build_glossary(tmp_path / "entities", tmp_path / "glossary.json")) == {}


def test_existing_glossary_skips_missing_upstream(tmp_path):
    output = tmp_path / "glossary.json"
    output.write_text("invalid", encoding="utf-8")
    assert build_glossary(tmp_path / "missing", output) == output
    assert output.read_text() == "invalid"


def test_matching_casefold_overlap_cjk_short_terms_and_no_cross_text_join(tmp_path, save_json, entry):
    glossary = save_json(tmp_path / "glossary.json", {
        source: source for source in (
            "Moonshadow City", "Moonshadow", "moonshadow", "Ann", "Orc", "月影", "魔法", "STRASSE",
            "OnlyKeyword", "OnlySecondary", "OnlyName", "CrossBoundary", "", "  ",
        )
    })
    save_json(tmp_path / "fields" / WORLD, [
        entry(name="OnlyName", keys=["OnlyKeyword"], secondary_keys=["OnlySecondary"],
              content="Moonshadow City: Anna, force, 月影城、魔法使い Straße", comment="Cross"),
        entry(7, content="Boundary"),
    ])
    paths = generate_glossary_subsets(tmp_path / "fields", glossary, tmp_path / "subsets")
    result = read_json(paths[0])
    assert set(result) == {"glossary", "keywords_glossary"}
    assert set(result["glossary"]) == {"Moonshadow City", "Moonshadow", "moonshadow", "Ann", "Orc", "月影", "魔法", "STRASSE"}
    assert list(result["glossary"]) == sorted(result["glossary"])
    assert result["keywords_glossary"] == {"OnlyKeyword": "OnlyKeyword", "OnlySecondary": "OnlySecondary"}


def test_manual_glossary_values_and_empty_subset_structure(tmp_path, save_json, entry):
    glossary = save_json(tmp_path / "glossary.json", {"Ailin": "Ailin", "Moonshadow": "月影の街"})
    save_json(tmp_path / "fields" / "data.description.json", {"text": "Ailin Moonshadow"})
    save_json(tmp_path / "fields" / "data.personality.json", {"text": ""})
    save_json(tmp_path / "fields" / WORLD, [entry(content=None, keys=[" ", ""])])
    generate_glossary_subsets(tmp_path / "fields", glossary, tmp_path / "subsets")
    assert read_json(tmp_path / "subsets" / "data.description.json") == {
        "glossary": {"Ailin": "Ailin", "Moonshadow": "月影の街"}, "keywords_glossary": {},
    }
    for name in ("data.personality.json", WORLD):
        assert read_json(tmp_path / "subsets" / name) == {"glossary": {}, "keywords_glossary": {}}


def test_keywords_use_exact_keys_and_overlaps_share_global_translation(tmp_path, save_json, entry):
    glossary = save_json(tmp_path / "glossary.json", {"Ailin": "艾琳", " Ailin ": " 艾琳 "})
    save_json(tmp_path / "fields" / WORLD, [entry(keys=[" Ailin ", "Ailin", "Ailin"], content="Ailin")])
    output = generate_glossary_subsets(tmp_path / "fields", glossary, tmp_path / "subsets")[0]
    subset = read_json(output)
    assert subset["glossary"] == {"Ailin": "艾琳"}
    assert subset["keywords_glossary"] == {" Ailin ": " 艾琳 ", "Ailin": "艾琳"}


def test_missing_keyword_mapping_fails_without_output(tmp_path, save_json, entry):
    glossary = save_json(tmp_path / "glossary.json", {"Ailin": "艾琳"})
    save_json(tmp_path / "fields" / WORLD, [entry(keys=["ailin"])])
    with pytest.raises(StageError, match="ailin"):
        generate_glossary_subsets(tmp_path / "fields", glossary, tmp_path / "subsets")
    assert not list((tmp_path / "subsets").iterdir())


def test_subsets_skip_without_reading_corrupt_inputs(tmp_path, save_json):
    field = save_json(tmp_path / "fields" / "data.description.json", {})
    field.write_text("bad json", encoding="utf-8")
    output = save_json(tmp_path / "subsets" / field.name, {})
    output.write_text("edited", encoding="utf-8")
    assert generate_glossary_subsets(field.parent, tmp_path / "missing.json", output.parent) == [output]
    assert output.read_text() == "edited"
