"""Run explicitly after build_portable.bat; no external API is contacted."""

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zipfile import ZipFile

import pytest

from st_character_card_translate.common import read_json

PROJECT = Path(__file__).resolve().parents[2]


@pytest.fixture
def portable(tmp_path):
    archive_path = PROJECT / "dist" / "st-character-card-translate-windows-x64.zip"
    assert archive_path.is_file(), "Run build_portable.bat before the portable tests"
    with ZipFile(archive_path) as archive:
        archive.extractall(tmp_path / "解压 目录")
    app = tmp_path / "解压 目录" / "st-character-card-translate"
    defaults = (PROJECT / "src/st_character_card_translate/config.default.toml").read_bytes()
    assert (app / "config.toml").read_bytes() == defaults
    assert (app / "_internal/st_character_card_translate/config.default.toml").read_bytes() == defaults
    assert (app / "README.md").read_bytes() == (PROJECT / "README.md").read_bytes()
    assert not (app / "PLAN.md").exists()
    assert list((app / "_internal").glob("python3*.dll"))

    cwd = tmp_path / "working directory"
    cwd.mkdir()
    (cwd / "config.toml").write_text("invalid cwd config", encoding="utf-8")
    env = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        env.pop(name, None)
    env["PATH"] = str(Path(env["SYSTEMROOT"]) / "System32")
    env["NO_PROXY"] = "127.0.0.1,localhost"
    for name in ("LOCALAPPDATA", "APPDATA"):
        env[name] = str(tmp_path / name)
        user_config = Path(env[name]) / "st-character-card-translate" / "config.toml"
        user_config.parent.mkdir(parents=True)
        user_config.write_text("invalid user config", encoding="utf-8")

    def run(*args, expected=0):
        result = subprocess.run(
            [str(app / "st-character-card-translate.exe"), *map(str, args)],
            cwd=cwd, env=env, capture_output=True, encoding="utf-8", timeout=60,
        )
        assert result.returncode == expected, result.stdout + result.stderr
        return result

    return app, cwd, run


def test_portable_packaged_defaults_and_config_errors(portable, save_json):
    app, cwd, run = portable
    card = save_json(cwd / "card.json", {"data": {"description": "Ailin"}})
    arguments = [card, "--source-lang", "en", "--to-stage", "extract"]
    local_config = app / "config.toml"
    local_config.write_text('[openai]\nmodel=42\n', encoding="utf-8")
    assert "--source-lang" in run("--help").stdout
    error = run(*arguments, expected=2).stderr
    assert "Configuration error:" in error
    assert str(local_config) in error
    explicit = cwd / "explicit.toml"
    explicit.write_text('[openai]\nmodel="valid"\n', encoding="utf-8")
    run(*arguments, "--config-file", explicit, expected=2)
    assert not (cwd / "card__en_to_zh-Hans").exists()

    local_config.unlink()
    run(*arguments)
    assert read_json(cwd / "card__en_to_zh-Hans/fields/data.description.json") == {"text": "Ailin"}
    assert not local_config.exists()
    run(*arguments, "--config-file", cwd / "missing.toml", expected=2)


def test_portable_full_pipeline_and_explicit_override(portable, save_json, entity):
    app, cwd, run = portable
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, self.headers.get("Authorization"), body))
            request = json.loads(body["messages"][1]["content"])
            schema = body["response_format"]["json_schema"]["name"]
            if schema == "EntitiesResponse":
                content = {"entities": [entity("Ailin", "艾琳")]}
            elif schema == "TextResponse":
                content = {"text": "艾琳"}
            else:
                content = {"entries": [
                    {"id": item["id"], "content": "艾琳居住在这里。", "comment": item["comment"]}
                    for item in request["entries"]
                ]}
            response = json.dumps({
                "id": "portable-test", "object": "chat.completion", "created": 0, "model": body["model"],
                "choices": [{"index": 0, "finish_reason": "stop", "message": {
                    "role": "assistant", "content": json.dumps(content, ensure_ascii=False),
                }}],
            }, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *args):
            pass

    card = save_json(cwd / "角色 🪨 card.json", {"data": {
        "description": "Ailin", "extensions": {"keep": True},
        "character_book": {"entries": [{
            "id": 42, "name": "Original name", "keys": ["Ailin", "Ailin"], "secondary_keys": [],
            "content": "Ailin lives here.", "comment": None,
        }]},
    }})
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        (app / "config.toml").write_text(
            f'[openai]\nbase_url="http://127.0.0.1:{server.server_port}/v1"\n'
            'api_key="portable-key"\nmodel="portable-model"\nmax_retries=0\n', encoding="utf-8",
        )
        explicit = cwd / "explicit.toml"
        explicit.write_text('[openai]\nmodel="explicit-model"\n', encoding="utf-8")
        for mode in ("portable", "explicit"):
            args = [card, "--source-lang", "en", "--output-dir", mode]
            if mode == "explicit":
                args += ["--config-file", explicit.name]
            completed = run(*args)
            assert "Completed:" in completed.stdout
            assert card.name in completed.stdout
            task = cwd / mode / f"{card.stem}__en_to_zh-Hans"
            result = read_json(task / "deduplicate_keys" / card.name)["data"]
            assert result["description"] == "艾琳"
            assert result["extensions"] == {"keep": True}
            world = result["character_book"]["entries"][0]
            assert world["id"] == 42
            assert world["name"] == "Original name"
            assert world["keys"] == ["艾琳"]
            assert world["content"] == "艾琳居住在这里。"
            assert read_json(task / "glossary.json")["Ailin"] == "艾琳"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert len(calls) == 8
    assert [body["model"] for _, _, body in calls] == ["portable-model"] * 4 + ["explicit-model"] * 4
    for path, authorization, body in calls:
        assert path == "/v1/chat/completions"
        assert authorization == "Bearer portable-key"
        assert body["stream"] is False
        assert body["response_format"]["json_schema"]["strict"] is True
