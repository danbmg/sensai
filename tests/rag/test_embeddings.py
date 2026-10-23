import pytest
import requests

from sensai.rag.embeddings import EmbeddingError, OllamaEmbeddings


class Response:
    def __init__(self, vectors=None, status=200):
        self.vectors, self.status_code = vectors, status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("server error")
    def json(self):
        return {"embeddings": self.vectors}


def test_direct_embed_api_batching_prefixes_and_cpu_limits(monkeypatch):
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response([[1, 2] for _ in kwargs["json"]["input"]])
    monkeypatch.setattr("sensai.rag.embeddings.requests.post", post)
    client = OllamaEmbeddings(host="http://local:11434/", batch_size=2)
    assert len(client.embed_documents(["a", "b", "c"])) == 3
    client.embed_query("question pseudonymisée")
    assert len(calls) == 3
    assert calls[0][0] == "http://local:11434/api/embed"
    assert calls[0][1]["json"]["input"] == ["search_document: a", "search_document: b"]
    assert calls[-1][1]["json"]["input"] == ["search_query: question pseudonymisée"]
    assert all(call[1]["json"]["truncate"] is False and call[1]["json"]["keep_alive"] == 0 for call in calls)
    assert calls[0][1]["json"]["options"]["num_thread"] == 2
    options = calls[0][1]["json"]["options"]
    assert options["num_batch"] >= options["num_ctx"]


@pytest.mark.parametrize("vectors", [[], [[0, 0]], [[float('nan'), 1]], [[1, 2], [3, 4]], [[1], [1, 2]]])
def test_invalid_embedding_results_are_rejected(monkeypatch, vectors):
    monkeypatch.setattr("sensai.rag.embeddings.requests.post", lambda *a, **k: Response(vectors))
    with pytest.raises(EmbeddingError):
        OllamaEmbeddings().embed_query("query")


def test_missing_model_and_server_errors_are_readable(monkeypatch):
    monkeypatch.setattr("sensai.rag.embeddings.requests.post", lambda *a, **k: Response(status=404))
    with pytest.raises(EmbeddingError, match="ollama pull nomic-embed-text"):
        OllamaEmbeddings().embed_query("query")
    def down(*args, **kwargs):
        raise requests.ConnectionError("connection refused")
    monkeypatch.setattr("sensai.rag.embeddings.requests.post", down)
    with pytest.raises(EmbeddingError, match="indisponibles"):
        OllamaEmbeddings().embed_query("query")


def test_query_cache_avoids_reloading_model_and_returns_independent_vectors(monkeypatch):
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs["json"])
        return Response([[1, 2]])
    monkeypatch.setattr("sensai.rag.embeddings.requests.post", post)
    client = OllamaEmbeddings()
    vector = client.embed_query("question masquée")
    vector[0] = 999
    assert client.embed_query("question masquée") == [1, 2]
    assert len(calls) == 1
    client.model = "autre-modele"
    client.embed_query("question masquée")
    assert len(calls) == 2


def test_query_cache_is_bounded_and_failed_requests_are_retried(monkeypatch):
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs["json"]["input"])
        if len(calls) == 1:
            raise requests.ConnectionError("temporary failure")
        return Response([[1, 2]])
    monkeypatch.setattr("sensai.rag.embeddings.requests.post", post)
    client = OllamaEmbeddings()
    with pytest.raises(EmbeddingError):
        client.embed_query("première question")
    client.embed_query("première question")
    for index in range(16):
        client.embed_query(f"autre question {index}")
    count = len(calls)
    client.embed_query("première question")  # l'ancienne entrée a été évincée
    assert len(calls) == count + 1
