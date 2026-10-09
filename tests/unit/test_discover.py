import pytest

from st_character_card_translate.common import StageError, read_json
from st_character_card_translate.phase_discover_entities import discover_entities

WORLD = "data.character_book.entries_000001_000003.json"


def test_forced_terms_are_exact_stable_and_have_nine_fields(
    tmp_path, save_json, entry, entity, fake_client, model_args,
):
    terms = ["Ailin", "ailin", " Ailin ", "Silver"]
    save_json(tmp_path / "fields" / WORLD, [
        entry(keys=["Ailin", "ailin", "", " Ailin ", "Ailin"], secondary_keys=[" ", "Silver"]),
        entry(7, keys=["Silver"]),
    ])
    client = fake_client([{"entities": [entity(term) for term in terms]}])
    outputs = discover_entities(tmp_path / "fields", tmp_path / "entities", client=client, **model_args)
    request = client.requests[0]
    assert request["forced_terms"] == terms
    assert set(request) == {"source_lang", "target_lang", "background", "forced_terms", "entries"}
    assert all(set(item) == {"id", "name", "content", "comment"} for item in request["entries"])
    assert [item["source"] for item in read_json(outputs[0])] == terms
    assert all(len(item) == 9 and item["entity_confidence"] == 1.0 for item in read_json(outputs[0]))
    assert "forced_terms" in client.calls[0]["messages"][0]["content"]
    assert all(item["type_confidence"] == 0.6 for item in read_json(outputs[0]))


def test_missing_forced_term_stops_without_current_output_or_next_call(
    tmp_path, save_json, entry, entity, fake_client, model_args,
):
    save_json(tmp_path / "fields" / WORLD, [entry(keys=[" Ailin "])])
    save_json(tmp_path / "fields" / "data.description.json", {"text": "another request"})
    client = fake_client([{"entities": [entity("Ailin")]}])
    with pytest.raises(StageError, match="Missing forced terms") as exc:
        discover_entities(tmp_path / "fields", tmp_path / "entities", client=client, **model_args)
    assert WORLD in str(exc.value)
    assert not list((tmp_path / "entities").iterdir())
    assert len(client.calls) == 1


def test_each_greeting_uses_plain_text_contract(tmp_path, save_json, fake_client, model_args):
    fields = tmp_path / "fields"
    for index in range(11):
        save_json(fields / f"data.alternate_greetings_{index}.json", {"text": f"greeting {index}"})
    save_json(fields / "data.description.json", {"text": "description"})
    client = fake_client([{"entities": []}] * 12)
    discover_entities(fields, tmp_path / "entities", client=client, **model_args)
    assert len(client.calls) == 12
    assert len({call["messages"][0]["content"] for call in client.calls}) == 1
    assert all(set(request) == {"source_lang", "target_lang", "background", "text"} for request in client.requests)
    assert all("forced_terms" not in call["messages"][0]["content"] for call in client.calls)
    assert [request["text"] for request in client.requests[:4]] == ["greeting 0", "greeting 1", "greeting 10", "greeting 2"]


def test_world_with_body_but_no_keywords_sends_empty_forced_terms(
    tmp_path, save_json, entry, fake_client, model_args,
):
    save_json(tmp_path / "fields" / WORLD, [entry(content="Story", keys=["", " "])])
    client = fake_client([{"entities": []}])
    discover_entities(tmp_path / "fields", tmp_path / "entities", client=client, **model_args)
    assert client.requests[0]["forced_terms"] == []


def test_empty_text_skips_model_and_background(tmp_path, save_json, entry, fake_client, model_args):
    fields = tmp_path / "fields"
    save_json(fields / "data.description.json", {"text": ""})
    save_json(fields / "data.alternate_greetings_0.json", {"text": " \r\n\t"})
    save_json(fields / WORLD, [entry(content=None, comment=" ", name="Name is not a source", keys=["", " "])])
    client = fake_client()
    outputs = discover_entities(
        fields, tmp_path / "entities", client=client,
        background_path=tmp_path / "absent.txt", **model_args,
    )
    assert all(read_json(path) == [] for path in outputs)
    assert not client.calls


def test_background_utf8_bom_and_reuse(tmp_path, save_json, fake_client, model_args):
    field = save_json(tmp_path / "fields" / "data.description.json", {"text": "Text"})
    background = tmp_path / "background.txt"
    background.write_text("背景\n", encoding="utf-8-sig")
    client = fake_client([{"entities": []}])
    output = discover_entities(
        field.parent, tmp_path / "entities", client=client, background_path=background, **model_args,
    )[0]
    assert client.requests[0]["background"] == "背景\n"
    output.write_text("invalid json", encoding="utf-8")
    field.write_text("also invalid", encoding="utf-8")
    discover_entities(field.parent, output.parent, client=client, **model_args)
    assert len(client.calls) == 1
    assert output.read_text() == "invalid json"
