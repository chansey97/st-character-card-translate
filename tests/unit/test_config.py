import pytest

from st_character_card_translate import config
from st_character_card_translate.config import ConfigError, load_config


def test_layered_overrides_allow_zero_retries(tmp_path, isolated_config):
    isolated_config.parent.mkdir()
    isolated_config.write_text('[openai]\nmodel = "user-model"\nmax_retries = 0\n', encoding="utf-8")
    explicit = tmp_path / "explicit.toml"
    explicit.write_text('[openai]\nbase_url = "http://localhost:9000/v1"\n', encoding="utf-8")
    settings = load_config(explicit)
    assert settings.model == "user-model"
    assert settings.max_retries == 0
    assert settings.base_url == "http://localhost:9000/v1"
    assert settings.api_key == "123456"


def test_defaults_do_not_create_user_config_or_load_cwd_or_env(tmp_path, isolated_config, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text("invalid", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "environment-must-not-override")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://wrong.invalid")
    settings = load_config()
    assert settings.api_key == "123456"
    assert settings.base_url == "http://127.0.0.1:8317/v1"
    assert settings.model == "gemini-3.8-flash-high"
    assert settings.max_retries == 2
    assert not isolated_config.parent.exists()


@pytest.mark.parametrize("contents", [
    "[other]\nx=1", "[openai]\nunknown=1", "[openai]\nmodel=42",
    '[openai]\napi_key=""', '[openai]\nbase_url="  "',
    "[openai]\nmax_retries=true", "[openai]\nmax_retries=-1",
    "[openai]\nmax_retries=1.5", '[openai]\nmax_retries="2"',
    "openai=42", "[openai", "[openai.model]\nx=1",
])
def test_each_invalid_lower_layer_fails_before_valid_override(tmp_path, isolated_config, contents):
    isolated_config.parent.mkdir()
    isolated_config.write_text(contents, encoding="utf-8")
    explicit = tmp_path / "valid.toml"
    explicit.write_text('[openai]\nmodel="good"\nmax_retries=0\n', encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_config(explicit)
    assert str(isolated_config) in str(exc.value)


def test_invalid_package_defaults_cannot_be_masked(tmp_path, isolated_config, monkeypatch):
    package = tmp_path / "package"
    package.mkdir()
    (package / "config.default.toml").write_text("[unknown]", encoding="utf-8")
    monkeypatch.setattr(config, "files", lambda _: package)
    with pytest.raises(ConfigError, match="config.default.toml"):
        load_config()


def test_explicit_missing_and_invalid_encoding_report_path(tmp_path, isolated_config):
    path = tmp_path / "explicit.toml"
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert str(path) in str(exc.value)
    path.write_bytes(b"\xff\xff")
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert str(path) in str(exc.value)


@pytest.fixture
def portable_config(tmp_path, monkeypatch):
    executable_dir = tmp_path / "portable app"
    executable_dir.mkdir()
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config.sys, "executable", str(executable_dir / "app.exe"))
    monkeypatch.setattr(
        config, "user_config_path", lambda *args, **kwargs: pytest.fail("Portable must not use user config"),
    )
    return executable_dir / "config.toml"


def test_portable_uses_executable_directory_and_explicit_field_overrides(tmp_path, portable_config, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text("invalid cwd config", encoding="utf-8")
    internal = portable_config.parent / "_internal"
    internal.mkdir()
    (internal / "config.toml").write_text("invalid internal config", encoding="utf-8")
    monkeypatch.setattr(config.sys, "_MEIPASS", str(internal), raising=False)
    portable_config.write_text('[openai]\nmodel="portable-model"\nmax_retries=0\n', encoding="utf-8")

    assert load_config().model == "portable-model"
    explicit = tmp_path / "explicit.toml"
    explicit.write_text('[openai]\nmodel="explicit-model"\nbase_url="http://localhost:9000/v1"\n', encoding="utf-8")
    settings = load_config(explicit)
    assert settings.model == "explicit-model"
    assert settings.base_url == "http://localhost:9000/v1"
    assert settings.max_retries == 0
    assert settings.api_key == "123456"


def test_missing_portable_config_uses_defaults_without_creating_file(portable_config):
    settings = load_config()
    assert settings.model == "gemini-3.8-flash-high"
    assert settings.api_key == "123456"
    assert settings.max_retries == 2
    assert not portable_config.exists()


def test_invalid_portable_config_cannot_be_masked(tmp_path, portable_config):
    portable_config.write_text('[openai]\nmodel=42\n', encoding="utf-8")
    explicit = tmp_path / "valid.toml"
    explicit.write_text('[openai]\nmodel="valid"\n', encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_config(explicit)
    assert str(portable_config) in str(exc.value)


def test_unfrozen_uses_user_config_and_ignores_executable_directory(tmp_path, isolated_config, monkeypatch):
    monkeypatch.setattr(config.sys, "frozen", False, raising=False)
    monkeypatch.setattr(config.sys, "executable", str(tmp_path / "python.exe"))
    (tmp_path / "config.toml").write_text("invalid executable config", encoding="utf-8")
    isolated_config.parent.mkdir()
    isolated_config.write_text('[openai]\nmodel="user-model"\n', encoding="utf-8")
    assert load_config().model == "user-model"
