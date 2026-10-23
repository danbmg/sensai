"""Ingestion idempotente ; une erreur d'embeddings préserve l'ancien document."""
import hashlib
import json

from sensai.rag.documents import PublicDocument, chunk_pages, read_pages
from sensai.rag.store import VectorStore


def index_document(document: PublicDocument, store: VectorStore, embedder,
                   chunk_size=900, overlap=120, force=False) -> dict:
    pages = read_pages(document)
    chunks = chunk_pages(document.document_id, pages, chunk_size, overlap)
    fingerprint = hashlib.sha256(json.dumps({
        "pages": pages, "title": document.title, "publisher": document.publisher,
        "date": document.document_date, "tags": document.tags,
        "model": embedder.model, "size": chunk_size, "overlap": overlap,
    }, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if not force and store.is_current(document.document_id, fingerprint):
        return {"document_id": document.document_id, "chunks": len(chunks), "status": "inchangé"}
    vectors = embedder.embed_documents([chunk.text for chunk in chunks])
    store.replace_document(document, chunks, vectors, embedder.model, fingerprint)
    return {"document_id": document.document_id, "chunks": len(chunks), "status": "indexé"}
