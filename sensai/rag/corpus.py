"""Manifeste de sources publiques et téléchargement explicite, jamais dans le chat."""
import json
import hashlib
import os
from pathlib import Path
import ssl
import tempfile
from contextlib import contextmanager
from urllib.parse import urlparse

import requests

from sensai.rag.documents import PublicDocument, validate_source


@contextmanager
def verified_download(url: str):
    """TLS reste vérifié, même si HAS omet son intermédiaire Sectigo R36."""
    bundle = None
    try:
        try:
            response = requests.get(url, stream=True, timeout=30)
        except requests.exceptions.SSLError:
            host = urlparse(url).hostname or ""
            if host != "has-sante.fr" and not host.endswith(".has-sante.fr"):
                raise
            certificate = Path(__file__).resolve().parents[2] / "corpus/tls/sectigo-ov-r36.pem"
            pem = certificate.read_text()
            digest = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
            if digest != "6542d176bed50f193c0ce297ae44ecd8a0a86bec2ede682769344059b4e78530":
                raise ValueError("Le certificat intermédiaire HAS fourni a été modifié.")
            with tempfile.NamedTemporaryFile(delete=False) as file:
                bundle = Path(file.name)
                file.write(Path(requests.certs.where()).read_bytes() + b"\n" + pem.encode())
            response = requests.get(url, stream=True, timeout=30, verify=str(bundle))
        with response:
            yield response
    finally:
        if bundle:
            bundle.unlink(missing_ok=True)


def documents_from_manifest(manifest: str | Path, directory: str | Path) -> list[PublicDocument]:
    payload = json.loads(Path(manifest).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        raise ValueError("Le manifeste doit contenir une liste documents.")
    root = Path(directory).resolve()
    documents = []
    for entry in payload["documents"]:
        path = (root / entry["file"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Le fichier sort du répertoire du corpus.")
        document = PublicDocument(path, entry["title"], entry["source"], entry["publisher"],
                                  entry.get("date", ""), tuple(entry.get("tags", [])),
                                  entry.get("public", False), entry.get("section_id", ""))
        document.validate()
        documents.append(document)
    if len({document.document_id for document in documents}) != len(documents):
        raise ValueError("Deux documents du manifeste ont la même source et la même section.")
    return documents


def fetch_corpus(manifest: str | Path, directory: str | Path, overwrite=False) -> list[Path]:
    documents = documents_from_manifest(manifest, directory)
    paths = []
    for document in documents:
        destination = Path(document.path)
        if destination.exists() and not overwrite:
            paths.append(destination)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with verified_download(document.source) as response:
                response.raise_for_status()
                validate_source(response.url)
                with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as file:
                    temporary = Path(file.name)
                    total = 0
                    for chunk in response.iter_content(64 * 1024):
                        total += len(chunk)
                        if total > 25 * 1024 * 1024:
                            raise ValueError("Téléchargement supérieur à 25 Mo.")
                        file.write(chunk)
                os.replace(temporary, destination)
                paths.append(destination)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
    return paths
