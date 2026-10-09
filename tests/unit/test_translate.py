import pytest

from st_character_card_translate.common import StageError, read_json
from st_character_card_translate.phase_translate import translate

WORLD = "data.character_book.entries_000001_000003.json"


def prepare(save_json, root, name, field, glossary=None, keywords=None):
    save_json(root / "fields" / name, field)
    save_json(root / "subsets" / name, {"glossary": glossary or {}, "keywords_glossary": keywords or {}})


@pytest.mark.parametrize("keep", [False, True])
def test_modes_use_only_body_dictionary_and_preserve_keyword_order(
    tmp_path, save_json, entry, fake_client, model_args, keep,
):
    field = [entry(
        keys=["Ailin", "Ailin", "OnlyKey", "", " "], secondary_keys=["Second", "Ailin"],
        content="Ailin lives here", comment=None,
    )]
    body_glossary = {"Ailin": "正文名字", "manual term": "別の言語"}
    keywords = {"Ailin": "关键词名字", "OnlyKey": "仅关键词", "Second": "次关键词"}
    prepare(save_json, tmp_path, WORLD, field, body_glossary, keywords)
    client = fake_client([{"entries": [{"id": 42, "content": "正文名字住在这里", "comment": None}]}])
    output = translate(
        tmp_path / "fields", tmp_path / "subsets", tmp_path / "translations",
        client=client, no_translate_glossary=keep, **model_args,
    )[0]
    request = client.requests[0]
    assert request["entries"] == [{"id": 42, "content": "Ailin lives here", "comment": None}]
    assert "keywords_glossary" not in request
    assert "OnlyKey" not in str(request)
    result = read_json(output)[0]
    assert result["id"] == 42
    assert result["name"] == "Original name"
    if keep:
        assert request["do_not_translate_terms"] == ["Ailin", "manual term"]
        assert "glossary" not in request
        assert result["keys"] == field[0]["keys"]
        assert result["secondary_keys"] == field[0]["secondary_keys"]
    else:
        assert request["glossary"] == body_glossary
        assert "do_not_translate_terms" not in request
        assert result["keys"] == ["关键词名字", "关键词名字", "仅关键词", "", " "]
        assert result["secondary_keys"] == ["次关键词", "关键词名字"]


@pytest.mark.parametrize("keep", [False, True])
def test_no_body_match_still_translates_keys_with_empty_terms_request(
    tmp_path, save_json, entry, fake_client, model_args, keep,
):
    prepare(save_json, tmp_path, WORLD, [entry(content="An ordinary sentence", keys=["Secret"], secondary_keys=["Other"])],
            keywords={"Secret": "秘密", "Other": "其他"})
    client = fake_client([{"entries": [{"id": 42, "content": "一句话", "comment": None}]}])
    output = translate(tmp_path / "fields", tmp_path / "subsets", tmp_path / "translations",
                       client=client, no_translate_glossary=keep, **model_args)[0]
    assert client.requests[0].get("do_not_translate_terms" if keep else "glossary") == ([] if keep else {})
    assert read_json(output)[0]["keys"] == (["Secret"] if keep else ["秘密"])


@pytest.mark.parametrize("keep", [False, True])
def test_no_body_still_reads_subset_and_replaces_keywords(
    tmp_path, save_json, entry, fake_client, model_args, keep,
):
    original = [entry(keys=["A", "", " "], secondary_keys=None, content=" \r\n", comment=None)]
    prepare(save_json, tmp_path, WORLD, original, keywords={} if keep else {"A": "甲"})
    client = fake_client()
    output = translate(tmp_path / "fields", tmp_path / "subsets", tmp_path / "translations",
                       client=client, no_translate_glossary=keep, **model_args)[0]
    result = read_json(output)[0]
    assert result["keys"] == (["A", "", " "] if keep else ["甲", "", " "])
    assert result["secondary_keys"] is None
    assert result["content"] == " \r\n"
    assert result["comment"] is None
    assert not client.calls


def test_missing_mapping_fails_but_keep_mode_ignores_keyword_values(
    tmp_path, save_json, entry, fake_client, model_args,
):
    prepare(save_json, tmp_path, WORLD, [entry(keys=["Unmapped"])])
    client = fake_client()
    with pytest.raises(StageError, match="Unmapped"):
        translate(tmp_path / "fields", tmp_path / "subsets", tmp_path / "translations", client=client, **model_args)
    assert not list((tmp_path / "translations").iterdir())
    translate(tmp_path / "fields", tmp_path / "subsets", tmp_path / "translations",
              client=client, no_translate_glossary=True, **model_args)
    assert not client.calls


