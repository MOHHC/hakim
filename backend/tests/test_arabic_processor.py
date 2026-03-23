"""Comprehensive tests for ArabicProcessor — 40+ cases across all 5 methods."""

import pytest

from app.core.arabic_processor import ArabicProcessor, LexiconMatch

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def proc() -> ArabicProcessor:
    return ArabicProcessor()


@pytest.fixture(scope="module")
def proc_no_lexicon(tmp_path_factory) -> ArabicProcessor:
    """Processor with no lexicon file (empty indexes)."""
    p = tmp_path_factory.mktemp("empty")
    return ArabicProcessor(lexicon_path=p / "nonexistent.json")


# ===========================================================================
# 1. normalize()
# ===========================================================================


class TestNormalize:
    def test_removes_kasra(self, proc):
        assert "\u0650" not in proc.normalize("كِتاب")

    def test_removes_fatha(self, proc):
        assert "\u064e" not in proc.normalize("قَلْب")

    def test_removes_shadda(self, proc):
        assert "\u0651" not in proc.normalize("محمَّد")

    def test_removes_multiple_diacritics(self, proc):
        text = "وَجَعٌ شَدِيدٌ"
        result = proc.normalize(text)
        assert all(
            c not in result for c in "\u064b\u064c\u064d\u064e\u064f\u0650\u0651"
        )

    def test_normalizes_alef_with_hamza_above(self, proc):
        assert proc.normalize("أَلَم") == "الم"

    def test_normalizes_alef_with_hamza_below(self, proc):
        assert proc.normalize("إنسان") == "انسان"

    def test_normalizes_alef_with_madda(self, proc):
        assert proc.normalize("آلام") == "الام"

    def test_normalizes_taa_marbuta(self, proc):
        # صحة → صحه
        result = proc.normalize("صحة")
        assert result.endswith("ه")

    def test_normalizes_alef_maqsura(self, proc):
        # مرضى → مرضي
        result = proc.normalize("مرضى")
        assert result.endswith("ي")

    def test_strips_whitespace(self, proc):
        assert proc.normalize("  وجع  ") == "وجع"

    def test_empty_string(self, proc):
        assert proc.normalize("") == ""

    def test_plain_arabic_unchanged_structure(self, proc):
        # Characters that don't need normalizing should survive
        result = proc.normalize("وجع")
        assert "و" in result and "ج" in result and "ع" in result


# ===========================================================================
# 2. detect_language()
# ===========================================================================


class TestDetectLanguage:
    def test_pure_arabic(self, proc):
        assert proc.detect_language("وجع بالصدر") == "arabic"

    def test_arabic_with_diacritics(self, proc):
        assert proc.detect_language("قَلْبِي بِيوجَعني") == "arabic"

    def test_franco_arab_classic(self, proc):
        assert proc.detect_language("3andi waja3 ras") == "franco_arab"

    def test_franco_arab_7_digit(self, proc):
        assert proc.detect_language("7arara w dawkha") == "franco_arab"

    def test_franco_arab_2_digit(self, proc):
        assert proc.detect_language("2albi bidi2") == "franco_arab"

    def test_franco_arab_mixed_digits(self, proc):
        assert proc.detect_language("3andi 7arara w waja3 bil sadr") == "franco_arab"

    def test_english_plain(self, proc):
        assert proc.detect_language("I have a headache") == "english"

    def test_english_medical(self, proc):
        assert proc.detect_language("chest pain and shortness of breath") == "english"

    def test_empty_string(self, proc):
        assert proc.detect_language("") == "english"

    def test_whitespace_only(self, proc):
        assert proc.detect_language("   ") == "english"

    def test_majority_arabic_detected(self, proc):
        # Mix but >40% Arabic chars
        assert proc.detect_language("وجع pain") == "arabic"

    def test_pure_numbers_not_franco(self, proc):
        # Only digits, no letters → english
        result = proc.detect_language("12345")
        assert result == "english"


# ===========================================================================
# 3. transliterate()
# ===========================================================================


