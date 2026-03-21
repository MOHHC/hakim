# Hakim (حكيم)

> Arabic Medical Triage AI Agent — native Lebanese dialect support, strict safety guardrails.

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+
- (Optional) Docker

### Backend

```bash
cd backend
pip install -e ".[dev]"
cp ../.env.example ../.env  # fill in API keys
uvicorn app.main:app --reload --port 8000
```

Health check: http://localhost:8000/health

### Frontend

```bash
cd frontend
npm install
npm run dev -- --port 3000
```

App: http://localhost:3000

### Docker

```bash
cp .env.example .env  # fill in keys
docker compose up
```

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI, Python 3.11, uvicorn |
| Frontend | React 18, TypeScript, Tailwind CSS v4, Vite |
| Vector DB | ChromaDB |
| LLM | Gemini API (primary), Groq (fallback) |
| Observability | Langfuse |

## Safety

This tool provides triage guidance only — it is **not** a diagnostic tool and **not** a substitute for professional medical advice. See [docs/SAFETY.md](docs/SAFETY.md).

## Roadmap

- [ ] Phase 1: Foundation & Arabic NLP
- [ ] Phase 2: Knowledge Base & RAG Pipeline
- [ ] Phase 3: Triage Engine & Safety
- [ ] Phase 4: Full-Stack Application
- [ ] Phase 5: Evaluation & Testing
- [ ] Phase 6: Deployment & Polish
