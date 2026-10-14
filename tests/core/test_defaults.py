from sensai.core.defaults import (EmptyContext, EmptyRegistry, InMemorySessionStore, NullGuard,
                                  NullOutputGuard, NullVault)
from sensai.core.interfaces import SessionState


def test_null_guards_let_everything_through():
    assert not NullGuard().check("n'importe quoi").blocked
    assert NullOutputGuard().check("Jeanne Dupont") == "Jeanne Dupont"


def test_null_vault_is_identity_and_its_own_factory():
    vault = NullVault({"[PATIENT_1]": "Jeanne Dupont"})

    assert vault.mask("Jeanne Dupont") == "Jeanne Dupont"
    assert vault.reveal("[PATIENT_1]") == "[PATIENT_1]"
    assert vault.reveal_args({"patient": "x"}) == {"patient": "x"}
    assert NullVault(vault.export()).export() == {"[PATIENT_1]": "Jeanne Dupont"}


def test_empty_context_and_registry():
    assert EmptyContext().provide("q", "q", "s1") == []
    registry = EmptyRegistry()
    assert registry.schemas() == [] and not registry.is_dangerous("add_patient_note")
    result = registry.call("add_patient_note", {})
    assert result.is_error and "add_patient_note" in result.content


def test_unknown_session_is_empty():
    assert InMemorySessionStore().load("inconnue") == SessionState()


def test_session_saved_and_listed():
    store = InMemorySessionStore()
    store.save("s1", SessionState(history=[{"role": "user", "content": "Salut"}]))

    assert store.load("s1").history == [{"role": "user", "content": "Salut"}]
    assert store.list_sessions() == ["s1"]


def test_changes_without_save_are_not_kept():
    store = InMemorySessionStore()
    store.save("s1", SessionState())

    store.load("s1").history.append({"role": "user", "content": "perdu"})

    assert store.load("s1") == SessionState()
