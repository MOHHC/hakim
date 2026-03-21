# Monorepo Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap the hakim monorepo with a working FastAPI backend (/health → {"status":"ok"} on :8000) and React+TypeScript+Tailwind frontend (placeholder on :3000), plus all config files.

**Architecture:** Python monorepo with `backend/` using FastAPI + uvicorn and `frontend/` using Vite+React+TS+Tailwind. Docker Compose orchestrates both. Environment variables managed via `.env.example`.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, pyproject.toml, React 18, TypeScript, Tailwind CSS, Vite, Docker Compose

---

## File Map

### Created
- `backend/pyproject.toml` — Python project metadata + dependencies
- `backend/app/__init__.py`
- `backend/app/main.py` — FastAPI app factory, CORS, router registration
- `backend/app/config.py` — Settings via pydantic-settings
- `backend/app/api/__init__.py`
- `backend/app/api/routes/__init__.py`
- `backend/app/api/routes/health.py` — GET /health
- `backend/app/api/routes/chat.py` — stub
- `backend/app/api/routes/triage.py` — stub
- `backend/app/api/middleware/__init__.py`
- `backend/app/api/middleware/cors.py` — CORS config
- `backend/app/api/middleware/rate_limiter.py` — stub
- `backend/app/core/__init__.py`
- `backend/app/core/arabic_processor.py` — stub
- `backend/app/core/medical_lexicon.py` — stub
- `backend/app/core/triage_engine.py` — stub
- `backend/app/core/rag_pipeline.py` — stub
- `backend/app/core/safety_guardrails.py` — stub
- `backend/app/core/llm_client.py` — stub
- `backend/app/knowledge/__init__.py`
- `backend/app/knowledge/ingest.py` — stub
- `backend/app/knowledge/embeddings.py` — stub
- `backend/app/knowledge/vector_store.py` — stub
- `backend/app/data/lexicon/lebanese_medical.json` — empty seed
- `backend/app/data/lexicon/symptom_categories.json` — empty seed
- `backend/tests/__init__.py`
- `backend/tests/test_health.py` — health endpoint test
- `backend/eval/scenarios.json` — empty seed
- `backend/eval/run_eval.py` — stub
- `frontend/` — Vite React TS scaffold
- `frontend/src/components/` — stub files per CLAUDE.md
- `frontend/src/hooks/` — stub files
- `frontend/src/types/index.ts` — shared types stub
- `docker-compose.yml`
- `.gitignore`
- `.env.example`
- `README.md`
- `docs/ARCHITECTURE.md` — stub
- `docs/API.md` — stub
- `docs/SAFETY.md` — stub
- `docs/EVALUATION.md` — stub
- `docs/CONTRIBUTING.md` — stub

---

### Task 1: Backend Python project + /health endpoint

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/app/api/routes/health.py`
- Test: `backend/tests/test_health.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_health.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_health.py -v
```
Expected: ImportError or ModuleNotFoundError (app doesn't exist yet)

- [ ] **Step 3: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "hakim-backend"
version = "0.1.0"
description = "Hakim medical triage AI backend"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.2.0",
    "python-dotenv>=1.0.0",
    "httpx>=0.27.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 4: Create app/config.py**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Hakim"
    debug: bool = False
    gemini_api_key: str = ""
    groq_api_key: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    allowed_origins: str = "http://localhost:3000"

settings = Settings()
```

- [ ] **Step 5: Create app/api/routes/health.py**

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 6: Create app/main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.routes.health import router as health_router

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
```

- [ ] **Step 7: Create all `__init__.py` files**

```bash
touch backend/app/__init__.py
touch backend/app/api/__init__.py
touch backend/app/api/routes/__init__.py
touch backend/app/api/middleware/__init__.py
touch backend/app/core/__init__.py
touch backend/app/knowledge/__init__.py
touch backend/tests/__init__.py
```

- [ ] **Step 8: Install deps and run test**

```bash
cd backend && pip install -e ".[dev]" && python -m pytest tests/test_health.py -v
```
Expected: PASSED

- [ ] **Step 9: Verify uvicorn starts**

```bash
cd backend && uvicorn app.main:app --reload --port 8000 &
sleep 2 && curl http://localhost:8000/health
```
Expected: `{"status":"ok"}`

- [ ] **Step 10: Commit**

```bash
git add backend/
git commit -m "feat: add FastAPI backend with /health endpoint"
```

---

### Task 2: Backend stub modules + data seeds

**Files:** All stub files in core/, knowledge/, data/

- [ ] **Step 1: Create stub core modules**

Each file gets a module-level docstring and a `# TODO` comment only.

```python
# backend/app/core/arabic_processor.py
"""Arabic/Lebanese dialect NLP preprocessing."""
# TODO: Implement transliteration, normalization, Franco-Arab handling
```

Repeat pattern for: `medical_lexicon.py`, `triage_engine.py`, `rag_pipeline.py`, `safety_guardrails.py`, `llm_client.py`

- [ ] **Step 2: Create stub knowledge modules**

Same pattern for: `ingest.py`, `embeddings.py`, `vector_store.py`

- [ ] **Step 3: Create data seed files**

```json
// backend/app/data/lexicon/lebanese_medical.json
{}
```

```json
// backend/app/data/lexicon/symptom_categories.json
{}
```

```json
// backend/eval/scenarios.json
[]
```

- [ ] **Step 4: Create eval/run_eval.py stub**

```python
"""Evaluation runner for triage scenarios."""
# TODO: Load scenarios.json, run triage engine, score results
```

