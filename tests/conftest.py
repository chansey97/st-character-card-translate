import json
from types import SimpleNamespace

import pytest

from st_character_card_translate.common import write_json


class FakeClient:
    def __init__(self, replies=(), responder=None):
        self.replies = iter(replies)
        self.responder = responder
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.closed = False

    def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.responder(kwargs) if self.responder else next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, SimpleNamespace):
            return reply
        content = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content=content, refusal=None),
        )])

    @property
    def requests(self):
        return [json.loads(call["messages"][1]["content"]) for call in self.calls]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True


@pytest.fixture
def fake_client():
    return FakeClient


@pytest.fixture
def save_json():
    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, value)
        return path
    return save


@pytest.fixture
def entity():
    def make(source, translation=None, **overrides):
        return {
            "source": source, "context": source,
            "reasoning": "This term names a character or place.",
            "type": "concept", "subtype": "setting_term",
            "translation": translation if translation is not None else f"译{source}",
            "entity_confidence": 0.5, "type_confidence": 0.6,
            "translation_confidence": 0.7, **overrides,
        }
    return make


@pytest.fixture
def entry():
    def make(id=42, **overrides):
        return {
            "id": id, "name": "Original name", "keys": [], "secondary_keys": [],
            "content": "", "comment": None, **overrides,
        }
    return make


@pytest.fixture
def model_args():
    return {"source_lang": "en", "target_lang": "zh-Hans", "model": "test-model"}


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    from st_character_card_translate import config

    user_dir = tmp_path / "user-config"
    monkeypatch.setattr(config, "user_config_path", lambda *args, **kwargs: user_dir)
    return user_dir / "config.toml"
