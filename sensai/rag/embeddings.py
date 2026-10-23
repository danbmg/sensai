"""Client HTTP direct d'Ollama /api/embed, avec les préfixes de tâche Nomic."""
from collections import OrderedDict
import hashlib

import numpy as np
import requests


class EmbeddingError(RuntimeError):
    pass


class OllamaEmbeddings:
    def __init__(self, model="nomic-embed-text", host="http://localhost:11434", timeout=180, batch_size=4):
        if batch_size < 1:
            raise ValueError("La taille de lot doit être positive.")
        self.model, self.host, self.timeout = model, host.rstrip("/"), timeout
        self.batch_size = batch_size
        # Cache borné en RAM : aucun texte de question n'est conservé sur disque.
        self._queries = OrderedDict()

    def _embed(self, texts: list[str], prefix: str) -> list[list[float]]:
        result = []
        dimension = None
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            if any(not isinstance(text, str) or not text.strip() for text in batch):
                raise EmbeddingError("Un texte à encoder est vide ou invalide.")
            try:
                response = requests.post(f"{self.host}/api/embed", timeout=self.timeout, json={
                    "model": self.model, "input": [prefix + text for text in batch],
                    "truncate": False, "keep_alive": 0,
                    # L'encodeur Nomic exige un lot de tokens au moins aussi
                    # grand que le contexte (contrairement au modèle de chat).
                    "options": {"num_thread": 2, "num_batch": 2048, "num_ctx": 2048},
                })
                if response.status_code == 404:
                    raise EmbeddingError(f"Modèle d'embeddings absent : ollama pull {self.model}")
                if response.status_code == 400:
                    raise EmbeddingError("Ollama refuse les extraits : vérifiez la taille des morceaux "
                                         "et le contexte du modèle d'embeddings (2048 tokens).")
                response.raise_for_status()
                payload = response.json()
                vectors = payload.get("embeddings") if isinstance(payload, dict) else None
                array = np.asarray(vectors, dtype=np.float32)
                if array.ndim != 2 or array.shape[0] != len(batch) or array.shape[1] == 0:
                    raise ValueError("Nombre ou dimension de vecteurs invalide")
                norms = np.linalg.norm(array, axis=1)
                if not np.isfinite(array).all() or not np.isfinite(norms).all() or np.any(norms == 0):
                    raise ValueError("Vecteur nul ou non fini")
                if dimension is not None and dimension != array.shape[1]:
                    raise ValueError("Dimensions incohérentes entre lots")
                dimension = array.shape[1]
                result.extend(array.tolist())
            except (requests.RequestException, ValueError, TypeError) as error:
                raise EmbeddingError(f"Embeddings indisponibles : {error}") from error
        return result

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "search_document: ")

    def embed_query(self, query: str) -> list[float]:
        if not isinstance(query, str) or not query.strip():
            raise EmbeddingError("Un texte à encoder est vide ou invalide.")
        key = (self.model, self.host, hashlib.sha256(query.encode()).digest())
        if key not in self._queries:
            self._queries[key] = self._embed([query], "search_query: ")[0]
            if len(self._queries) > 16:
                self._queries.popitem(last=False)
        self._queries.move_to_end(key)
        return list(self._queries[key])
