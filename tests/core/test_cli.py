from types import SimpleNamespace

import pytest
import requests

from sensai import cli
from sensai.app import runtime as app_runtime
from sensai.core.ollama_client import ChatChunk, ModelNotFoundError, OllamaError
from sensai.memory.profiles import DoctorProfile, DoctorProfileStore
from sensai.memory.sessions import SQLiteSessionStore

TOOLS = ["completion", "tools"]


class FakeClient:
    capabilities_result: list[str] | Exception = TOOLS     # réponse de /api/show, ou erreur
    replies: list[list] = []                # une liste de fragments par appel ; une exception y est levée
    calls: list[list[dict]] = []            # messages reçus, un élément par appel

    def __init__(self, model, host, options=None, **kwargs):
        FakeClient.model, FakeClient.host, FakeClient.options = model, host, options
        FakeClient.keep_alive = kwargs.get("keep_alive")
        self.model, self.host, self.timeout = model, host, 120.0

    def capabilities(self):
        if isinstance(FakeClient.capabilities_result, Exception):
            raise FakeClient.capabilities_result
        return FakeClient.capabilities_result

    def chat_stream(self, messages, tools=None):
        FakeClient.calls.append(messages)
        for item in FakeClient.replies[len(FakeClient.calls) - 1]:
            if isinstance(item, BaseException):
                raise item
            yield item


def reply(text):
    return [ChatChunk(content=text, done=True)]


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[model]\nname = "llama3.2:3b"\nhost = "http://h:1"\ntemperature = 0.1\n'
                    '[assistant]\nsystem_prompt = "Tu es Sensai."\n', encoding="utf-8")
    return path


@pytest.fixture
def run_cli(monkeypatch, capsys, config_file):
    """Lance la CLI sur `inputs` (puis Ctrl+D) ; renvoie stdout sans la bannière, et stderr.

    Une exception dans `inputs` est levée par input() (ex. KeyboardInterrupt = Ctrl+C).
    """
    monkeypatch.setattr(app_runtime, "OllamaClient", FakeClient)

    def run(inputs, replies=(), argv=(), capabilities=TOOLS):
        FakeClient.capabilities_result = capabilities
        FakeClient.replies, FakeClient.calls = list(replies), []
        lines = iter(inputs)

        def fake_input(prompt=""):
            line = next(lines, EOFError())
            if isinstance(line, BaseException):
                raise line
            return line
        monkeypatch.setattr("builtins.input", fake_input)
        cli.main(["--config", str(config_file), "--db", str(config_file.parent / "test.sqlite3"), *argv])
        captured = capsys.readouterr()
        return SimpleNamespace(out=captured.out.split("\n", 1)[1], err=captured.err)
    return run


SYSTEM = {"role": "system", "content": "Tu es Sensai."}


def test_prints_streamed_answer(run_cli):
    out = run_cli(["Salut"],
                  [[ChatChunk(content="Bon"), ChatChunk(content="jour", done=True)]]).out

    assert out == "Bonjour\n\n"         # réponse, puis saut de ligne du Ctrl+D


def test_uses_config_file(run_cli):
    run_cli(["Salut"], [[]])

    assert (FakeClient.model, FakeClient.host) == ("llama3.2:3b", "http://h:1")
    assert FakeClient.options == {"temperature": 0.1, "num_ctx": 2048, "num_predict": 128,
                                 "num_thread": 2, "num_batch": 64}
    assert FakeClient.calls == [[SYSTEM, {"role": "user", "content": "Salut"}]]


def test_model_flag_overrides_config(run_cli):
    run_cli([], argv=["--model", "qwen2.5:3b"])

    assert FakeClient.model == "qwen2.5:3b"


def test_model_retention_is_opt_in(run_cli):
    run_cli([])
    assert FakeClient.keep_alive == 0
    run_cli([], argv=["--keep-alive", "2m"])
    assert FakeClient.keep_alive == "2m"
    with pytest.raises(SystemExit) as error:
        run_cli([], argv=["--keep-alive", "forever"])
    assert error.value.code == 2


def test_banner_shows_model_and_commands(monkeypatch, capsys, config_file):
    monkeypatch.setattr(app_runtime, "OllamaClient", FakeClient)
    monkeypatch.setattr(FakeClient, "capabilities_result", TOOLS)
    monkeypatch.setattr("builtins.input", lambda prompt="": "/quit")
    cli.main(["--config", str(config_file)])

    banner = capsys.readouterr().out
    assert "llama3.2:3b" in banner and "/reset" in banner and "/quit" in banner


