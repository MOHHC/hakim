"""Tests for the document ingestion pipeline."""

import json
from pathlib import Path

import pytest

from app.knowledge.ingest import (
    DocumentChunk,
    IngestResult,
    _count_tokens,
    _extract_section_title,
    _get_encoder,
    _infer_category,
    _split_text,
    extract_text_from_txt,
    ingest_directory,
    ingest_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def enc():
    return _get_encoder()


@pytest.fixture()
def tmp_source(tmp_path: Path) -> Path:
    src = tmp_path / "medical_sources"
    src.mkdir()
    return src


@pytest.fixture()
def tmp_output(tmp_path: Path) -> Path:
    out = tmp_path / "chunks"
    return out


SAMPLE_MEDICAL_TEXT = """\
# Chest Pain Assessment

Chest pain is one of the most common complaints in emergency medicine.
It can range from benign musculoskeletal causes to life-threatening conditions
such as myocardial infarction or pulmonary embolism.

## History Taking

A thorough history should include onset, character, radiation, associated symptoms,
timing, exacerbating and relieving factors, and severity (SOCRATES framework).

## Physical Examination

Vital signs must be obtained immediately. Auscultation of the heart and lungs
is essential. Peripheral pulses should be assessed for equality.

## Investigations

A 12-lead ECG should be performed within 10 minutes of presentation.
Troponin levels, chest X-ray, and D-dimer may be indicated depending on
clinical suspicion.
"""


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------


def test_count_tokens_basic(enc):
    count = _count_tokens("hello world", enc)
    assert count > 0
    assert count < 5


def test_count_tokens_arabic(enc):
    count = _count_tokens("وجع في الصدر", enc)
    assert count > 0


def test_count_tokens_empty(enc):
    assert _count_tokens("", enc) == 0


# ---------------------------------------------------------------------------
# Category inference
# ---------------------------------------------------------------------------


def test_infer_category_cardiovascular():
    assert _infer_category("cardiology_guide.pdf") == "cardiovascular"


def test_infer_category_respiratory():
    assert _infer_category("respiratory_diseases.txt") == "respiratory"


def test_infer_category_mental_health():
    assert _infer_category("mental_health_overview.md") == "mental_health"


def test_infer_category_emergency():
    assert _infer_category("emergency_protocols.pdf") == "emergency"


def test_infer_category_fallback():
    assert _infer_category("unknown_document.txt") == "general"


# ---------------------------------------------------------------------------
# Section title extraction
# ---------------------------------------------------------------------------


def test_extract_section_title_markdown():
    text = "# Introduction\nSome content here."
    title = _extract_section_title(text, char_offset=20)
    assert title == "Introduction"


def test_extract_section_title_no_heading():
    text = "Just plain text with no headings at all."
    title = _extract_section_title(text, char_offset=10)
    assert title == ""


def test_extract_section_title_picks_nearest():
    text = "# Section A\nContent A.\n## Section B\nContent B."
    # offset is inside Section B content
    title = _extract_section_title(text, char_offset=40)
    assert "Section B" in title


# ---------------------------------------------------------------------------
# Text splitting
# ---------------------------------------------------------------------------


def test_split_text_produces_chunks(enc):
    long_text = "This is a medical sentence about symptoms. " * 200
    spans = _split_text(long_text, enc, chunk_tokens=100, overlap_tokens=10)
    assert len(spans) > 1


def test_split_text_chunk_size_respected(enc):
    long_text = "word " * 1000
    spans = _split_text(long_text, enc, chunk_tokens=50, overlap_tokens=5)
    for start, end in spans:
        chunk = long_text[start:end]
        tokens = _count_tokens(chunk, enc)
        # Allow some slack since we decode by token boundaries
        assert tokens <= 60, f"Chunk too large: {tokens} tokens"


def test_split_text_overlap(enc):
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa " * 50
    spans = _split_text(text, enc, chunk_tokens=20, overlap_tokens=5)
    assert len(spans) >= 2
    # Overlapping chunks should share some text
    first_text = text[spans[0][0] : spans[0][1]]
    second_text = text[spans[1][0] : spans[1][1]]
    # The tail of chunk 1 should appear at the start of chunk 2
    overlap_text = first_text[-30:]
    assert overlap_text[:10] in second_text or second_text[:10] in first_text


def test_split_text_single_chunk_for_short_text(enc):
    short = "This is a short sentence."
    spans = _split_text(short, enc, chunk_tokens=500, overlap_tokens=50)
    assert len(spans) == 1


# ---------------------------------------------------------------------------
# File extraction
# ---------------------------------------------------------------------------


def test_extract_text_from_txt(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Hello medical world.", encoding="utf-8")
    pages = extract_text_from_txt(f)
    assert len(pages) == 1
    page_num, text = pages[0]
    assert page_num == 0
    assert "Hello medical world" in text


# ---------------------------------------------------------------------------
# ingest_file
# ---------------------------------------------------------------------------


def test_ingest_file_txt(tmp_source, enc):
    doc = tmp_source / "cardiology_intro.txt"
    doc.write_text(SAMPLE_MEDICAL_TEXT, encoding="utf-8")
    chunks = ingest_file(doc, enc)
    assert len(chunks) >= 1
    assert all(isinstance(c, DocumentChunk) for c in chunks)


def test_ingest_file_metadata(tmp_source, enc):
    doc = tmp_source / "respiratory_guide.txt"
    doc.write_text(SAMPLE_MEDICAL_TEXT, encoding="utf-8")
    chunks = ingest_file(doc, enc)
    for chunk in chunks:
        assert chunk.source_name == "respiratory_guide.txt"
        assert chunk.medical_category == "respiratory"
        assert chunk.token_count > 0
        assert len(chunk.text) > 0
        assert chunk.chunk_id.startswith("respiratory_guide_")


def test_ingest_file_section_titles_detected(tmp_source, enc):
    doc = tmp_source / "chest_pain.md"
    doc.write_text(SAMPLE_MEDICAL_TEXT, encoding="utf-8")
    chunks = ingest_file(doc, enc)
    titles = [c.section_title for c in chunks]
    assert any("Chest Pain" in t or "History" in t or "Physical" in t for t in titles)


def test_ingest_file_token_counts_within_range(tmp_source, enc):
    long_text = SAMPLE_MEDICAL_TEXT * 10
    doc = tmp_source / "long_doc.txt"
    doc.write_text(long_text, encoding="utf-8")
    chunks = ingest_file(doc, enc, chunk_tokens=100, overlap_tokens=10)
    for chunk in chunks:
        # Allow 20% slack beyond nominal chunk size
        assert chunk.token_count <= 130, f"Chunk too large: {chunk.token_count}"


def test_ingest_file_md(tmp_source, enc):
    doc = tmp_source / "emergency_guide.md"
    doc.write_text(SAMPLE_MEDICAL_TEXT, encoding="utf-8")
    chunks = ingest_file(doc, enc)
    assert len(chunks) >= 1
    assert chunks[0].medical_category == "emergency"


# ---------------------------------------------------------------------------
# ingest_directory
# ---------------------------------------------------------------------------


def test_ingest_directory_writes_json(tmp_source, tmp_output, enc):
    (tmp_source / "cardiology_notes.txt").write_text(
        SAMPLE_MEDICAL_TEXT, encoding="utf-8"
    )
    result = ingest_directory(tmp_source, tmp_output)
    assert isinstance(result, IngestResult)
    assert result.files_processed == 1
    assert result.total_chunks >= 1
    output = Path(result.output_path)
    assert output.exists()


def test_ingest_directory_json_structure(tmp_source, tmp_output):
    (tmp_source / "symptoms_guide.txt").write_text(
        SAMPLE_MEDICAL_TEXT, encoding="utf-8"
    )
    result = ingest_directory(tmp_source, tmp_output)
    data = json.loads(Path(result.output_path).read_text(encoding="utf-8"))
    assert "metadata" in data
    assert "chunks" in data
    assert data["metadata"]["files_processed"] == 1
    assert len(data["chunks"]) == result.total_chunks


def test_ingest_directory_chunk_fields(tmp_source, tmp_output):
    (tmp_source / "digestive_health.txt").write_text(
        SAMPLE_MEDICAL_TEXT, encoding="utf-8"
    )
    ingest_directory(tmp_source, tmp_output)
    data = json.loads((tmp_output / "chunks.json").read_text(encoding="utf-8"))
    chunk = data["chunks"][0]
    for field in (
        "chunk_id",
        "source_name",
        "page_number",
        "section_title",
        "medical_category",
        "text",
        "token_count",
        "char_start",
        "char_end",
    ):
        assert field in chunk, f"Missing field: {field}"


def test_ingest_directory_multiple_files(tmp_source, tmp_output):
    (tmp_source / "cardiology.txt").write_text(SAMPLE_MEDICAL_TEXT, encoding="utf-8")
    (tmp_source / "respiratory.txt").write_text(SAMPLE_MEDICAL_TEXT, encoding="utf-8")
    result = ingest_directory(tmp_source, tmp_output)
    assert result.files_processed == 2
    assert result.total_chunks >= 2


def test_ingest_directory_empty_dir(tmp_source, tmp_output):
    result = ingest_directory(tmp_source, tmp_output)
    assert result.files_processed == 0
    assert result.total_chunks == 0
    assert result.errors == []


def test_ingest_directory_no_errors_on_valid_files(tmp_source, tmp_output):
    (tmp_source / "mental_health.txt").write_text(SAMPLE_MEDICAL_TEXT, encoding="utf-8")
    result = ingest_directory(tmp_source, tmp_output)
    assert result.errors == []