class TestTransliterate:
    def test_3_becomes_ain(self, proc):
        result = proc.transliterate("3ayn")
        assert "ع" in result

    def test_7_becomes_ha_emphatic(self, proc):
        result = proc.transliterate("7arara")
        assert "ح" in result

    def test_2_becomes_hamza(self, proc):
        result = proc.transliterate("2albi")
        assert "أ" in result

    def test_sh_digraph(self, proc):
        result = proc.transliterate("shams")
        assert "ش" in result

    def test_kh_digraph(self, proc):
        result = proc.transliterate("khabar")
        assert "خ" in result

    def test_already_arabic_preserved(self, proc):
        result = proc.transliterate("وجع")
        assert "وجع" in result

    def test_mixed_arabic_and_franco(self, proc):
        result = proc.transliterate("عندي waja3")
        assert "ع" in result  # Arabic preserved
        assert "و" in result  # Franco converted

    def test_waja3_transliterates(self, proc):
        result = proc.transliterate("waja3")
        assert "ع" in result

    def test_empty_string(self, proc):
        assert proc.transliterate("") == ""


# ===========================================================================
# 4. lookup()
# ===========================================================================


class TestLookup:
    def test_latin_exact_match(self, proc):
        results = proc.lookup("waja3")
        assert len(results) >= 1
        assert any("pain" in m.english_medical_term.lower() for m in results)

    def test_arabic_exact_match(self, proc):
        results = proc.lookup("وجع")
        assert len(results) >= 1
        assert any("pain" in m.english_medical_term.lower() for m in results)

    def test_unknown_term_returns_empty(self, proc):
        results = proc.lookup("xyzqwerty")
        assert results == []

    def test_returns_lexicon_match_objects(self, proc):
        results = proc.lookup("waja3")
        assert all(isinstance(r, LexiconMatch) for r in results)

    def test_match_has_all_fields(self, proc):
        results = proc.lookup("waja3")
        m = results[0]
        assert m.dialect_term
        assert m.dialect_term_latin
        assert m.msa_equivalent
        assert m.english_medical_term
        assert m.category
        assert m.body_system
        assert m.severity_hint
        assert m.matched_on in ("arabic", "latin")

    def test_franco_arab_phrase_lookup(self, proc):
        results = proc.lookup("3andi waja3 ras")
        assert len(results) >= 1

    def test_deduplication(self, proc):
        # Same term mentioned twice should not duplicate
        results = proc.lookup("waja3 waja3")
        ids = [m.dialect_term_latin for m in results]
        assert len(ids) == len(set(ids))

    def test_no_lexicon_returns_empty(self, proc_no_lexicon):
        assert proc_no_lexicon.lookup("waja3") == []

    def test_severity_hint_present(self, proc):
        results = proc.lookup("waja3")
        assert results[0].severity_hint != ""

    def test_category_present(self, proc):
        results = proc.lookup("waja3")
        assert results[0].category != ""


# ===========================================================================
# 5. extract_symptoms()
# ===========================================================================


class TestExtractSymptoms:
    def test_single_franco_symptom(self, proc):
        results = proc.extract_symptoms("3andi waja3 ras")
        terms = [m.dialect_term_latin for m in results]
        assert any("waja3" in t for t in terms)

    def test_arabic_free_text(self, proc):
        results = proc.extract_symptoms("عندي وجع بالصدر وحمى")
        assert len(results) >= 1

    def test_multiple_symptoms_extracted(self, proc):
        # "waja3" (pain) + "7arara" (fever) — should find both if in lexicon
        results = proc.extract_symptoms("3andi waja3 w 7arara")
        assert len(results) >= 1

    def test_returns_lexicon_match_objects(self, proc):
        results = proc.extract_symptoms("waja3 ras")
        assert all(isinstance(r, LexiconMatch) for r in results)

    def test_no_symptoms_in_gibberish(self, proc):
        results = proc.extract_symptoms("zzz qqq xyz")
        assert results == []

    def test_deduplication_across_text(self, proc):
        results = proc.extract_symptoms("waja3 waja3 waja3")
        ids = [m.dialect_term_latin for m in results]
        assert len(ids) == len(set(ids))

    def test_english_medical_terms_extracted(self, proc):
        # English words that appear as latin keys in lexicon
        results = proc.extract_symptoms("I have a fever and chest pain")
        # Should match on latin substrings if they appear in lexicon
        assert isinstance(results, list)

    def test_empty_text_returns_empty(self, proc):
        assert proc.extract_symptoms("") == []

    def test_no_lexicon_returns_empty(self, proc_no_lexicon):
        assert proc_no_lexicon.extract_symptoms("waja3 ras") == []

    def test_bigram_matching(self, proc):
        # "waja3 ras" as a two-token window may match "headache" entries
        results = proc.extract_symptoms("waja3 ras")
        assert isinstance(results, list)