def test_thinking_not_displayed(run_cli):
    # Event n'a pas de type « thinking » : seul le contenu de la réponse s'affiche.
    out = run_cli(["Salut"],
                  [[ChatChunk(thinking="hmm"), ChatChunk(content="Bonjour", done=True)]]).out

    assert out == "Bonjour\n\n"


def test_tool_call_and_result_displayed_on_their_own_lines(run_cli):
    call = {"function": {"name": "add_patient_note", "arguments": {"patient": "Paul"}}}
    out = run_cli(["Note"], [[ChatChunk(content="Je note."), ChatChunk(tool_calls=[call])]]).out

    assert out == (f"Je note.\n{cli.DIM}→ add_patient_note(patient='Paul'){cli.RESET}\n"
                   'Action proposée : add_patient_note({"patient": "Paul"})\n'
                   f"{cli.DIM}← Action refusée par le médecin{cli.RESET}\n"
                   "Action annulée à votre demande. Non exécuté : add_patient_note.\n\n")


def test_previous_turns_sent_to_model(run_cli):
    run_cli(["Je m'appelle Paul", "Comment je m'appelle ?"],
            [reply("Enchanté, Paul."), reply("Paul.")])

    assert FakeClient.calls[1] == [
        SYSTEM,
        {"role": "user", "content": "Je m'appelle Paul"},
        {"role": "assistant", "content": "Enchanté, Paul."},
        {"role": "user", "content": "Comment je m'appelle ?"},
    ]


def test_history_keeps_full_answer_without_thinking(run_cli):
    run_cli(["a", "b"], [[ChatChunk(thinking="hmm"), ChatChunk(content="Bon"),
                          ChatChunk(content="jour", done=True)], reply("")])

    assert FakeClient.calls[1][2] == {"role": "assistant", "content": "Bonjour"}


def test_reset_clears_history_but_keeps_system_prompt(run_cli):
    out = run_cli(["Je m'appelle Paul", "/reset", "Comment je m'appelle ?"],
                  [reply("Enchanté."), reply("Je ne sais pas.")]).out

    assert FakeClient.calls[1] == [SYSTEM, {"role": "user", "content": "Comment je m'appelle ?"}]
    assert "Conversation effacée." in out


def test_restart_restores_patient_and_profile_and_rejects_mixed_patient(run_cli, config_file):
    db = config_file.parent / "test.sqlite3"
    profiles = DoctorProfileStore(db)
    profiles.save(DoctorProfile("generaliste", "Médecine générale", ["Réponses courtes"], "Citer les sources"))
    run_cli(["Quelles allergies sont enregistrées ?"], [reply("Dossier consulté.")],
            argv=["--demo", "--profile", "generaliste", "--session", "consultation"])
    run_cli(["/dossier", "/profile", "Quelles allergies sont enregistrées ?"], [reply("Dossier consulté.")],
            argv=["--session", "consultation"])
    context = "\n".join(m["content"] for m in FakeClient.calls[0] if m["role"] == "system")
    assert "Médecine générale" in context and "pénicilline" in context.casefold()
    assert "Jeanne Dupont" not in context  # le modèle reçoit le dossier masqué
    assert len(SQLiteSessionStore(db).load("consultation").history) == 4
    with pytest.raises(SystemExit, match="autre patient"):
        run_cli([], argv=["--session", "consultation", "--patient", "demo-bernard"])


def test_session_switch_restores_associated_patient(run_cli):
    out = run_cli(["/patient demo-bernard", "/session dupont", "/dossier"],
                  argv=["--demo", "--session", "dupont"]).out
    assert '"name": "Jeanne Dupont"' in out


def test_reset_reloads_modified_profile_at_next_conversation(run_cli, config_file):
    profiles = DoctorProfileStore(config_file.parent / "test.sqlite3")
    profiles.save(DoctorProfile("default", "Médecine générale"))
    def change_profile():
        yield "Premier échange"
        profiles.save(DoctorProfile("default", "Cardiologie"))
        yield "/reset"
        yield "Deuxième échange"
    run_cli(change_profile(), [reply("Bonjour."), reply("Bonjour.")])
    first = " ".join(m["content"] for m in FakeClient.calls[0])
    second = " ".join(m["content"] for m in FakeClient.calls[1])
    assert "Médecine générale" in first and "Cardiologie" not in first
    assert "Cardiologie" in second and "Médecine générale" not in second


