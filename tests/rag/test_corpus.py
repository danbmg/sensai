import json
from pathlib import Path

import pytest
import requests

from sensai.rag.corpus import fetch_corpus, verified_download


class Response:
    url = "https://has-sante.fr/public.pdf"
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def raise_for_status(self): pass
    def iter_content(self, size): yield b"public document"


def test_has_missing_intermediate_keeps_tls_verification(monkeypatch):
    calls = []
    def get(url, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise requests.exceptions.SSLError("missing intermediate")
        bundle = Path(kwargs["verify"])
        assert bundle.exists() and "BEGIN CERTIFICATE" in bundle.read_text()
        return Response()
    monkeypatch.setattr("sensai.rag.corpus.requests.get", get)
    with verified_download("https://has-sante.fr/public.pdf"):
        pass
    assert len(calls) == 2 and calls[1]["verify"] is not False
    assert not Path(calls[1]["verify"]).exists()


def test_other_hosts_tls_errors_are_not_bypassed(monkeypatch):
    def get(*args, **kwargs): raise requests.exceptions.SSLError("invalid certificate")
    monkeypatch.setattr("sensai.rag.corpus.requests.get", get)
    with pytest.raises(requests.exceptions.SSLError):
        with verified_download("https://ansm.sante.fr/doc.pdf"):
            pass


def test_download_skip_and_atomic_replacement_on_failure(tmp_path, monkeypatch):
    manifest = tmp_path / "sources.json"
    manifest.write_text(json.dumps({"documents": [{"file": "public.pdf", "source": Response.url,
        "title": "HAS test", "publisher": "HAS", "public": True}]}))
    root = tmp_path / "corpus"
    monkeypatch.setattr("sensai.rag.corpus.requests.get", lambda *a, **k: Response())
    path = fetch_corpus(manifest, root)[0]
    assert path.read_bytes() == b"public document"
    class Broken(Response):
        def iter_content(self, size):
            yield b"partial"
            raise requests.ConnectionError("download interrupted")
    monkeypatch.setattr("sensai.rag.corpus.requests.get", lambda *a, **k: Broken())
    assert fetch_corpus(manifest, root) == [path]  # cache préservé
    with pytest.raises(requests.ConnectionError):
        fetch_corpus(manifest, root, overwrite=True)
    assert path.read_bytes() == b"public document"
    assert list(root.iterdir()) == [path]
