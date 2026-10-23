"""Extraction de documents publics et découpage par page, sans framework LLM."""
from dataclasses import dataclass
from datetime import date
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urlparse


PUBLIC_HOSTS = ("ansm.sante.fr", "has-sante.fr", "base-donnees-publique.medicaments.gouv.fr")


def validate_source(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not any(
        parsed.hostname == host or (parsed.hostname or "").endswith("." + host) for host in PUBLIC_HOSTS
    ):
        raise ValueError("La source doit être une URL HTTPS officielle ANSM, HAS ou BDPM.")


@dataclass(frozen=True)
class PublicDocument:
    path: Path
    title: str
    source: str
    publisher: str
    document_date: str = ""
    tags: tuple[str, ...] = ()
    public: bool = False
    section_id: str = ""

    def validate(self) -> None:
        if self.public is not True:
            raise ValueError("Le document doit être explicitement déclaré public ; aucun dossier patient n'est indexé.")
        validate_source(self.source)
        if not self.title.strip() or self.publisher not in {"ANSM", "HAS"}:
            raise ValueError("Titre obligatoire et éditeur ANSM ou HAS attendu.")
        if self.document_date:
            if date.fromisoformat(self.document_date).isoformat() != self.document_date:
                raise ValueError("Date attendue : YYYY-MM-DD.")
        if any(not isinstance(tag, str) or not tag.strip() for tag in self.tags):
            raise ValueError("Les étiquettes doivent être des textes non vides.")
        if Path(self.path).suffix.lower() not in {".pdf", ".txt", ".md", ".html", ".htm"}:
            raise ValueError("Format attendu : PDF, texte, Markdown ou HTML public.")

    @property
    def document_id(self) -> str:
        return hashlib.sha256((self.source + "#" + self.section_id).encode()).hexdigest()[:24]


class HTMLText(HTMLParser):
    def __init__(self, section_id=""):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0
        self.section_id = section_id
        self.depth = 0
        self.found = not section_id
        self.stack = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "header", "footer"}:
            self.skip += 1
        attributes = dict(attrs)
        starts = bool(self.section_id and attributes.get("id") == self.section_id)
        if starts:
            self.found = True
        active = starts or bool(self.depth)
        if tag not in {"br", "hr", "img", "input", "meta", "link", "wbr", "source"}:
            self.stack.append((tag, active, tag in {"script", "style", "nav", "header", "footer"}))
            if active:
                self.depth += 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                removed = self.stack[index:]
                del self.stack[index:]
                self.depth -= sum(active for _, active, _ in removed)
                self.skip -= sum(skip for _, _, skip in removed)
                break
        if tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip and (not self.section_id or self.depth):
            self.parts.append(data)


def read_pages(document: PublicDocument) -> list[tuple[int, str]]:
    document.validate()
    path = Path(document.path)
    if path.stat().st_size > 25 * 1024 * 1024:
        raise ValueError("Document trop volumineux (limite : 25 Mo).")
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
        try:
            reader = PdfReader(path)
            if reader.is_encrypted:
                raise ValueError("Les PDF chiffrés ne sont pas pris en charge.")
            pages = [(index + 1, page.extract_text() or "") for index, page in enumerate(reader.pages)]
        except PdfReadError as error:
            raise ValueError(f"PDF illisible : {path.name}") from error
    else:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in {".html", ".htm"}:
            parser = HTMLText(document.section_id)
            parser.feed(text)
            if not parser.found:
                raise ValueError(f"Section HTML introuvable : {document.section_id}")
            text = "".join(parser.parts)
        pages = [(1, text)]
    pages = [(number, re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]*\n[ \t]*", "\n", text.replace("\xa0", " "))).strip())
             for number, text in pages]
    if not any(text.strip() for _, text in pages):
        raise ValueError("Document sans texte extractible ; les PDF scannés nécessitent un OCR externe.")
    return pages


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    page: int
    position: int
    start: int
    end: int
    text: str


def chunk_pages(document_id: str, pages: list[tuple[int, str]], size=900, overlap=120) -> list[Chunk]:
    if not isinstance(size, int) or not isinstance(overlap, int) or size < 100 or not 0 <= overlap < size:
        raise ValueError("Découpage attendu : taille >= 100 et 0 <= chevauchement < taille.")
    chunks = []
    for page, raw in pages:
        text = re.sub(r"[ \t]+", " ", raw.replace("\r\n", "\n")).strip()
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                split = text.rfind(" ", start + size // 2, end)
                if split > start:
                    end = split
            value = text[start:end].strip()
            if value:
                position = len(chunks)
                chunks.append(Chunk(f"{document_id}:{position}", document_id, page, position, start, end, value))
            if end == len(text):
                break
            start = max(start + 1, end - overlap)
    return chunks
