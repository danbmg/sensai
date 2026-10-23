"""Ingestion et recherche : python -m sensai.rag --help."""
import argparse
import json
from pathlib import Path
import sqlite3

import requests

from sensai.core.config import ConfigError, load_config
from sensai.guardrails.pii_vault import SensaiPIIVault
from sensai.memory.patients import PatientStore
from sensai.rag.corpus import documents_from_manifest, fetch_corpus
from sensai.rag.documents import PublicDocument
from sensai.rag.embeddings import EmbeddingError, OllamaEmbeddings
from sensai.rag.indexing import index_document
from sensai.rag.retrieval import Retriever, source_records
from sensai.rag.settings import load_settings, resolve_index_path
from sensai.rag.store import Filters, IndexError, VectorStore


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--index", type=Path)
    parser.add_argument("--host")
    parser.add_argument("--embedding-model")
    parser.add_argument("--memory-db", type=Path, default=Path(".sensai/memory.sqlite3"), help="dossiers connus pour pseudonymiser la recherche")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch", help="télécharger explicitement le corpus public")
    index = commands.add_parser("index", help="indexer le corpus téléchargé")
    for command in (fetch, index):
        command.add_argument("--manifest", type=Path, default=Path("corpus/sources.json"))
        command.add_argument("--directory", type=Path, default=Path(".sensai/corpus"))
    fetch.add_argument("--overwrite", action="store_true")
    index.add_argument("--force", action="store_true")
    ingest = commands.add_parser("ingest", help="indexer un document public local")
    ingest.add_argument("path", type=Path)
    ingest.add_argument("--title", required=True)
    ingest.add_argument("--source", required=True)
    ingest.add_argument("--publisher", choices=["ANSM", "HAS"], required=True)
    ingest.add_argument("--date", default="")
    ingest.add_argument("--tag", action="append", default=[])
    ingest.add_argument("--public", action="store_true", help="attester que le fichier est public, sans dossier patient")
    ingest.add_argument("--section-id", default="")
    ingest.add_argument("--force", action="store_true")
    commands.add_parser("list")
    remove = commands.add_parser("remove")
    remove.add_argument("document_id")
    search = commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--publisher", choices=["ANSM", "HAS"])
    search.add_argument("--tag", action="append", default=[])
    search.add_argument("--since", default="")
    search.add_argument("--until", default="")
    search.add_argument("--no-rerank", action="store_true")
    args = parser.parse_args(argv)
    try:
        cfg, settings = load_config(args.config), load_settings(args.config)
        if args.command == "fetch":
            paths = fetch_corpus(args.manifest, args.directory, args.overwrite)
            print("\n".join(map(str, paths)))
            return
        index_path = args.index or resolve_index_path(settings, args.memory_db)
        if index_path.resolve() == args.memory_db.resolve():
            raise ValueError("L'index documentaire doit être séparé de la base des patients et sessions.")
        store = VectorStore(index_path)
        embedder = OllamaEmbeddings(args.embedding_model or settings.model,
                                    args.host or cfg.host, settings.timeout, settings.batch_size)
        if args.command == "list":
            result = store.list_documents()
        elif args.command == "remove":
            store.remove_document(args.document_id)
            result = {"removed": args.document_id}
        elif args.command in {"index", "ingest"}:
            documents = (documents_from_manifest(args.manifest, args.directory) if args.command == "index"
                         else [PublicDocument(args.path, args.title, args.source, args.publisher,
                                             args.date, tuple(args.tag), args.public, args.section_id)])
            result = []
            for document in documents:
                record = index_document(document, store, embedder, settings.chunk_size, settings.overlap, args.force)
                result.append(record)
                print(f"{document.title} : {record['status']} ({record['chunks']} extraits)", flush=True)
        else:
            known = PatientStore(args.memory_db).list_patients() if args.memory_db.exists() else []
            query = SensaiPIIVault(patients=known).mask(args.query)
            retriever = Retriever(store, embedder, top_k=settings.top_k, candidates=settings.candidates,
                                  min_similarity=settings.min_similarity, min_relevance=settings.min_relevance,
                                  rerank=settings.rerank and not args.no_rerank)
            result = source_records(retriever.search(query, Filters(args.publisher, tuple(args.tag), args.since, args.until)))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError, ConfigError, EmbeddingError, IndexError,
            sqlite3.Error, requests.RequestException) as error:
        parser.exit(1, f"RAG : {error}\n")


if __name__ == "__main__":
    main()