def test_document_commands_and_source_persistence(run_cli, monkeypatch, config_file):
    from sensai.rag.documents import PublicDocument, chunk_pages
    from sensai.rag.store import VectorStore
    path = config_file.parent / "public.txt"
    path.write_text("Allergie à la pénicilline : extrait public de test.")
    document = PublicDocument(path, "Notice de test", "https://ansm.sante.fr/test", "ANSM", public=True)
    store = VectorStore(config_file.parent / "rag.sqlite3")
    chunks = chunk_pages(document.document_id, [(1, path.read_text())])
    store.replace_document(document, chunks, [[1, 0]], "nomic-embed-text", "test")
    queries = []
    class FakeEmbeddings:
        model = "nomic-embed-text"
        def __init__(self, *args): pass
        def embed_query(self, text):
            queries.append(text)
            return [1, 0]
    monkeypatch.setattr(app_runtime, "OllamaEmbeddings", FakeEmbeddings)
    run_cli(["/search Allergie de Jeanne Dupont à la pénicilline", "/sources"],
            argv=["--demo", "--session", "sources"])
    assert queries and "Jeanne Dupont" not in queries[0]
    resumed = run_cli(["/sources"], argv=["--session", "sources"]).out
    assert '"citation": "S1"' in resumed and "https://ansm.sante.fr/test" in resumed
    filtered = run_cli(['/rag-filter {"publisher":"HAS"}', "/search allergie", "/sources"],
                       argv=["--session", "sources"]).out
    assert "Aucun extrait documentaire pertinent" in filtered
    assert len(queries) == 1  # aucun document HAS : aucun appel embeddings


def test_failed_turn_keeps_previous_sources(run_cli, monkeypatch, config_file):
    from sensai.rag.retrieval import Hit
    from dataclasses import asdict
    db = config_file.parent / "test.sqlite3"
    DoctorProfileStore(db).ensure_default()
    sessions = SQLiteSessionStore(db)
    hit = Hit("a:0", "a", "Source précédente", "https://ansm.sante.fr/a", "ANSM", "", 1, "Texte public", .8, .7, 1)
    sessions.save_context("interruption", {"patient_id": None, "profile_id": "default", "sources": [asdict(hit)]})
    out = run_cli(["Question", "/sources"], [[requests.ConnectionError("refused")]],
                  argv=["--session", "interruption"])
    assert "Source précédente" in out.out
    assert sessions.load_context("interruption")["sources"][0]["document_id"] == "a"


def test_quit_stops_without_calling_model(run_cli):
    run_cli(["/quit", "Salut"])

    assert FakeClient.calls == []


def test_ctrl_d_quits(run_cli):
    run_cli(["Salut"], [reply("Bonjour")])     # l'entrée s'épuise → EOFError

    assert len(FakeClient.calls) == 1


def test_commands_ignore_surrounding_spaces(run_cli):
    run_cli(["  /quit  ", "Salut"])

    assert FakeClient.calls == []


def test_unknown_command_not_sent_to_model(run_cli):
    out = run_cli(["/reste"]).out

    assert FakeClient.calls == []
    assert "Commande inconnue : /reste" in out


# --- Erreurs au démarrage (/api/show) ---

def test_ollama_down_at_startup_exits_with_message(run_cli):
    with pytest.raises(SystemExit, match=r"Ollama ne répond pas sur http://h:1.*ollama serve"):
        run_cli(["Salut"], capabilities=requests.ConnectionError("refused"))
    assert FakeClient.calls == []


def test_connect_timeout_reported_as_unreachable(run_cli):
    with pytest.raises(SystemExit, match="Ollama ne répond pas sur"):
        run_cli([], capabilities=requests.ConnectTimeout("timed out"))


def test_missing_model_suggests_pull(run_cli):
    with pytest.raises(SystemExit, match="ollama pull llama3.2:3b"):
        run_cli(["Salut"], capabilities=ModelNotFoundError("llama3.2:3b"))
    assert FakeClient.calls == []


def test_model_without_tools_refused(run_cli):
    with pytest.raises(SystemExit, match="« tools » absente"):
        run_cli(["Salut"], capabilities=["completion"])
    assert FakeClient.calls == []


def test_thinking_model_warns_but_runs(run_cli):
    result = run_cli(["Salut"], [reply("Bonjour")], capabilities=TOOLS + ["thinking"])

    assert "⚠ llama3.2:3b est un modèle « thinking »" in result.err
    assert len(FakeClient.calls) == 1


