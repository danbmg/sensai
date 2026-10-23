from dataclasses import asdict

import pytest

from sensai.memory.context import PatientContext
from sensai.memory.patients import PatientStore
from sensai.memory.profiles import DoctorProfile, DoctorProfileStore, ProfileNotFoundError, main


def test_profile_survives_restart_and_is_injected_without_a_patient(tmp_path):
    path = tmp_path / "memory.sqlite3"
    profile = DoctorProfile("generaliste", "Médecine générale", ["Réponses courtes", "Citer les sources"], "Répondre en français.")
    DoctorProfileStore(path).save(profile)
    restored = DoctorProfileStore(path).load("generaliste")
    assert restored == profile
    context = PatientContext(PatientStore(path), profile=restored)
    messages = context.provide("question", "question", "s")
    assert len(messages) == 1 and messages[0]["role"] == "system"
    for text in ("Médecine générale", "Réponses courtes", "Citer les sources", "Répondre en français"):
        assert text in messages[0]["content"]


def test_profiles_are_independent_and_context_uses_startup_snapshot(tmp_path):
    path = tmp_path / "memory.sqlite3"
    store = DoctorProfileStore(path)
    first = DoctorProfile("a", "Généraliste", ["Concis"])
    store.save(first)
    store.save(DoctorProfile("b", "Pédiatrie"))
    context = PatientContext(PatientStore(path), profile=store.load("a"))
    first.preferences.append("Mutation externe")
    store.save(DoctorProfile("a", "Cardiologie"))
    assert "Généraliste" in context.provide("", "", "s")[0]["content"]
    assert "Mutation externe" not in context.provide("", "", "s")[0]["content"]
    assert store.load("b").specialty == "Pédiatrie"
    assert store.list_profiles() == ["a", "b"]


def test_default_profile_preserves_preferences_and_unknown_profile_is_explicit(tmp_path):
    store = DoctorProfileStore(tmp_path / "db.sqlite3")
    assert store.ensure_default() == DoctorProfile()
    store.save(DoctorProfile("default", "Pédiatrie"))
    assert store.ensure_default().specialty == "Pédiatrie"
    with pytest.raises(ProfileNotFoundError):
        store.load("typo")


@pytest.mark.parametrize("profile", [DoctorProfile(""), DoctorProfile("p", preferences="bad"),
                                      DoctorProfile("p", preferences=[""]), DoctorProfile("p", specialty=3)])
def test_invalid_profile_is_not_persisted(tmp_path, profile):
    store = DoctorProfileStore(tmp_path / "db.sqlite3")
    with pytest.raises(ValueError):
        store.save(profile)
    assert store.list_profiles() == []


def test_profile_management_command(tmp_path, capsys):
    path = str(tmp_path / "db.sqlite3")
    main(["--db", path, "set", "default", "--specialty", "Médecine générale", "--preference", "Concis"])
    capsys.readouterr()
    main(["--db", path, "show", "default"])
    assert "Médecine générale" in capsys.readouterr().out
    main(["--db", path, "list"])
    assert capsys.readouterr().out.strip() == "default"
