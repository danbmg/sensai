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