@pytest.mark.parametrize("failure", ["too_few", "too_many", "swapped", "wrong_id", "null_removed", "null_added"])
def test_world_response_alignment_failure_stops_and_keeps_previous_outputs(
    tmp_path, save_json, entry, fake_client, model_args, failure,
):
    source = [entry(id, content=f"body {id}") for id in (42, 7, 105)]
    prepare(save_json, tmp_path, WORLD, source)
    prepare(save_json, tmp_path, "data.description.json", {"text": "later"})
    earlier = save_json(tmp_path / "translations" / "data.alternate_greetings_0.json", {"text": "existing"})
    response = [{"id": id, "content": f"译文 {id}", "comment": None} for id in (42, 7, 105)]
    if failure == "too_few":
        response.pop()
        response[0]["id"] = -99  # Count failure must win over id mismatch.
    elif failure == "too_many":
        response.append(response[0])
    elif failure == "swapped":
        response[0], response[1] = response[1], response[0]
    elif failure == "wrong_id":
        response[0]["id"] = 99
    elif failure == "null_removed":
        response[0]["comment"] = ""
    else:
        response[0]["content"] = None
    client = fake_client([{"entries": response}])
    match = "Expected" if failure in ("too_few", "too_many") else "mismatch"
    with pytest.raises(StageError, match=match) as exc:
        translate(tmp_path / "fields", tmp_path / "subsets", tmp_path / "translations", client=client, **model_args)
    assert WORLD in str(exc.value)
    assert list((tmp_path / "translations").iterdir()) == [earlier]
    assert read_json(earlier) == {"text": "existing"}
    assert len(client.calls) == 1


def test_restore_blank_world_bodies_after_response(tmp_path, save_json, entry, fake_client, model_args):
    source = [entry(content="content", comment=" \t\r\n"), entry(7, content="", comment=None)]
    prepare(save_json, tmp_path, WORLD, source)
    client = fake_client([{"entries": [
        {"id": 42, "content": "正文", "comment": "model changed whitespace"},
        {"id": 7, "content": "invented text", "comment": None},
    ]}])
    output = translate(tmp_path / "fields", tmp_path / "subsets", tmp_path / "translations", client=client, **model_args)[0]
    result = read_json(output)
    assert result[0]["comment"] == " \t\r\n"
    assert result[1]["content"] == ""
    assert result[1]["keys"] == []


@pytest.mark.parametrize("value", ["", " \r\n\t", None])
def test_blank_plain_text_copies_value_but_requires_subset(
    tmp_path, save_json, fake_client, model_args, value,
):
    name = "data.alternate_greetings_0.json"
    save_json(tmp_path / "fields" / name, {"text": value})
    client = fake_client()
    with pytest.raises(StageError, match="subsets"):
        translate(tmp_path / "fields", tmp_path / "subsets", tmp_path / "translations", client=client, **model_args)
    save_json(tmp_path / "subsets" / name, {"glossary": {}, "keywords_glossary": {}})
    output = translate(tmp_path / "fields", tmp_path / "subsets", tmp_path / "translations", client=client, **model_args)[0]
    assert read_json(output) == {"text": value}
    assert not client.calls


def test_greetings_and_normal_fields_share_contract(tmp_path, save_json, fake_client, model_args):
    for name in ("data.description.json", "data.alternate_greetings_10.json"):
        prepare(save_json, tmp_path, name, {"text": "Ailin"}, {"Ailin": "艾琳"})
    client = fake_client([{"text": "艾琳"}] * 2)
    translate(tmp_path / "fields", tmp_path / "subsets", tmp_path / "translations", client=client, **model_args)
    assert client.calls[0] == client.calls[1]
    assert set(client.requests[0]) == {"source_lang", "target_lang", "background", "glossary", "text"}
    assert "id" not in client.requests[0]


def test_existing_translation_skips_corrupt_source_and_missing_subset(tmp_path, save_json, fake_client, model_args):
    field = save_json(tmp_path / "fields" / "data.description.json", {})
    field.write_text("invalid", encoding="utf-8")
    output = save_json(tmp_path / "translations" / field.name, {})
    output.write_text("manual edit", encoding="utf-8")
    client = fake_client()
    assert translate(field.parent, tmp_path / "missing", output.parent, client=client, **model_args) == [output]
    assert output.read_text() == "manual edit"
    assert not client.calls