- [ ] **Step 5: Create stub route files**

```python
# backend/app/api/routes/chat.py
from fastapi import APIRouter
router = APIRouter()
# TODO: POST /chat endpoint
```

```python
# backend/app/api/routes/triage.py
from fastapi import APIRouter
router = APIRouter()
# TODO: POST /triage endpoint
```

```python
# backend/app/api/middleware/cors.py
"""CORS configuration."""
# TODO: Extract CORS settings to this module
```

```python
# backend/app/api/middleware/rate_limiter.py
"""Rate limiting middleware."""
# TODO: Implement per-IP rate limiting
```

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "feat: add backend stub modules and data seeds"
```

---

### Task 3: React + TypeScript + Tailwind frontend

**Files:** `frontend/` — full Vite scaffold

- [ ] **Step 1: Scaffold with Vite**

```bash
cd d:/Hakim/hakim && npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

- [ ] **Step 2: Configure Tailwind**

Edit `frontend/tailwind.config.js`:
```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: { extend: {} },
  plugins: [],
}
```

Edit `frontend/src/index.css` — replace content with:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 3: Create placeholder App.tsx**

```tsx
// frontend/src/App.tsx
export default function App() {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center" dir="rtl">
      <div className="text-center">
        <h1 className="text-4xl font-bold text-gray-900 mb-2">حكيم</h1>
        <p className="text-lg text-gray-500">Hakim — Arabic Medical Triage AI</p>
        <p className="mt-4 text-sm text-gray-400">Coming soon — Phase 1 in progress</p>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Create component stub files**

Create these files with a stub functional component each:
- `frontend/src/components/ChatInterface.tsx`
- `frontend/src/components/MessageBubble.tsx`
- `frontend/src/components/TriageBadge.tsx`
- `frontend/src/components/SymptomHistory.tsx`
- `frontend/src/components/SourceCitation.tsx`
- `frontend/src/components/DisclaimerBanner.tsx`
- `frontend/src/components/RTLWrapper.tsx`

Pattern:
```tsx
// frontend/src/components/ChatInterface.tsx
/** TODO: Main chat interface component */
export default function ChatInterface() {
  return <div>ChatInterface — TODO</div>
}
```

- [ ] **Step 5: Create hook stubs**

```tsx
// frontend/src/hooks/useChat.ts
/** TODO: Chat state management hook */
export function useChat() {
  return {}
}
```

```tsx
// frontend/src/hooks/useTriage.ts
/** TODO: Triage state hook */
export function useTriage() {
  return {}
}
```

- [ ] **Step 6: Create types stub**

```ts
// frontend/src/types/index.ts
export type TriageLevel = "GREEN" | "YELLOW" | "RED"

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: Date
}

export interface TriageResult {
  level: TriageLevel
  conditions: string[]
  nextSteps: string[]
  disclaimer: string
}
```

- [ ] **Step 7: Verify frontend runs**

```bash
cd frontend && npm run dev -- --port 3000
```
Expected: Vite dev server on http://localhost:3000, placeholder page visible

- [ ] **Step 8: Commit**

```bash
git add frontend/
git commit -m "feat: add React+TS+Tailwind frontend with placeholder page"
```

---

### Task 4: Root config files

**Files:** `docker-compose.yml`, `.gitignore`, `.env.example`, `README.md`, `docs/*.md`

- [ ] **Step 1: Create docker-compose.yml**

```yaml
version: "3.9"

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - ./backend:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    env_file: .env
    volumes:
      - ./frontend:/app
      - /app/node_modules
    command: npm run dev -- --host 0.0.0.0 --port 3000
```

- [ ] **Step 2: Create .env.example**

```bash
# LLM APIs
GEMINI_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here

# Observability
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key_here
LANGFUSE_SECRET_KEY=your_langfuse_secret_key_here
LANGFUSE_HOST=https://cloud.langfuse.com

# App settings
APP_NAME=Hakim
DEBUG=false
ALLOWED_ORIGINS=http://localhost:3000

# Frontend
VITE_API_URL=http://localhost:8000
```

- [ ] **Step 3: Create .gitignore**

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
.venv/
venv/
.pytest_cache/
.mypy_cache/
*.db

# Node
node_modules/
dist/
.next/

# Env
.env
.env.local
.env.*.local

# ChromaDB
chroma_db/

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/
```

- [ ] **Step 4: Create README.md**

```markdown
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
| Frontend | React 18, TypeScript, Tailwind CSS, Vite |
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
```

- [ ] **Step 5: Create doc stubs**

```bash
for f in ARCHITECTURE API SAFETY EVALUATION CONTRIBUTING; do
  echo "# $f\n\nTODO" > docs/$f.md
done
```

- [ ] **Step 6: Commit everything**

```bash
git add .
git commit -m "feat: add docker-compose, .gitignore, .env.example, README, docs stubs"
```

---

### Task 5: Verify end-to-end

- [ ] **Step 1: Run backend health test**

```bash
cd backend && python -m pytest tests/test_health.py -v
```
Expected: `PASSED`

- [ ] **Step 2: Start backend, hit /health**

```bash
cd backend && uvicorn app.main:app --port 8000 &
curl http://localhost:8000/health
```
Expected: `{"status":"ok"}`

- [ ] **Step 3: Start frontend, verify loads**

```bash
cd frontend && npm run dev -- --port 3000 &
curl http://localhost:3000
```
Expected: HTML with "حكيم"

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "chore: verify foundation complete — backend :8000 and frontend :3000 running"
```
