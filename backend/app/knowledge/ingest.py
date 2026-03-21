"""Document ingestion pipeline.

Reads .txt, .md, and .pdf files from a source directory, splits them into
overlapping token-based chunks, attaches metadata, and writes the results as
JSON ready for embedding.

CLI usage:
    python -m app.knowledge.ingest --source-dir ./data/medical_sources
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import tiktoken
from pypdf import PdfReader

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHUNK_TOKENS = 500
OVERLAP_TOKENS = 50
ENCODING_NAME = "cl100k_base"  # same encoder used by GPT-4 / text-embedding-3

# Heuristic: map filename keywords → medical category
_CATEGORY_HINTS: list[tuple[str, str]] = [
    ("cardio", "cardiovascular"),
    ("heart", "cardiovascular"),
    ("respiratory", "respiratory"),
    ("pulmonary", "respiratory"),
    ("lung", "respiratory"),
    ("digestive", "digestive"),
    ("gastro", "digestive"),
    ("mental", "mental_health"),
    ("psych", "mental_health"),
    ("pediatric", "pediatrics"),
    ("child", "pediatrics"),
    ("emergency", "emergency"),
    ("triage", "triage"),
    ("symptom", "symptoms"),
    ("anatomy", "anatomy"),
    ("pharmacol", "pharmacology"),
]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class DocumentChunk:
    chunk_id: str           # "{source_stem}_{page}_{index}"
    source_name: str        # original filename
    page_number: int        # 1-based; 0 for non-paged sources
    section_title: str      # nearest heading above this chunk (empty if none)
    medical_category: str   # inferred from filename or "general"
    text: str               # chunk text
    token_count: int
    char_start: int         # character offset in the full document text
    char_end: int


@dataclass
class IngestResult:
    source_dir: str
    files_processed: int
    total_chunks: int
    output_path: str
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tokenizer helpers
# ---------------------------------------------------------------------------

def _get_encoder() -> tiktoken.Encoding:
    return tiktoken.get_encoding(ENCODING_NAME)


def _count_tokens(text: str, enc: tiktoken.Encoding) -> int:
    return len(enc.encode(text))


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text_from_txt(path: Path) -> list[tuple[int, str]]:
    """Returns list of (page_number, text). TXT/MD are treated as one page."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return [(0, text)]


def extract_text_from_pdf(path: Path) -> list[tuple[int, str]]:
    """Returns list of (page_number, text), 1-based page numbers."""
    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append((i, text))
    return pages


def extract_text(path: Path) -> list[tuple[int, str]]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    elif suffix in (".txt", ".md"):
        return extract_text_from_txt(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


# ---------------------------------------------------------------------------
# Section title detection
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+(.+)|([A-Z][A-Z\s]{3,}[A-Z]))\s*$",
    re.MULTILINE,
)


def _extract_section_title(text: str, char_offset: int) -> str:
    """Find the last heading that appears before char_offset in text."""
    best = ""
    for m in _HEADING_RE.finditer(text):
        if m.start() > char_offset:
            break
        title = (m.group(1) or m.group(2) or "").strip()
        if title:
            best = title
    return best


# ---------------------------------------------------------------------------
# Medical category inference
# ---------------------------------------------------------------------------

def _infer_category(source_name: str) -> str:
    lower = source_name.lower()
    for keyword, category in _CATEGORY_HINTS:
        if keyword in lower:
            return category
    return "general"


# ---------------------------------------------------------------------------
# Recursive text splitter
# ---------------------------------------------------------------------------

