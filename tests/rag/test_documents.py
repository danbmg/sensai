from dataclasses import replace

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from sensai.rag.corpus import documents_from_manifest
from sensai.rag.documents import PublicDocument, chunk_pages, read_pages


def document(path, **kwargs):
    return PublicDocument(path, "Notice de test", "https://ansm.sante.fr/test", "ANSM", public=True, **kwargs)


def test_chunk_boundaries_overlap_and_page_references():
    text = " ".join(f"mot{index:03}" for index in range(90))
    chunks = chunk_pages("doc", [(2, text), (4, "Autre page")], size=120, overlap=30)
    assert chunks[0].page == 2 and chunks[-1].page == 4
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    for chunk in chunks[:-1]:
        assert chunk.text == text[chunk.start:chunk.end].strip()
        assert len(chunk.text) <= 120
    assert chunks[1].start == chunks[0].end - 30
    assert chunks[-2].end == len(text)


@pytest.mark.parametrize("size, overlap", [(20, 0), (100, 100), (100, -1)])
def test_invalid_chunking_is_refused(size, overlap):
    with pytest.raises(ValueError):
        chunk_pages("doc", [(1, "text")], size, overlap)


def test_html_section_excludes_other_sections_and_scripts(tmp_path):
    path = tmp_path / "notice.html"
    path.write_text('<nav>Navigation</nav><div id="rcp">Autre texte</div>'
                    '<div id="notice"><h2>Notice</h2><p>Allergie &amp; pénicilline.</p>'
                    '<script>secret_script</script></div><footer>Footer</footer>')
    pages = read_pages(document(path, section_id="notice"))
    assert "Allergie & pénicilline." in pages[0][1]
    assert all(text not in pages[0][1] for text in ("Autre texte", "secret_script", "Navigation", "Footer"))
    with pytest.raises(ValueError, match="Section"):
        read_pages(document(path, section_id="missing"))


def make_pdf(path):
    writer = PdfWriter()
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    for value in ("Allergie document page un", "Prescription document page deux"):
        page = writer.add_blank_page(width=600, height=800)
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 700 Td ({value}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)


def test_pdf_extraction_keeps_page_numbers_and_rejects_scans(tmp_path):
    path = tmp_path / "public.pdf"
    make_pdf(path)
    pages = read_pages(document(path))
    assert [page for page, _ in pages] == [1, 2]
    assert "Allergie" in pages[0][1] and "Prescription" in pages[1][1]
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(path)
    with pytest.raises(ValueError, match="OCR"):
        read_pages(document(path))


def test_private_documents_sqlite_and_untrusted_sources_are_refused(tmp_path):
    path = tmp_path / "public.txt"
    path.write_text("Texte public")
    base = document(path)
    for invalid in (replace(base, public=False), replace(base, path=tmp_path / "patients.sqlite3"),
                    replace(base, source="https://example.com/notice"),
                    replace(base, source="https://ansm.sante.fr.evil.example/doc")):
        with pytest.raises(ValueError):
            read_pages(invalid)


def test_manifest_cannot_escape_corpus_directory(tmp_path):
    import json
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"documents": [{"file": "../patient.txt", "title": "Bad", "source": "https://ansm.sante.fr/t", "publisher": "ANSM", "public": True}]}))
    with pytest.raises(ValueError, match="répertoire"):
        documents_from_manifest(path, tmp_path / "corpus")
