import pytest

from sensai.core.config import DEFAULT_PATH, Config, ConfigError, load_config
from sensai.core.ollama_client import DEFAULT_HOST


@pytest.fixture
def write_config(tmp_path):
    def write(text):
        path = tmp_path / "config.toml"
        path.write_text(text, encoding="utf-8")
        return path
    return write


def test_reads_all_fields(write_config):
    path = write_config('''
[model]
name = "llama3.2:3b"
host = "http://h:1"
temperature = 0.7

[assistant]
system_prompt = """
Tu es Sensai.
"""
max_tool_iterations = 3
''')
    assert load_config(path) == Config(model="llama3.2:3b", host="http://h:1", temperature=0.7,
                                       system_prompt="Tu es Sensai.", max_tool_iterations=3)


def test_missing_optional_fields_use_defaults(write_config):
    cfg = load_config(write_config('[model]\nname = "m"\n'))

    assert cfg == Config(model="m")
    assert cfg.host == DEFAULT_HOST


def test_model_argument_overrides_file(write_config):
    path = write_config('[model]\nname = "llama3.2:3b"\n')

    assert load_config(path, model="qwen2.5:3b").model == "qwen2.5:3b"


def test_model_argument_alone_is_enough(write_config):
    assert load_config(write_config(""), model="m").model == "m"


def test_missing_model_name_raises(write_config):
    with pytest.raises(ConfigError, match="name manquant"):
        load_config(write_config("[model]\ntemperature = 0.2\n"))


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError, match="introuvable"):
        load_config(tmp_path / "absent.toml")


def test_invalid_toml_raises(write_config):
    with pytest.raises(ConfigError):
        load_config(write_config("[model\nname = "))


def test_project_config_is_valid_and_avoids_thinking_tag():
    cfg = load_config()

    assert DEFAULT_PATH.name == "config.toml"
    assert cfg.system_prompt
    assert cfg.model != "qwen3:4b"   # Qwen3-4B-Thinking : réfléchit toujours, voir CLAUDE.md


@pytest.mark.parametrize("text", [
    'model = "bad"',
    '[model]\nname = 123',
    '[model]\nname = "m"\nhost = 123',
    '[model]\nname = "m"\nnum_thread = 0',
    '[model]\nname = "m"\ntemperature = nan',
    '[model]\nname = "m"\ntimeout = inf',
    '[model]\nname = "m"\n[assistant]\nsystem_prompt = 123',
])
def test_invalid_configuration_reports_config_error(write_config, text):
    with pytest.raises(ConfigError):
        load_config(write_config(text))


def test_history_window_read_and_validated(tmp_path):
    from sensai.core.config import ConfigError, load_config
    path = tmp_path / "config.toml"
    path.write_text('[model]\nname = "m"\n[assistant]\nmax_history_turns = 4\n', encoding="utf-8")
    assert load_config(path).max_history_turns == 4
    path.write_text('[model]\nname = "m"\n[assistant]\nmax_history_turns = -1\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="max_history_turns"):
        load_config(path)


def test_validate_config_rejects_live_changes():
    from dataclasses import replace
    from sensai.core.config import Config, ConfigError, validate_config
    validate_config(Config("m"))
    for change in ({"temperature": -0.1}, {"num_ctx": 0}, {"model": " "}, {"max_tool_iterations": True}):
        with pytest.raises(ConfigError):
            validate_config(replace(Config("m"), **change))