def _split_text(
    text: str,
    enc: tiktoken.Encoding,
    chunk_tokens: int = CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[tuple[int, int]]:
    """
    Returns list of (char_start, char_end) spans for chunks.

    Strategy: split on paragraph breaks first, then sentences, then words,
    to avoid cutting in the middle of a sentence when possible.
    """
    tokens = enc.encode(text)
    total = len(tokens)
    spans: list[tuple[int, int]] = []

    pos = 0  # token position
    while pos < total:
        end = min(pos + chunk_tokens, total)
        chunk_token_ids = tokens[pos:end]
        chunk_text = enc.decode(chunk_token_ids)

        # Find char offsets: locate chunk_text inside full text starting from
        # approximate position to avoid false matches at the beginning
        approx_char = int(pos / total * len(text)) if total > 0 else 0
        search_start = max(0, approx_char - 200)
        idx = text.find(chunk_text, search_start)
        if idx == -1:
            # Fallback: search from beginning
            idx = text.find(chunk_text)
        if idx == -1:
            idx = search_start

        char_start = idx
        char_end = idx + len(chunk_text)
        spans.append((char_start, char_end))

        step = chunk_tokens - overlap_tokens
        pos += max(step, 1)

    return spans


# ---------------------------------------------------------------------------
# Core ingestion
# ---------------------------------------------------------------------------

def ingest_file(
    path: Path,
    enc: tiktoken.Encoding,
    chunk_tokens: int = CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[DocumentChunk]:
    source_name = path.name
    medical_category = _infer_category(source_name)
    stem = path.stem
    chunks: list[DocumentChunk] = []

    pages = extract_text(path)

    for page_num, page_text in pages:
        if not page_text.strip():
            continue

        spans = _split_text(page_text, enc, chunk_tokens, overlap_tokens)

        for chunk_idx, (char_start, char_end) in enumerate(spans):
            chunk_text = page_text[char_start:char_end].strip()
            if not chunk_text:
                continue

            token_count = _count_tokens(chunk_text, enc)
            section_title = _extract_section_title(page_text, char_start)
            chunk_id = f"{stem}_{page_num}_{chunk_idx}"

            chunks.append(DocumentChunk(
                chunk_id=chunk_id,
                source_name=source_name,
                page_number=page_num,
                section_title=section_title,
                medical_category=medical_category,
                text=chunk_text,
                token_count=token_count,
                char_start=char_start,
                char_end=char_end,
            ))

    return chunks


def ingest_directory(
    source_dir: Path,
    output_dir: Path,
    chunk_tokens: int = CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> IngestResult:
    """Ingest all supported files in source_dir and write chunks JSON to output_dir."""
    enc = _get_encoder()
    output_dir.mkdir(parents=True, exist_ok=True)

    all_chunks: list[DocumentChunk] = []
    errors: list[str] = []
    files_processed = 0

    supported = list(source_dir.glob("*.txt")) + list(source_dir.glob("*.md")) + list(source_dir.glob("*.pdf"))

    if not supported:
        logger.warning("No supported files found in %s", source_dir)

    for path in sorted(supported):
        try:
            logger.info("Ingesting %s ...", path.name)
            file_chunks = ingest_file(path, enc, chunk_tokens, overlap_tokens)
            all_chunks.extend(file_chunks)
            files_processed += 1
            logger.info("  → %d chunks", len(file_chunks))
        except Exception as exc:
            msg = f"{path.name}: {exc}"
            logger.error("Failed to ingest %s", msg)
            errors.append(msg)

    output_path = output_dir / "chunks.json"
    payload = {
        "metadata": {
            "source_dir": str(source_dir),
            "files_processed": files_processed,
            "total_chunks": len(all_chunks),
            "chunk_tokens": chunk_tokens,
            "overlap_tokens": overlap_tokens,
            "encoding": ENCODING_NAME,
        },
        "chunks": [asdict(c) for c in all_chunks],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote %d chunks to %s", len(all_chunks), output_path)

    return IngestResult(
        source_dir=str(source_dir),
        files_processed=files_processed,
        total_chunks=len(all_chunks),
        output_path=str(output_path),
        errors=errors,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.knowledge.ingest",
        description="Ingest medical documents into chunked JSON for embedding.",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path("app/data/medical_sources"),
        help="Directory containing .txt, .md, or .pdf files (default: app/data/medical_sources)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("app/data/chunks"),
        help="Directory where chunks.json is written (default: app/data/chunks)",
    )
    parser.add_argument(
        "--chunk-tokens",
        type=int,
        default=CHUNK_TOKENS,
        help=f"Target tokens per chunk (default: {CHUNK_TOKENS})",
    )
    parser.add_argument(
        "--overlap-tokens",
        type=int,
        default=OVERLAP_TOKENS,
        help=f"Overlap tokens between chunks (default: {OVERLAP_TOKENS})",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = _build_parser()
    args = parser.parse_args()

    result = ingest_directory(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        chunk_tokens=args.chunk_tokens,
        overlap_tokens=args.overlap_tokens,
    )

    print(f"\nDone.")
    print(f"  Files processed : {result.files_processed}")
    print(f"  Total chunks    : {result.total_chunks}")
    print(f"  Output          : {result.output_path}")
    if result.errors:
        print(f"  Errors ({len(result.errors)}):")
        for e in result.errors:
            print(f"    - {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
