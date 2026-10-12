from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from st_character_card_translate import llm
from st_character_card_translate.schemas import EntitiesResponse, EntriesResponse, TextResponse


def test_request_contract_and_wait_before_first_and_each_call(fake_client, monkeypatch):
    events = []

    def respond(call):
        events.append("call")
        assert set(call) == {"model", "stream", "messages", "response_format", "reasoning_effort"}
        assert call["reasoning_effort"] == "none"
        assert call["stream"] is False
        assert call["response_format"]["type"] == "json_schema"
        assert call["response_format"]["json_schema"]["strict"] is True
        assert "月影" in call["messages"][1]["content"]
        return {"text": "translated"}

    client = fake_client(responder=respond)
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: events.append(seconds))
    for _ in range(2):
        assert llm.request_json(client, "model", "prompt", {"text": "月影"}, TextResponse, 0.125) == {"text": "translated"}
    assert events == [0.125, "call", 0.125, "call"]


@pytest.mark.parametrize("schema", [TextResponse, EntriesResponse, EntitiesResponse])
def test_every_schema_object_has_only_required_fields(schema):
    def check(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for child in node.values():
                check(child)
        elif isinstance(node, list):
            for child in node:
                check(child)
    check(schema.model_json_schema())


@pytest.mark.parametrize("reply", [
    "not json", "```json\n{\"text\": \"hi\"}\n```", {"text": None},
    {"text": 42}, {"text": "hi", "extra": True}, {},
])
def test_invalid_model_responses_are_rejected_without_retries(fake_client, reply):
    client = fake_client([reply])
    with pytest.raises(ValidationError):
        llm.request_json(client, "model", "prompt", {}, TextResponse)
    assert len(client.calls) == 1


@pytest.mark.parametrize("kind", ["length", "content_filter", "no_choices", "no_content", "refusal", "transport"])
def test_abnormal_model_completion_fails(fake_client, kind):
    message = SimpleNamespace(content='{"text": "ok"}', refusal=None)
    reply = SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=message)])
    if kind in ("length", "content_filter"):
        reply.choices[0].finish_reason = kind
    elif kind == "no_choices":
        reply.choices = []
    elif kind == "no_content":
        message.content = None
    elif kind == "refusal":
        message.refusal = "refused"
    else:
        reply = RuntimeError("transport failed")
    client = fake_client([reply])
    with pytest.raises((ValueError, RuntimeError)):
        llm.request_json(client, "model", "prompt", {}, TextResponse)
    assert len(client.calls) == 1


@pytest.mark.parametrize("score", [-0.1, 1.1, "0.5", float("nan")])
def test_entity_confidence_bounds_and_types(entity, score):
    with pytest.raises(ValidationError):
        EntitiesResponse.model_validate({"entities": [entity("A", entity_confidence=score)]})


def test_id_must_be_integer_and_nullable_fields_are_required():
    for entry in (
        {"id": "42", "content": None, "comment": None},
        {"id": True, "content": None, "comment": None},
        {"id": 42, "content": None},
    ):
        with pytest.raises(ValidationError):
            EntriesResponse.model_validate({"entries": [entry]})
