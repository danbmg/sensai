"""Logs EV3 (JSONL pseudonymisé) et métriques calculées dessus."""
import json
from datetime import date, datetime

import pytest

from sensai.core.config import ConfigError
from sensai.core.pipeline import TurnRecord
from sensai.obs.__main__ import main, render
from sensai.obs.logger import TurnLogger, short_hash
from sensai.obs.metrics import load_entries, percentile, summarize
from sensai.obs.settings import LogSettings, load_log_settings


def record(**changes):
    values = dict(session_id="dupont", model="qwen2.5:3b", latency_s=60.0, prompt_tokens=800,
                  completion_tokens=40, context_tokens=840, tools=["add_patient_note"],
                  prompt=[{"role": "user", "content": "Note pour [PATIENT_1]"}],
                  messages=[{"role": "user", "content": "Note pour [PATIENT_1]"},
                            {"role": "assistant", "content": "", "tool_calls": [{"function": {
                                "name": "add_patient_note", "arguments": {"patient": "[PATIENT_1]"}}}]},
                            {"role": "tool", "tool_name": "add_patient_note", "content": "ok"},
                            {"role": "assistant", "content": "Note ajoutée pour [PATIENT_1]."}])
    values.update(changes)
    return TurnRecord(**values)


def test_logger_writes_one_line_per_turn(tmp_path):
    clock = iter([datetime(2026, 10, 22, 9, 0), datetime(2026, 10, 23, 9, 0)])
    logger = TurnLogger(tmp_path, lambda: {"temperature": 0.2}, clock=lambda: next(clock))

    logger(record())
    logger(record(error="Ollama ne répond pas", messages=[]))

    first = json.loads((tmp_path / "2026-10-22.jsonl").read_text())
    assert first["session"] == short_hash("dupont") and "dupont" not in json.dumps(first)
    assert first["status"] == "ok" and first["response"] == "Note ajoutée pour [PATIENT_1]."
    assert first["tool_calls"] == [{"name": "add_patient_note", "arguments": {"patient": "[PATIENT_1]"}}]
    assert first["prompt"] == record().prompt and first["config"] == {"temperature": 0.2}
    assert json.loads((tmp_path / "2026-10-23.jsonl").read_text())["status"] == "error"


def test_logger_failure_is_reported_not_raised(tmp_path):
    blocker = tmp_path / "logs"
    blocker.write_text("un fichier, pas un dossier")
    logger = TurnLogger(blocker)

    logger(record())

    assert "impossible" in logger.last_error


def write(tmp_path, day, *entries):
    with (tmp_path / f"{day}.jsonl").open("a") as file:
        for entry in entries:
            file.write((entry if isinstance(entry, str) else json.dumps(entry)) + "\n")


def entry(status="ok", latency=10.0, model="qwen2.5:3b", config=None, day="2026-10-22", tools=()):
    return {"timestamp": f"{day}T10:00:00", "model": model, "status": status, "error": "x" if status == "error" else "",
            "latency_s": latency, "prompt_tokens": 100, "completion_tokens": 10, "context_tokens": 110,
            "tool_calls": [{"name": name} for name in tools], "config": config or {"prompt_version": "a"}}


def test_load_entries_skips_broken_lines_and_filters_days(tmp_path):
    write(tmp_path, "2026-10-01", entry(day="2026-10-01"))
    write(tmp_path, "2026-10-22", entry(), '{"coupé', entry())
    (tmp_path / "notes.jsonl").write_text("ignoré")

    entries, skipped = load_entries(tmp_path)
    assert (len(entries), skipped) == (3, 1)
    recent, _ = load_entries(tmp_path, days=7, today=date(2026, 10, 23))
    assert len(recent) == 2
    assert load_entries(tmp_path / "absent") == ([], 0)


def test_percentile_nearest_rank():
    assert percentile(list(range(1, 21)), 95) == 19
    assert percentile([3, 1, 2], 50) == 2 and percentile([], 95) == 0.0


def test_summary_separates_errors_from_refusals_and_shows_drift():
    entries = [entry(latency=10), entry(latency=20, tools=["get_patient"]), entry("error", latency=99),
               entry("blocked", latency=0),
               entry(latency=40, config={"prompt_version": "b"}, day="2026-10-23"),
               entry(latency=44, config={"prompt_version": "b"}, day="2026-10-23", model="llama3.2:3b")]

    summary = summarize(entries)

    assert (summary["turns"], summary["errors"], summary["blocked"]) == (6, 1, 1)
    assert summary["error_rate"] == 0.2                     # 1 erreur sur 5 tours soumis au modèle
    assert summary["latency_mean"] == 28.5                  # tours aboutis seulement
    assert summary["tool_calls"] == {"get_patient": 1}
    versions = [group["config"]["prompt_version"] for group in summary["by_config"]]
    assert versions == ["a", "b"] and summary["by_config"][1]["latency_mean"] == 42.0
    assert [day["day"] for day in summary["by_day"]] == ["2026-10-22", "2026-10-23"]
    assert {group["model"] for group in summary["by_model"]} == {"qwen2.5:3b", "llama3.2:3b"}
    assert summary["recent"][0]["latency_s"] == 44


def test_render_and_command_line(tmp_path, capsys):
    assert render(summarize([])) == "Aucun tour enregistré dans les logs."
    write(tmp_path, "2026-10-22", entry(), entry("blocked"))

    main(["--dir", str(tmp_path)])
    text = capsys.readouterr().out
    assert "Tours : 2" in text and "bloqués 1" in text and "Par configuration" in text
    main(["--dir", str(tmp_path), "--json"])
    assert json.loads(capsys.readouterr().out)["turns"] == 2


def test_log_settings(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[model]\nname = "m"\n', encoding="utf-8")
    assert load_log_settings(path) == LogSettings(enabled=False, directory="logs")
    path.write_text('[logging]\nenabled = true\ndirectory = "journal"\n', encoding="utf-8")
    assert load_log_settings(path) == LogSettings(True, "journal")
    path.write_text('[logging]\nenabled = "oui"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_log_settings(path)
    path.write_text('[logging]\nniveau = 3\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="option inconnue"):
        load_log_settings(path)