def test_other_http_error_at_startup_exits_with_message(run_cli):
    with pytest.raises(SystemExit, match="Erreur d'Ollama : 500"):
        run_cli([], capabilities=requests.HTTPError("500 Server Error"))


# --- Erreurs en cours de session : message, et la session continue ---

def test_empty_input_ignored(run_cli):
    run_cli(["", "   ", "Salut"], [reply("Bonjour")])

    assert len(FakeClient.calls) == 1


def test_ctrl_c_at_prompt_keeps_session(run_cli):
    result = run_cli(["Je m'appelle Paul", KeyboardInterrupt(), "Comment je m'appelle ?"],
                     [reply("Enchanté."), reply("Paul.")])

    assert len(FakeClient.calls[1]) == 4        # système + tour 1 + question
    assert "/quit pour quitter" in result.out


def test_ctrl_c_during_generation_drops_turn_and_keeps_session(run_cli):
    result = run_cli(["Je m'appelle Paul", "Raconte une histoire", "Comment je m'appelle ?"],
                     [reply("Enchanté."), [ChatChunk(content="Il était"), KeyboardInterrupt()],
                      reply("Paul.")])

    assert f"Il était\n{cli.DIM}Génération interrompue." in result.out
    assert FakeClient.calls[2] == [
        SYSTEM,
        {"role": "user", "content": "Je m'appelle Paul"},
        {"role": "assistant", "content": "Enchanté."},
        {"role": "user", "content": "Comment je m'appelle ?"},
    ]


@pytest.mark.parametrize("error, message", [
    (requests.ReadTimeout("read timed out"), "aucun fragment reçu en 120 s"),
    (requests.ConnectionError("refused"), "ollama serve"),
    (ModelNotFoundError("llama3.2:3b"), "ollama pull llama3.2:3b"),
    (OllamaError("model runner crashed"), "Erreur d'Ollama : model runner crashed"),
])
def test_error_during_generation_reported_and_session_kept(run_cli, error, message):
    result = run_cli(["Je m'appelle Paul", "Raconte", "Comment je m'appelle ?"],
                     [reply("Enchanté."), [ChatChunk(content="Il était"), error],
                      reply("Paul.")])

    assert message in result.err
    assert "Traceback" not in result.err
    assert [m["content"] for m in FakeClient.calls[2]] == [
        "Tu es Sensai.", "Je m'appelle Paul", "Enchanté.", "Comment je m'appelle ?"]


def test_missing_config_exits_with_message(tmp_path):
    with pytest.raises(SystemExit, match="Configuration invalide.*introuvable"):
        cli.main(["--config", str(tmp_path / "absent.toml")])


# --- Contexte et logs visibles depuis la CLI (CE-1, CE-3, EV3) ---

def test_usage_line_after_answer(run_cli):
    out = run_cli(["Salut"], [[ChatChunk(content="Bonjour"),
                               ChatChunk(done=True, prompt_tokens=812, completion_tokens=54)]]).out

    assert "tokens : 812 lus + 54 générés · contexte 866/2048" in out


def test_prompt_command_shows_exact_pseudonymized_prompt(run_cli):
    out = run_cli(["/prompt", "Mme Dupont va-t-elle bien ?", "/prompt"], [reply("Oui.")], argv=["--demo"]).out

    assert "Aucun prompt envoyé" in out
    prompt = out.split("(pseudonymisé) :", 1)[1]
    assert '"content": "[PATIENT_1] va-t-elle bien ?"' in prompt and "Dupont" not in prompt
    assert "Outils proposés : aucun" in prompt


def test_metrics_command(run_cli, config_file):
    assert "Logs désactivés" in run_cli(["/metrics"]).out
    logs = config_file.parent / "logs"
    config_file.write_text(config_file.read_text() + f'[logging]\nenabled = true\ndirectory = "{logs}"\n')

    out = run_cli(["Salut", "/metrics"], [reply("Bonjour")]).out

    assert "Tours : 1" in out and len(list(logs.glob("*.jsonl"))) == 1


def test_commands_needing_a_value_explain_their_usage(run_cli):
    err = run_cli(["/patient", "/note"], argv=["--demo"]).err

    assert "usage : /patient <nom complet ou id>" in err and "usage : /note <texte>" in err


def test_tools_command_marks_actions_needing_approval(run_cli):
    out = run_cli(["/tools"]).out

    assert "add_patient_entry : " in out and "(validation du médecin)" in out
    assert "find_patients : Cherche" in out and "find_patients : Cherche les patients dont le nom contient le texte donné (nom et identifiant).\n" in out
