import typing

import pytest

from sensai.core import interfaces
from sensai.core.interfaces import PSEUDONYM_RE, Event, GuardResult, SessionState, ToolResult


def test_guard_result_defaults():
    result = GuardResult()
    assert not result.blocked
    assert result.reason == ""


def test_session_state_not_shared_between_instances():
    a, b = SessionState(), SessionState()
    a.history.append({"role": "user", "content": "[PATIENT_1]"})
    a.pii_map["[PATIENT_1]"] = "Jeanne Dupont"
    assert b == SessionState()


def test_tool_result_and_event_defaults():
    assert ToolResult("ok").is_error is False
    assert Event("done").data is None


@pytest.mark.parametrize("text", ["[PATIENT_1]", "[NAISSANCE_2]", "[ADRESSE_10]",
                                  "[TEL_1]", "[NIR_1]", "[EMAIL_3]"])
def test_pseudonym_re_matches_known_types(text):
    assert PSEUDONYM_RE.fullmatch(text)


@pytest.mark.parametrize("text", ["[PATIENT]", "[patient_1]", "[NOM_1]", "PATIENT_1",
                                  "[PATIENT_1", "[DATE_NAISSANCE_1]"])
def test_pseudonym_re_rejects_other_brackets(text):
    assert not PSEUDONYM_RE.fullmatch(text)


@pytest.mark.parametrize("protocol", [interfaces.InputGuard, interfaces.PIIVault,
                                      interfaces.OutputGuard, interfaces.ContextProvider,
                                      interfaces.SessionStore, interfaces.ToolRegistry])
def test_protocol_annotations_resolve(protocol):
    """Garde-fou : une méthode nommée comme un type (ex. list) casse les annotations en 3.14."""
    for name, member in vars(protocol).items():
        if callable(member) and not name.startswith("_"):
            typing.get_type_hints(member)
