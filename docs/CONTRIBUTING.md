# Contributing

Thank you for considering contributing to Hakim! This guide will help you get started.

## Getting Started

### 1. Fork and Clone

```bash
git clone https://github.com/YOUR_USERNAME/hakim.git
cd hakim
```

### 2. Set Up Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate    # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

### 3. Set Up Frontend

```bash
cd frontend
npm install
```

### 4. Environment Variables

```bash
cp .env.example .env
# Fill in at minimum: GEMINI_API_KEY
```

### 5. Run Locally

```bash
# Terminal 1: Backend
cd backend
uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
echo "VITE_API_URL=http://localhost:8000" > .env
npm run dev
```

## Code Style

### Python (Backend)

- **Formatter:** [ruff](https://docs.astral.sh/ruff/) (format + lint)
- **Type hints:** Required on all function signatures
- **Async:** Use `async/await` for all I/O operations
- **Imports:** Sorted by ruff (isort-compatible)

```bash
cd backend
ruff check .           # Lint
ruff format --check .  # Format check
ruff format .          # Auto-format
```

### TypeScript (Frontend)

- **Linter:** ESLint with TypeScript plugin
- **No `any` types** — use proper typing or `unknown`
- **Functional components** — no class components
- **Inline styles** — project uses inline `style={}` objects, not CSS classes for component-specific styles

```bash
cd frontend
npm run lint           # ESLint check
npm run build          # TypeScript check + build
```

### General

- No trailing whitespace
- Files end with a newline
- UTF-8 encoding everywhere
- Meaningful variable names (no abbreviations except well-known ones)

## Making Changes

### Branch Naming

```
feature/add-voice-input
fix/franco-arab-transliteration
docs/update-api-reference
```

### Commit Messages

Use clear, concise messages. Start with a verb:

```
Add Egyptian dialect terms to medical lexicon
Fix emergency detection for compound cardiac patterns
Update API docs with new triage response fields
```

### What to Work On

**Good first issues:**
- Add new terms to the Lebanese medical lexicon (`backend/app/data/lexicon/lebanese_medical.json`)
- Add new evaluation scenarios (`backend/tests/eval/scenarios.json`)
- Improve Arabic translations (`frontend/src/context/LanguageContext.tsx`)
- Fix typos in documentation

**Larger contributions:**
- Support for additional Arabic dialects (Egyptian, Gulf, Moroccan)
- Voice input / speech-to-text
- Multi-turn follow-up conversation support
- New medical knowledge sources for the RAG pipeline

## Pull Request Process

### 1. Before Opening a PR

- [ ] Run the linters: `ruff check .` and `npm run lint`
- [ ] Run the tests: `pytest --tb=short -q`
- [ ] Run the build: `npm run build`
- [ ] If you changed triage logic, run the eval: `python -m tests.eval.run_eval --skip-quality`
- [ ] Verify emergency recall is still >= 95%

### 2. PR Format

**Title:** Short, imperative (under 70 chars)

**Body:**

```markdown
## Summary
- What changed and why (1-3 bullet points)

## Test Plan
- [ ] How to verify this change works
- [ ] Any specific scenarios to test
```

### 3. Review

- PRs require at least one approval
- CI must pass (lint, test, eval, build)
- Emergency recall gate (95%) must pass

## Safety Guidelines

If your change touches the triage pipeline, safety guardrails, or LLM prompts:

1. **Never weaken safety checks.** If you need to modify a guardrail, explain why in the PR.
2. **Add eval scenarios** for any new triage behavior.
3. **Test edge cases** — especially around the GREEN/YELLOW/RED boundaries.
4. **Don't remove disclaimers** or reduce their prominence.
5. **No medication recommendations** — this is a hard rule, even in test fixtures.

## Adding Lexicon Terms

The Lebanese medical lexicon (`backend/app/data/lexicon/lebanese_medical.json`) is the heart of Hakim's Arabic understanding. To add terms:

```json
{
  "dialect_term": "دوخة",
  "dialect_term_latin": "dawkha",
  "msa_equivalent": "دوار",
  "english_medical_term": "dizziness / vertigo",
  "category": "common_symptoms",
  "body_system": "neurological",
  "severity_hint": "mild_to_moderate"
}
```

**Fields:**
- `dialect_term` — Lebanese Arabic script
- `dialect_term_latin` — Franco-Arab transliteration (use 3=ع, 7=ح, 5=خ, 2=ء, 8=ق)
- `msa_equivalent` — Modern Standard Arabic
- `english_medical_term` — English medical term(s)
- `category` — One of: pain_descriptions, body_parts, common_symptoms, chronic_conditions, emergency_phrases, mental_health, childrens_symptoms, digestive, respiratory, cardiovascular
- `body_system` — Anatomical system
- `severity_hint` — `mild_to_moderate`, `moderate`, `severe`, `emergency`

## Adding Evaluation Scenarios

See [EVALUATION.md](EVALUATION.md#adding-new-scenarios) for the scenario format and guidelines.

## Questions?

Open an issue on GitHub. For safety-related concerns, please use the "Safety" issue label.
