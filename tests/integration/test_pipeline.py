import json

import pytest

from st_character_card_translate import cli
from st_character_card_translate.common import read_json


def test_cross_chunk_terms_reach_body_and_keyword_translation(
    tmp_path, save_json, entity, fake_client, monkeypatch, isolated_config,
):
    card = save_json(tmp_path / "card.json", {"data": {"character_book": {"entries": [
        {"id": 1, "name": "Moonshadow City", "keys": ["Moonshadow City"], "secondary_keys": [],
         "content": "The ruler of Moonshadow City is Ailin.", "comment": None},
        {"id": 2, "name": "Ailin", "keys": ["Ailin", "Ailin"], "secondary_keys": ["Ice Mage"],
         "content": "Ailin is a 300-year-old ice mage.", "comment": None},
    ]}}})
    client = fake_client([
        {"entities": [entity("Moonshadow City", "月影城")]},  # Intentionally omit Ailin here.
        {"entities": [entity("Ailin", "艾琳"), entity("Ice Mage", "冰法师")]},
        {"entries": [{"id": 1, "content": "月影城的统治者是艾琳。", "comment": None}]},
        {"entries": [{"id": 2, "content": "艾琳是一位三百岁的冰法师。", "comment": None}]},
    ])
    monkeypatch.setattr(cli, "OpenAI", lambda **kwargs: client)
    arguments = [str(card), "--source-lang", "en", "--chunk-size", "1", "--output-dir", str(tmp_path / "outputs")]
    assert cli.main(arguments) == 0
    task = tmp_path / "outputs" / "card__en_to_zh-Hans"
    first = "data.character_book.entries_000001_000001.json"
    second = "data.character_book.entries_000002_000002.json"
    assert [e["source"] for e in read_json(task / "entities" / first)] == ["Moonshadow City"]
    assert read_json(task / "glossary.json")["Ailin"] == "艾琳"
    assert read_json(task / "glossary_subsets" / first)["glossary"]["Ailin"] == "艾琳"
    assert read_json(task / "glossary_subsets" / second)["keywords_glossary"]["Ailin"] == "艾琳"
    assert client.requests[2]["glossary"]["Ailin"] == "艾琳"
    assert read_json(task / "translations" / second)[0]["keys"] == ["艾琳", "艾琳"]
    assert read_json(task / "backfill" / card.name)["data"]["character_book"]["entries"][1]["keys"] == ["艾琳", "艾琳"]
    assert read_json(task / "deduplicate_keys" / card.name)["data"]["character_book"]["entries"][1]["keys"] == ["艾琳"]
    assert client.closed
    assert cli.main(arguments) == 0
    assert len(client.calls) == 4


def test_eleven_greetings_blank_values_and_noncontinuous_world_ids(
    tmp_path, save_json, entity, fake_client, monkeypatch, isolated_config,
):
    greetings = [f"Greeting {index}" for index in range(11)]
    greetings[3:5] = ["", " \r\n\t"]
    card = save_json(tmp_path / "card.json", {"data": {
        "alternate_greetings": greetings,
        "character_book": {"entries": [
            {"id": id, "content": f"Entry {id}", "keys": [f"Key {id}"]} for id in (42, 7, 105)
        ]},
    }})

    def responder(call):
        request = json.loads(call["messages"][1]["content"])
        name = call["response_format"]["json_schema"]["name"]
        if name == "EntitiesResponse":
            return {"entities": [entity(term) for term in request.get("forced_terms", [])]}
        if name == "TextResponse":
            return {"text": "译" + request["text"]}
        return {"entries": [
            {"id": item["id"], "content": "译" + item["content"], "comment": item["comment"]}
            for item in request["entries"]
        ]}

    client = fake_client(responder=responder)
    monkeypatch.setattr(cli, "OpenAI", lambda **kwargs: client)
    assert cli.main([str(card), "--source-lang", "en", "--chunk-size", "2", "--output-dir", str(tmp_path)]) == 0
    task = tmp_path / "card__en_to_zh-Hans"
    result = read_json(task / "deduplicate_keys" / card.name)["data"]
    assert result["alternate_greetings"] == ["译" + value if value.strip() else value for value in greetings]
    assert [item["id"] for item in result["character_book"]["entries"]] == [42, 7, 105]
    assert len(client.calls) == 22  # Nine greetings and two world chunks, in each model stage.
    for index in (3, 4):
        filename = f"data.alternate_greetings_{index}.json"
        assert read_json(task / "entities" / filename) == []
        assert read_json(task / "translations" / filename) == {"text": greetings[index]}
    assert all("id" not in request and "entries" not in request for request in client.requests if "text" in request)


@pytest.mark.parametrize("data", [{}, {"alternate_greetings": [], "character_book": {"entries": []}}])
def test_empty_card_completes_all_stages(tmp_path, save_json, fake_client, monkeypatch, isolated_config, data):
    card = save_json(tmp_path / "empty.json", {"data": data})
    client = fake_client()
    monkeypatch.setattr(cli, "OpenAI", lambda **kwargs: client)
    assert cli.main([str(card), "--source-lang", "en", "--output-dir", str(tmp_path)]) == 0
    task = tmp_path / "empty__en_to_zh-Hans"
    assert read_json(task / "deduplicate_keys" / card.name) == {"data": data}
    assert read_json(task / "glossary.json") == {}
    for name in ("fields", "entities", "glossary_subsets", "translations", "backfill", "deduplicate_keys"):
        assert (task / name).is_dir()
    assert not client.calls


def test_staged_manual_glossary_edit_controls_translation(
    tmp_path, save_json, fake_client, entity, monkeypatch, isolated_config,
):
    card = save_json(tmp_path / "card.json", {"data": {"description": "Ailin"}})
    client = fake_client([{"entities": [entity("Ailin", "艾琳")]}, {"text": "アーリン"}])
    monkeypatch.setattr(cli, "OpenAI", lambda **kwargs: client)
    args = [str(card), "--source-lang", "en", "--output-dir", str(tmp_path)]
    assert cli.main(args + ["--to-stage", "glossary"]) == 0
    task = tmp_path / "card__en_to_zh-Hans"
    assert not (task / "glossary_subsets").exists()
    save_json(task / "glossary.json", {"Ailin": "アーリン"})
    assert cli.main(args + ["--from-stage", "subsets"]) == 0
    assert client.requests[1]["glossary"] == {"Ailin": "アーリン"}
    assert read_json(task / "deduplicate_keys" / card.name)["data"]["description"] == "アーリン"
