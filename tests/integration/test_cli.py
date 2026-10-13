import io
import subprocess
import sys
from pathlib import Path

import pytest

from st_character_card_translate import cli
from st_character_card_translate.common import read_json


@pytest.mark.parametrize("extra", [
    ["--chunk-size"], ["--chunk-size", "0"], ["--chunk-size", "-1"],
    ["--chunk-size", "1.5"], ["--chunk-size", "2", "3"],
    ["--delay-between-requests", "-1"], ["--delay-between-requests", "nan"],
    ["--delay-between-requests", "inf"], ["--delay-between-requests", "bad"],
    ["--target-lang", ""], ["--target-lang", "zh_Hans"],
    ["--source-lang", "日本語"], ["--source-lang", "../en"],
    ["--from-stage", "translate", "--to-stage", "extract"], ["--to-stage", "unknown"],
])
def test_invalid_arguments_exit_two_without_artifacts(tmp_path, extra, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        cli.main(["card.json", "--source-lang", "en", *extra])
    assert exc.value.code == 2
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("args", [[], ["card.json"], ["--source-lang", "en"]])
def test_required_input_and_source_even_when_resuming(args):
    with pytest.raises(SystemExit) as exc:
        cli.main(args + ["--from-stage", "backfill"])
    assert exc.value.code == 2


def test_parser_defaults_and_language_tags_verbatim():
    args = cli.make_parser().parse_args(["card.json", "--source-lang", "EN-Latn-US-x-custom", "--delay-between-requests", ".25"])
    assert args.chunk_size == 10
    assert args.source_lang == "EN-Latn-US-x-custom"
    assert args.target_lang == "zh-Hans"
    assert args.delay_between_requests == 0.25


def test_help_does_not_read_config_or_create_client(monkeypatch, capsys):
    def unexpected(*args, **kwargs):
        pytest.fail("help must not load config or create client")
    monkeypatch.setattr(cli, "load_config", unexpected)
    monkeypatch.setattr(cli, "OpenAI", unexpected)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "--chunk-size" in capsys.readouterr().out


def test_bad_config_blocks_even_local_stage_before_output(tmp_path, isolated_config, capsys):
    isolated_config.parent.mkdir()
    isolated_config.write_text('[openai]\nmodel=""', encoding="utf-8")
    output = tmp_path / "output"
    assert cli.main(["missing.json", "--source-lang", "en", "--to-stage", "extract", "--output-dir", str(output)]) == 2
    assert not output.exists()
    assert str(isolated_config) in capsys.readouterr().err


@pytest.mark.parametrize("encoding", ["cp1252", "gbk"])
def test_unicode_paths_with_legacy_output_encoding(tmp_path, save_json, isolated_config, monkeypatch, encoding):
    card = save_json(tmp_path / "角色 🪨 card.json", {"data": {"description": "Ailin"}})
    args = [str(card), "--source-lang", "en", "--to-stage", "extract", "--output-dir", str(tmp_path)]
    with (
        io.TextIOWrapper(io.BytesIO(), encoding=encoding) as stdout,
        io.TextIOWrapper(io.BytesIO(), encoding=encoding, errors="backslashreplace") as stderr,
        monkeypatch.context() as streams,
    ):
        streams.setattr(sys, "stdout", stdout)
        streams.setattr(sys, "stderr", stderr)
        assert cli.main(args) == 0
        stdout.flush()
        assert card.stem in stdout.buffer.getvalue().decode("utf-8")

        missing_config = tmp_path / "缺失 🪨.toml"
        assert cli.main([*args, "--config-file", str(missing_config)]) == 2
        stderr.flush()
        assert str(missing_config) in stderr.buffer.getvalue().decode("utf-8")

    task = tmp_path / f"{card.stem}__en_to_zh-Hans"
    assert read_json(task / "fields/data.description.json") == {"text": "Ailin"}


def test_only_requested_stage_runs_and_does_not_create_client(tmp_path, save_json, isolated_config, monkeypatch):
    def unexpected(**kwargs):
        pytest.fail("local stages must not create client")
    monkeypatch.setattr(cli, "OpenAI", unexpected)
    task = tmp_path / "card__en_to_zh-Hans"
    save_json(task / "entities" / "partial.json", [])
    assert cli.main(["card.json", "--source-lang", "en", "--output-dir", str(tmp_path),
                     "--from-stage", "glossary", "--to-stage", "glossary"]) == 0
    assert read_json(task / "glossary.json") == {}
    assert not (task / "fields").exists()
    assert not (task / "glossary_subsets").exists()


@pytest.mark.parametrize("explicit", [False, True])
def test_default_output_and_explicit_dot_match(tmp_path, save_json, isolated_config, monkeypatch, explicit):
    card = save_json(tmp_path / "card.json", {"data": {}})
    monkeypatch.chdir(tmp_path)
    args = [str(card), "--source-lang", "EN", "--to-stage", "extract"]
    assert cli.main(args + (["--output-dir", "./"] if explicit else [])) == 0
    assert (tmp_path / "card__EN_to_zh-Hans" / "fields").is_dir()


def test_missing_upstream_exits_one_and_reports_stage_path(tmp_path, isolated_config, capsys):
    assert cli.main(["card.json", "--source-lang", "en", "--output-dir", str(tmp_path),
                     "--from-stage", "glossary", "--to-stage", "glossary"]) == 1
    error = capsys.readouterr().err
    assert "glossary" in error and "entities" in error


def test_consumed_corrupt_json_fails_and_keeps_prior_outputs(tmp_path, save_json, isolated_config, capsys):
    task = tmp_path / "card__en_to_zh-Hans"
    path = save_json(task / "entities" / "invalid.json", [])
    path.write_text("invalid", encoding="utf-8")
    assert cli.main(["card.json", "--source-lang", "en", "--output-dir", str(tmp_path),
                     "--from-stage", "glossary", "--to-stage", "glossary"]) == 1
    assert str(path) in capsys.readouterr().err
    assert path.read_text() == "invalid"
    assert not (task / "glossary.json").exists()


def test_clients_use_config_and_reuse_does_not_wait(
    tmp_path, save_json, fake_client, isolated_config, monkeypatch,
):
    from st_character_card_translate import llm

    card = save_json(tmp_path / "card.json", {"data": {"description": "Hello"}})
    config_file = tmp_path / "explicit.toml"
    config_file.write_text('[openai]\nmodel="chosen"\nmax_retries=0\n', encoding="utf-8")
    client = fake_client([{"entities": []}, {"text": "你好"}])
    created, waits = [], []

    def create(**kwargs):
        created.append(kwargs)
        return client

    monkeypatch.setattr(cli, "OpenAI", create)
    monkeypatch.setattr(llm.time, "sleep", waits.append)
    args = [str(card), "--source-lang", "en", "--output-dir", str(tmp_path),
            "--config-file", str(config_file), "--delay-between-requests", ".1"]
    assert cli.main(args) == 0
    assert created == [{"base_url": "http://127.0.0.1:8317/v1", "api_key": "123456", "max_retries": 0}]
    assert waits == [0.1, 0.1]
    assert all(call["model"] == "chosen" for call in client.calls)
    assert cli.main(args) == 0
    assert waits == [0.1, 0.1]


def test_both_installed_entrypoints_have_same_help():
    module = subprocess.run([sys.executable, "-m", "st_character_card_translate", "--help"], capture_output=True, text=True)
    executable = Path(sys.executable).parent / ("st-character-card-translate.exe" if sys.platform == "win32" else "st-character-card-translate")
    console = subprocess.run([str(executable), "--help"], capture_output=True, text=True)
    assert module.returncode == console.returncode == 0
    assert module.stdout == console.stdout
