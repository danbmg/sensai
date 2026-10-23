from dataclasses import replace
import json

import pytest

from sensai.rag.documents import PublicDocument, chunk_pages
from sensai.rag.indexing import index_document
from sensai.rag.retrieval import Retriever, format_context
from sensai.rag.store import Filters, IndexError, VectorStore


class Embedder:
    model = "test-embeddings"
    def __init__(self):
        self.calls = []
    def embed_documents(self, texts):
        self.calls.extend(texts)
        return [[1.0, 0.0] for _ in texts]
    def embed_query(self, query):
        self.calls.append(query)
        return [1.0, 0.0]


def add(store, tmp_path, title, text, publisher="ANSM", date="2025-01-01", tags=(), vector=None):
    path = tmp_path / f"{title}.txt"
    path.write_text(text)
    document = PublicDocument(path, title, f"https://{'has-sante.fr' if publisher == 'HAS' else 'ansm.sante.fr'}/{title}",
                              publisher, date, tags, True)
    chunks = chunk_pages(document.document_id, [(1, text)])
    store.replace_document(document, chunks, [vector or [1, 0]] * len(chunks), "test-embeddings", title)
    return document


def test_cosine_search_reranking_and_relevance_threshold(tmp_path):
    store = VectorStore(tmp_path / "rag.sqlite3")
    add(store, tmp_path, "a", "Le paracétamol est décrit ici.")
    add(store, tmp_path, "z", "Amoxicilline : allergie à la pénicilline.", vector=[0.98, 0.2])
    embedder = Embedder()
    semantic = Retriever(store, embedder, rerank=False)
    advanced = Retriever(store, embedder, rerank=True)
    assert semantic.search("allergie pénicilline")[0].title == "a"
    hits = advanced.search("allergie pénicilline")
    assert hits[0].title == "z" and hits[0].lexical_score > 0
    assert hits[0].relevance > hits[1].relevance
    strict = Retriever(store, embedder, min_relevance=0.95)
    assert strict.search("allergie pénicilline") == []


def test_metadata_filters_apply_before_embedding_and_ranking(tmp_path):
    store = VectorStore(tmp_path / "rag.sqlite3")
    add(store, tmp_path, "old", "Allergie", "HAS", "2014-02-01", ("antibiotiques",))
    add(store, tmp_path, "new", "Allergie", "ANSM", "2025-02-01", ("notice",))
    embedder = Embedder()
    search = Retriever(store, embedder)
    assert [hit.title for hit in search.search("allergie", Filters(publisher="ANSM", since="2025-01-01", tags=("notice",)))] == ["new"]
    embedder.calls.clear()
    assert search.search("allergie", Filters(publisher="HAS", since="2025-01-01")) == []
    assert embedder.calls == []
    with pytest.raises(ValueError):
        search.search("allergie", Filters(since="2026-01-01", until="2020-01-01"))


def test_empty_index_does_not_call_embedding_server(tmp_path):
    embedder = Embedder()
    assert Retriever(VectorStore(tmp_path / "rag.sqlite3"), embedder).search("question") == []
    assert embedder.calls == []


def test_reindex_is_idempotent_and_failure_preserves_old_data(tmp_path):
    store, embedder = VectorStore(tmp_path / "rag.sqlite3"), Embedder()
    path = tmp_path / "doc.txt"
    path.write_text("Allergie à la pénicilline.")
    document = PublicDocument(path, "Notice", "https://ansm.sante.fr/test", "ANSM", public=True)
    assert index_document(document, store, embedder)["status"] == "indexé"
    count = len(embedder.calls)
    assert index_document(document, store, embedder)["status"] == "inchangé"
    assert len(embedder.calls) == count
    path.write_text("Texte modifié")
    class Broken(Embedder):
        def embed_documents(self, texts): raise RuntimeError("Ollama down")
    with pytest.raises(RuntimeError):
        index_document(document, store, Broken())
    assert store.candidates()[0]["text"] == "Allergie à la pénicilline."
    assert len(store.list_documents()) == 1
    index_document(document, store, embedder)
    assert store.candidates()[0]["text"] == "Texte modifié"
    assert len(store.list_documents()) == 1


def test_model_dimension_and_zero_vector_mismatches_are_rejected(tmp_path):
    store = VectorStore(tmp_path / "rag.sqlite3")
    document = add(store, tmp_path, "first", "Allergie")
    embedder = Embedder()
    embedder.model = "different"
    with pytest.raises(IndexError):
        Retriever(store, embedder).search("allergie")
    embedder.model = "test-embeddings"
    embedder.embed_query = lambda query: [1, 0, 0]
    with pytest.raises(IndexError):
        Retriever(store, embedder).search("allergie")
    with pytest.raises(ValueError):
        store.replace_document(document, chunk_pages(document.document_id, [(1, "text")]), [[0, 0]], "test-embeddings", "bad")
    assert store.candidates()[0]["text"] == "Allergie"


def test_context_budget_and_source_references_are_consistent(tmp_path):
    store = VectorStore(tmp_path / "rag.sqlite3")
    add(store, tmp_path, "a", "allergie " * 90)
    hits = Retriever(store, Embedder()).search("allergie")
    text, used = format_context(hits, max_chars=650)
    assert len(text) <= 650
    assert "[S1]" in text and "https://ansm.sante.fr/a" in text and "page 1" in text
    assert len(used) == 1 and used[0].text in text
