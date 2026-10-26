"""Serveurs MCP tiers ([[mcp.servers]]) : branchés à côté du serveur médical, sans code commun."""
import sys
from pathlib import Path

import pytest

from sensai.app.tool_routing import requested_tools
from sensai.core.config import ConfigError
from sensai.memory.fixtures import seed_demo_patients
from sensai.memory.patients import PatientStore
from sensai.tools.runtime import medical_tools
from sensai.tools.settings import MCPServer, load_mcp_servers

FAKE_SERVER = str(Path(__file__).with_name("fake_time_server.py"))


@pytest.fixture
def patients(tmp_path):
    store = PatientStore(tmp_path / "memory.sqlite3")
    seed_demo_patients(store)
    return store


def fake_time(**changes) -> MCPServer:
    values = dict(name="time", command=sys.executable, args=(FAKE_SERVER,),
                  tools=("get_current_time", "convert_time"), keywords=("fuseau",))
    return MCPServer(**{**values, **changes})


def test_third_party_tools_are_prefixed_filtered_and_callable(patients):
    with medical_tools(patients, use_mcp=True, servers=(fake_time(),)) as registry:
        names = {schema["function"]["name"] for schema in registry.schemas()}
        # Préfixe : pas de collision avec notre get_current_time ; set_clock n'est pas retenu.
        assert {"get_current_time", "time_get_current_time", "time_convert_time", "get_patient"} <= names
        assert "time_set_clock" not in names
        result = registry.call("time_get_current_time", {"timezone": "Europe/Paris"})
        assert not result.is_error and "2026-10-28T14:00:00" in result.content
        assert registry.keywords["time_convert_time"] == ("fuseau",)


def test_third_party_write_tool_can_require_the_doctor(patients):
    server = fake_time(tools=(), dangerous=("set_clock",))
    with medical_tools(patients, use_mcp=True, servers=(server,)) as registry:
        assert registry.is_dangerous("time_set_clock")
        assert not registry.is_dangerous("time_get_current_time")


def test_unavailable_third_party_server_is_skipped(patients, capsys):
    broken = fake_time(name="absent", command="/nonexistent/python")
    with medical_tools(patients, use_mcp=True, servers=(broken, fake_time())) as registry:
        names = {schema["function"]["name"] for schema in registry.schemas()}
        assert "time_get_current_time" in names and "get_patient" in names
        assert not any(name.startswith("absent_") for name in names)
    assert "Serveur MCP « absent » ignoré" in capsys.readouterr().err


def test_third_party_servers_need_mcp_mode(patients):
    with medical_tools(patients, use_mcp=False, servers=(fake_time(),)) as registry:
        assert not any(schema["function"]["name"].startswith("time_") for schema in registry.schemas())


def test_keywords_offer_third_party_tools_when_a_record_is_open():
    keywords = {"time_convert_time": ("fuseau",)}
    assert "time_convert_time" in requested_tools("Quelle heure dans le fuseau de New York ?", keywords)
    assert "time_convert_time" not in requested_tools("Mme Dupont peut-elle prendre de l'amoxicilline ?", keywords)


def test_config_describes_servers(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('[[mcp.servers]]\nname = "time"\ncommand = "py"\nargs = ["-m", "srv"]\n'
                      'keywords = ["Fuseau"]\n', encoding="utf-8")
    [server] = load_mcp_servers(config)
    assert (server.prefix, server.args, server.keywords) == ("time_", ("-m", "srv"), ("fuseau",))
    assert load_mcp_servers(_empty(tmp_path)) == ()                     # sans [mcp] : aucun serveur tiers


@pytest.mark.parametrize("body, message", [
    ('[[mcp.servers]]\nname = "medical"\nargs = ["x"]\n', "unique"),            # nom réservé
    ('[[mcp.servers]]\nname = "a b"\nargs = ["x"]\n', "identifiant"),
    ('[[mcp.servers]]\nname = "time"\n', "obligatoire"),                         # ni command ni args
    ('[[mcp.servers]]\nname = "time"\nargs = ["x"]\nport = 3\n', "inconnue"),
])
def test_config_rejects_bad_servers(tmp_path, body, message):
    config = tmp_path / "config.toml"
    config.write_text(body, encoding="utf-8")
    with pytest.raises(ConfigError, match=message):
        load_mcp_servers(config)


def _empty(tmp_path):
    path = tmp_path / "empty.toml"
    path.write_text("", encoding="utf-8")
    return path
