"""Arabic text processing for Lebanese dialect medical input."""

from __future__ import annotations
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_LEXICON_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "lexicon" / "lebanese_medical.json"
)
_TASHKEEL_RE = re.compile(r"[\u064b-\u065f\u0670]")
_ALEF_VARIANTS = str.maketrans(
    {"\u0623": "\u0627", "\u0625": "\u0627", "\u0622": "\u0627", "\u0671": "\u0627"}
)
_TAA_MARBUTA = str.maketrans({"\u0629": "\u0647"})
_YAA_VARIANTS = str.maketrans({"\u0649": "\u064a"})
_HA_VARIANTS = str.maketrans({"\u06c1": "\u0647"})
_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06ff]")
_FRANCO_DIGIT_RE = re.compile(r"[23567890]")
_FRANCO_PATTERN_RE = re.compile(
    r"\b(?:[a-zA-Z]+[23567890][a-zA-Z0-9]*|[a-zA-Z0-9]*[23567890][a-zA-Z]+)\b"
)
_FRANCO_MAP: list[tuple[str, str]] = [
    ("sh", "ش"),
    ("kh", "خ"),
    ("gh", "غ"),
    ("th", "ث"),
    ("ch", "ش"),
    ("ph", "ف"),
    ("dh", "ذ"),
    ("2", "أ"),
    ("3", "ع"),
    ("5", "خ"),
    ("6", "ط"),
    ("7", "ح"),
    ("8", "غ"),
    ("9", "ق"),
    ("a", "ا"),
    ("b", "ب"),
    ("t", "ت"),
    ("j", "ج"),
    ("d", "د"),
    ("r", "ر"),
    ("z", "ز"),
    ("s", "س"),
    ("f", "ف"),
    ("k", "ك"),
    ("l", "ل"),
    ("m", "م"),
    ("n", "ن"),
    ("h", "ه"),
    ("w", "و"),
    ("y", "ي"),
    ("q", "ق"),
    ("i", "ي"),
    ("o", "و"),
    ("u", "و"),
    ("e", ""),
    ("p", "ب"),
    ("v", "ف"),
    ("g", "ج"),
    ("x", "كس"),
    ("c", "ك"),
]
_FRANCO_REGEX = re.compile(
    "|".join(re.escape(s) for s, _ in _FRANCO_MAP), re.IGNORECASE
)
_FRANCO_REPLACE_MAP = {s.lower(): d for s, d in _FRANCO_MAP}


@dataclass
class LexiconMatch:
    dialect_term: str
    dialect_term_latin: str
    msa_equivalent: str
    english_medical_term: str
    category: str
    body_system: str
    severity_hint: str
    matched_on: str


class ArabicProcessor:
    def __init__(self, lexicon_path: Path = _LEXICON_PATH) -> None:
        self._entries: list[dict] = []
        self._latin_index: dict[str, dict] = {}
        self._arabic_index: dict[str, dict] = {}
        self._load_lexicon(lexicon_path)

    def _load_lexicon(self, path: Path) -> None:
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self._entries = data.get("entries", [])
        for entry in self._entries:
            latin = entry.get("dialect_term_latin", "").lower().strip()
            if latin:
                self._latin_index[latin] = entry
            arabic = self.normalize(entry.get("dialect_term", ""))
            if arabic:
                self._arabic_index[arabic] = entry

    def normalize(self, text: str) -> str:
        text = _TASHKEEL_RE.sub("", text)
        text = text.translate(_ALEF_VARIANTS)
        text = text.translate(_TAA_MARBUTA)
        text = text.translate(_YAA_VARIANTS)
        text = text.translate(_HA_VARIANTS)
        return text.strip()

    def detect_language(self, text: str) -> Literal["arabic", "franco_arab", "english"]:
        non_space = re.sub(r"\s", "", text.strip())
        if not non_space:
            return "english"
        arabic_count = len(_ARABIC_CHAR_RE.findall(non_space))
        if arabic_count / len(non_space) > 0.40:
            return "arabic"
        if _FRANCO_DIGIT_RE.search(text) and (
            _FRANCO_PATTERN_RE.search(text) or re.search(r"[a-zA-Z]", text)
        ):
            return "franco_arab"
        return "english"

    def transliterate(self, text: str) -> str:
        tokens = text.split()
        out: list[str] = []
        for token in tokens:
            ratio = len(_ARABIC_CHAR_RE.findall(token)) / max(len(token), 1)
            if ratio > 0.4:
                out.append(token)
            else:
                out.append(
                    _FRANCO_REGEX.sub(
                        lambda m: _FRANCO_REPLACE_MAP.get(
                            m.group(0).lower(), m.group(0)
                        ),
                        token,
                    )
                )
        return " ".join(out)

    def lookup(self, text: str) -> list[LexiconMatch]:
        results: dict[str, LexiconMatch] = {}
        normalized = self.normalize(text)
        latin_lower = text.lower()
        lang = self.detect_language(text)
        if lang in ("arabic", "franco_arab"):
            for candidate in [normalized] + normalized.split():
                if candidate in self._arabic_index:
                    self._add_match(results, self._arabic_index[candidate], "arabic")
        for latin_key, entry in self._latin_index.items():
            if latin_key in latin_lower:
                self._add_match(results, entry, "latin")
        return list(results.values())

    def _add_match(self, results: dict, entry: dict, matched_on: str) -> None:
        key = entry.get("dialect_term_latin", "")
        if key not in results:
            results[key] = LexiconMatch(
                dialect_term=entry.get("dialect_term", ""),
                dialect_term_latin=key,
                msa_equivalent=entry.get("msa_equivalent", ""),
                english_medical_term=entry.get("english_medical_term", ""),
                category=entry.get("category", ""),
                body_system=entry.get("body_system", ""),
                severity_hint=entry.get("severity_hint", ""),
                matched_on=matched_on,
            )

    def extract_symptoms(self, text: str) -> list[LexiconMatch]:
        seen: dict[str, LexiconMatch] = {}
        tokens = re.findall(r"[\u0600-\u06ff]+|[a-zA-Z0-9]+", text)
        for n in (1, 2, 3):
            for i in range(len(tokens) - n + 1):
                window = " ".join(tokens[i : i + n])
                for m in self.lookup(window):
                    if m.dialect_term_latin not in seen:
                        seen[m.dialect_term_latin] = m
        for m in self.lookup(text):
            if m.dialect_term_latin not in seen:
                seen[m.dialect_term_latin] = m
        return list(seen.values())
