"""Tests for TriageEngine -- LLM and RAGPipeline mocked throughout."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.arabic_processor import LexiconMatch
from app.core.llm_client import LLMResponse
from app.core.rag_pipeline import RetrievalResult
from app.core.triage_engine import (
    TriageEngine,
    TriageLevel,
    TriageResult,
    _DISCLAIMER,
    _EMERGENCY_DISCLAIMER,
    _EMERGENCY_RE,
    _REFUSAL_RE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _llm_response(text: str, tokens: int = 50) -> LLMResponse:
    return LLMResponse(
        text=text,
        provider="gemini",
        model="gemini-2.0-flash",
        prompt_tokens=tokens // 2,
        completion_tokens=tokens // 2,
        total_tokens=tokens,
        latency_ms=100.0,
    )


def _mock_llm(text: str = "Hello", tokens: int = 50) -> MagicMock:
    llm = MagicMock()
    llm.generate = AsyncMock(return_value=_llm_response(text, tokens))
    return llm


def _mock_rag(results: list | None = None) -> MagicMock:
    rag = MagicMock()
    rag.retrieve = AsyncMock(return_value=results or [])
    return rag


def _mock_proc(symptoms: list | None = None) -> MagicMock:
    proc = MagicMock()
    proc.extract_symptoms = MagicMock(return_value=symptoms or [])
    return proc


def _make_symptom(
    latin: str = "waja3", msa: str = "pain", english: str = "pain"
) -> LexiconMatch:
    return LexiconMatch(
        dialect_term="waja3",
        dialect_term_latin=latin,
        msa_equivalent=msa,
        english_medical_term=english,
        category="pain",
        body_system="general",
        severity_hint="mild",
        matched_on="latin",
    )


def _make_retrieval_result(chunk_id: str = "doc_0") -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        chunk_text="Chest pain can indicate cardiovascular conditions.",
        source="cardiology.txt",
        relevance_score=0.85,
        medical_category="cardiovascular",
        section_title="Chest Pain",
        page_number=1,
        vector_score=0.85,
        rerank_score=-1.0,
    )


def _triage_json(level: str = "GREEN") -> str:
    return (
        '{"triage_level": "' + level + '", '
        '"possible_conditions": ["condition A"], '
        '"recommended_actions": ["rest", "hydrate"]}'
    )


# ---------------------------------------------------------------------------
# TriageLevel
# ---------------------------------------------------------------------------


class TestTriageLevel:
    def test_values(self):
        assert TriageLevel.GREEN.value == "GREEN"
        assert TriageLevel.YELLOW.value == "YELLOW"
        assert TriageLevel.RED.value == "RED"

    def test_is_string(self):
        assert isinstance(TriageLevel.GREEN, str)

    def test_enum_members(self):
        assert set(TriageLevel.__members__) == {"GREEN", "YELLOW", "RED"}


# ---------------------------------------------------------------------------
# TriageResult.to_dict()
# ---------------------------------------------------------------------------


class TestTriageResultToDict:
    def _make(self, level: TriageLevel = TriageLevel.GREEN) -> TriageResult:
        return TriageResult(
            triage_level=level,
            response_text="You should rest.",
            possible_conditions=["cold"],
            recommended_actions=["rest"],
            sources=[],
            disclaimer=_DISCLAIMER,
        )

    def test_required_keys_present(self):
        d = self._make().to_dict()
        for key in (
            "triage_level",
            "response_text",
            "possible_conditions",
            "recommended_actions",
            "sources",
            "disclaimer",
            "needs_clarification",
            "clarification_question",
        ):
            assert key in d

    def test_triage_level_is_string(self):
        d = self._make(TriageLevel.RED).to_dict()
        assert d["triage_level"] == "RED"
        assert isinstance(d["triage_level"], str)

    def test_needs_clarification_default_false(self):
        assert self._make().to_dict()["needs_clarification"] is False

    def test_clarification_question_default_none(self):
        assert self._make().to_dict()["clarification_question"] is None


# ---------------------------------------------------------------------------
# _parse_triage_json (static method, tested directly)
# ---------------------------------------------------------------------------


class TestParseTriageJson:
    parse = staticmethod(TriageEngine._parse_triage_json)

    def test_valid_green(self):
        level, conditions, actions = self.parse(_triage_json("GREEN"))
        assert level == TriageLevel.GREEN
        assert conditions == ["condition A"]
        assert actions == ["rest", "hydrate"]

    def test_valid_yellow(self):
        level, _, _ = self.parse(_triage_json("YELLOW"))
        assert level == TriageLevel.YELLOW

    def test_valid_red(self):
        level, _, _ = self.parse(_triage_json("RED"))
        assert level == TriageLevel.RED

    def test_markdown_fences_stripped(self):
        wrapped = "```json\n" + _triage_json("GREEN") + "\n```"
        level, _, _ = self.parse(wrapped)
        assert level == TriageLevel.GREEN

    def test_unknown_level_defaults_to_yellow(self):
        text = '{"triage_level": "ORANGE", "possible_conditions": [], "recommended_actions": []}'
        level, _, _ = self.parse(text)
        assert level == TriageLevel.YELLOW

    def test_malformed_json_returns_defaults(self):
        level, conditions, actions = self.parse("not json at all")
        assert level == TriageLevel.YELLOW
        assert conditions == []
        assert actions == []

    def test_missing_fields_return_empty_lists(self):
        text = '{"triage_level": "GREEN"}'
        _, conditions, actions = self.parse(text)
        assert conditions == []
        assert actions == []

    def test_caps_conditions_at_five(self):
        text = (
            '{"triage_level": "GREEN", '
            '"possible_conditions": ["a","b","c","d","e","f","g"], '
            '"recommended_actions": []}'
        )
        _, conditions, _ = self.parse(text)
        assert len(conditions) == 5

    def test_extra_text_around_json(self):
        text = (
            "Sure! Here is the JSON:\n" + _triage_json("YELLOW") + "\nHope that helps."
        )
        level, _, _ = self.parse(text)
        assert level == TriageLevel.YELLOW


# ---------------------------------------------------------------------------
# _format_context (static method)
# ---------------------------------------------------------------------------


class TestFormatContext:
    fmt = staticmethod(TriageEngine._format_context)

    def test_empty_returns_fallback(self):
        result = self.fmt([])
        assert "No additional" in result

    def test_includes_chunk_text(self):
        r = _make_retrieval_result()
        text = self.fmt([r])
        assert "Chest pain" in text

    def test_includes_source(self):
        r = _make_retrieval_result()
        text = self.fmt([r])
        assert "cardiology.txt" in text

    def test_capped_at_four_results(self):
        results = [_make_retrieval_result(f"doc_{i}") for i in range(10)]
        text = self.fmt(results)
        assert "[4]" in text
        assert "[5]" not in text

    def test_numbered_citations(self):
        results = [_make_retrieval_result(f"doc_{i}") for i in range(3)]
        text = self.fmt(results)
        assert "[1]" in text and "[2]" in text and "[3]" in text


# ---------------------------------------------------------------------------
# Emergency / refusal regex sanity checks
# ---------------------------------------------------------------------------


class TestEmergencyRegex:
    def test_chest_pain_english(self):
        assert _EMERGENCY_RE.search("I have chest pain")

    def test_shortness_of_breath(self):
        assert _EMERGENCY_RE.search("shortness of breath")

    def test_heart_attack(self):
        assert _EMERGENCY_RE.search("heart attack symptoms")

    def test_normal_headache_not_emergency(self):
        assert not _EMERGENCY_RE.search("I have a mild headache")

    def test_franco_arab_emergency(self):
        assert _EMERGENCY_RE.search("waja3 sadr ktir")


class TestRefusalRegex:
    def test_infant_arabic(self):
        assert _REFUSAL_RE.search("\u0631\u0636\u064a\u0639")  # رضيع

    def test_lab_result_arabic(self):
        assert _REFUSAL_RE.search(
            "\u0646\u062a\u064a\u062c\u0629 \u062a\u062d\u0644\u064a\u0644"
        )

    def test_normal_query_not_refused(self):
        assert not _REFUSAL_RE.search("I have a headache and fever")


# ---------------------------------------------------------------------------
# TriageEngine.triage() -- integration tests with all deps mocked
# ---------------------------------------------------------------------------


class TestTriageEngineIntegration:
    def _engine(
        self,
        llm_responses: list[str] | None = None,
        symptoms: list | None = None,
        rag_results: list | None = None,
        include_rag: bool = False,
    ) -> TriageEngine:
        if llm_responses:
            responses = [_llm_response(t, 40) for t in llm_responses]
            llm = MagicMock()
            llm.generate = AsyncMock(side_effect=responses)
        else:
            llm = _mock_llm(_triage_json("GREEN"), 40)
        proc = _mock_proc(symptoms if symptoms is not None else [])
        rag = _mock_rag(rag_results) if include_rag else None
        return TriageEngine(llm_client=llm, arabic_processor=proc, rag_pipeline=rag)

    # ------ safety refusal ------

    @pytest.mark.asyncio
    async def test_refusal_for_infant_query(self):
        engine = self._engine()
        result = await engine.triage(
            "\u0631\u0636\u064a\u0639 \u0639\u0646\u062f\u0647 \u062d\u0645\u0649"
        )
        assert result.triage_level == TriageLevel.YELLOW
        assert result.possible_conditions == []
        assert result.sources == []

    @pytest.mark.asyncio
    async def test_refusal_does_not_call_llm(self):
        llm = _mock_llm()
        proc = _mock_proc([])
        engine = TriageEngine(llm_client=llm, arabic_processor=proc)
        await engine.triage("\u0631\u0636\u064a\u0639")  # رضيع
        llm.generate.assert_not_called()

    # ------ emergency fast-path ------

    @pytest.mark.asyncio
    async def test_emergency_returns_red(self):
        engine = self._engine(llm_responses=["Go to ER immediately."])
        result = await engine.triage("I have chest pain right now")
        assert result.triage_level == TriageLevel.RED

    @pytest.mark.asyncio
    async def test_emergency_uses_emergency_disclaimer(self):
        engine = self._engine(llm_responses=["Go to ER!"])
        result = await engine.triage("chest pain")
        assert result.disclaimer == _EMERGENCY_DISCLAIMER

    @pytest.mark.asyncio
    async def test_emergency_skips_rag(self):
        rag = _mock_rag()
        llm = _mock_llm("Go to ER!", 40)
        proc = _mock_proc([])
        engine = TriageEngine(llm_client=llm, arabic_processor=proc, rag_pipeline=rag)
        await engine.triage("chest pain")
        rag.retrieve.assert_not_called()

    @pytest.mark.asyncio
    async def test_emergency_calls_llm_once(self):
        llm = MagicMock()
        llm.generate = AsyncMock(return_value=_llm_response("Emergency response."))
        proc = _mock_proc([])
        engine = TriageEngine(llm_client=llm, arabic_processor=proc)
        await engine.triage("chest pain")
        assert llm.generate.call_count == 1

    # ------ clarification ------

    @pytest.mark.asyncio
    async def test_vague_query_requests_clarification(self):
        engine = self._engine(
            llm_responses=["When did this start?"],
            symptoms=[],  # no symptoms extracted
        )
        result = await engine.triage("pain")  # < 4 words, < 2 symptoms
        assert result.needs_clarification is True
        assert result.clarification_question == "When did this start?"

    @pytest.mark.asyncio
    async def test_clarification_calls_llm_once(self):
        llm = MagicMock()
        llm.generate = AsyncMock(return_value=_llm_response("When?"))
        proc = _mock_proc([])
        engine = TriageEngine(llm_client=llm, arabic_processor=proc)
        await engine.triage("pain")
        assert llm.generate.call_count == 1

    @pytest.mark.asyncio
    async def test_sufficient_symptoms_skip_clarification(self):
        symptoms = [_make_symptom("waja3"), _make_symptom("7arara", "fever", "fever")]
        engine = self._engine(
            llm_responses=[_triage_json("GREEN"), "You should rest."],
            symptoms=symptoms,
        )
        result = await engine.triage("3andi waja3 w 7arara")
        assert result.needs_clarification is False

    # ------ full pipeline ------

    @pytest.mark.asyncio
    async def test_full_pipeline_green_result(self):
        symptoms = [_make_symptom(), _make_symptom("7arara", "fever", "fever")]
        engine = self._engine(
            llm_responses=[_triage_json("GREEN"), "You can rest at home."],
            symptoms=symptoms,
        )
        result = await engine.triage("3andi waja3 w 7arara")
        assert result.triage_level == TriageLevel.GREEN
        assert result.response_text == "You can rest at home."
        assert result.possible_conditions == ["condition A"]
        assert result.disclaimer == _DISCLAIMER

    @pytest.mark.asyncio
    async def test_full_pipeline_yellow_result(self):
        symptoms = [_make_symptom(), _make_symptom("7arara", "fever", "fever")]
        engine = self._engine(
            llm_responses=[_triage_json("YELLOW"), "See a doctor soon."],
            symptoms=symptoms,
        )
        result = await engine.triage("3andi waja3 w 7arara")
        assert result.triage_level == TriageLevel.YELLOW

    @pytest.mark.asyncio
    async def test_full_pipeline_red_uses_emergency_disclaimer(self):
        symptoms = [_make_symptom(), _make_symptom("7arara", "fever", "fever")]
        engine = self._engine(
            llm_responses=[_triage_json("RED"), "Go to ER now."],
            symptoms=symptoms,
        )
        result = await engine.triage("3andi waja3 w 7arara")
        assert result.triage_level == TriageLevel.RED
        assert result.disclaimer == _EMERGENCY_DISCLAIMER

    @pytest.mark.asyncio
    async def test_full_pipeline_calls_llm_twice(self):
        llm = MagicMock()
        llm.generate = AsyncMock(
            side_effect=[
                _llm_response(_triage_json("GREEN"), 40),
                _llm_response("Rest at home.", 40),
            ]
        )
        symptoms = [_make_symptom(), _make_symptom("hammy", "fever", "fever")]
        proc = _mock_proc(symptoms)
        engine = TriageEngine(llm_client=llm, arabic_processor=proc)
        await engine.triage("3andi waja3 w 7arara")
        assert llm.generate.call_count == 2

    @pytest.mark.asyncio
    async def test_prior_symptoms_skip_extraction(self):
        proc = _mock_proc()
        llm = MagicMock()
        llm.generate = AsyncMock(
            side_effect=[
                _llm_response(_triage_json("GREEN"), 40),
                _llm_response("Rest.", 40),
            ]
        )
        engine = TriageEngine(llm_client=llm, arabic_processor=proc)
        prior = [_make_symptom(), _make_symptom("hammy", "fever", "fever")]
        await engine.triage("query text", prior_symptoms=prior)
        proc.extract_symptoms.assert_not_called()

    # ------ RAG integration ------

    @pytest.mark.asyncio
    async def test_rag_called_when_provided(self):
        rag = _mock_rag([_make_retrieval_result()])
        llm = MagicMock()
        llm.generate = AsyncMock(
            side_effect=[
                _llm_response(_triage_json("GREEN"), 40),
                _llm_response("Rest.", 40),
            ]
        )
        symptoms = [_make_symptom(), _make_symptom("hammy", "fever", "fever")]
        proc = _mock_proc(symptoms)
        engine = TriageEngine(llm_client=llm, arabic_processor=proc, rag_pipeline=rag)
        result = await engine.triage("3andi waja3 w 7arara")
        rag.retrieve.assert_called_once()
        assert len(result.sources) == 1

    @pytest.mark.asyncio
    async def test_rag_skipped_when_none(self):
        llm = MagicMock()
        llm.generate = AsyncMock(
            side_effect=[
                _llm_response(_triage_json("GREEN"), 40),
                _llm_response("Rest.", 40),
            ]
        )
        symptoms = [_make_symptom(), _make_symptom("hammy", "fever", "fever")]
        proc = _mock_proc(symptoms)
        engine = TriageEngine(llm_client=llm, arabic_processor=proc, rag_pipeline=None)
        result = await engine.triage("3andi waja3 w 7arara")
        assert result.sources == []

    # ------ token counting ------

    @pytest.mark.asyncio
    async def test_total_tokens_accumulated(self):
        llm = MagicMock()
        llm.generate = AsyncMock(
            side_effect=[
                _llm_response(_triage_json("GREEN"), 60),
                _llm_response("Rest.", 80),
            ]
        )
        symptoms = [_make_symptom(), _make_symptom("hammy", "fever", "fever")]
        proc = _mock_proc(symptoms)
        engine = TriageEngine(llm_client=llm, arabic_processor=proc)
        result = await engine.triage("waja3 w 7arara w dawkha")
        assert result.total_tokens == 140

    # ------ to_dict round-trip ------

    @pytest.mark.asyncio
    async def test_to_dict_serializable(self):
        import json as _json

        symptoms = [_make_symptom(), _make_symptom("hammy", "fever", "fever")]
        engine = self._engine(
            llm_responses=[_triage_json("GREEN"), "Rest."],
            symptoms=symptoms,
        )
        result = await engine.triage("3andi waja3 w 7arara")
        # Should not raise
        serialized = _json.dumps(result.to_dict())
        assert "triage_level" in serialized
