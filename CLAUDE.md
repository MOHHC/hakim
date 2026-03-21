# Hakim (حكيم) — Arabic Medical Triage AI Agent

## What This Project Is

Hakim is an open-source AI-powered medical triage assistant for Arabic speakers, with native support for Lebanese dialect and Franco-Arab input. It takes symptom descriptions in everyday Lebanese Arabic, triages urgency (GREEN/YELLOW/RED), suggests possible conditions with medical citations, and recommends next steps — all with strict safety guardrails.

## Tech Stack

- Backend: FastAPI + Python 3.11
- Frontend: React 18 + TypeScript + Tailwind CSS
- Vector DB: ChromaDB (local)
- LLM: Google Gemini API (free tier), Groq (fallback)
- Embeddings: Gemini text-embedding-004
- Observability: Langfuse
- Hosting: Vercel (frontend) + Render (backend)
- CI/CD: GitHub Actions

## Project Structure

hakim/
├── CLAUDE.md
├── README.md
├── LICENSE
├── docker-compose.yml
├── .github/workflows/
├── backend/
│ ├── app/
│ │ ├── main.py
│ │ ├── config.py
│ │ ├── api/routes/ (chat.py, triage.py, health.py)
│ │ ├── api/middleware/ (rate_limiter.py, cors.py)
│ │ ├── core/ (arabic_processor.py, medical_lexicon.py, triage_engine.py, rag_pipeline.py, safety_guardrails.py, llm_client.py)
│ │ ├── knowledge/ (ingest.py, embeddings.py, vector_store.py)
│ │ └── data/lexicon/ (lebanese_medical.json, symptom_categories.json)
│ └── tests/
│ └── eval/ (scenarios.json, run_eval.py)
├── frontend/
│ └── src/
│ ├── components/ (ChatInterface, MessageBubble, TriageBadge, SymptomHistory, SourceCitation, DisclaimerBanner, RTLWrapper)
│ ├── hooks/ (useChat, useTriage)
│ └── types/
└── docs/ (ARCHITECTURE.md, API.md, SAFETY.md, EVALUATION.md, CONTRIBUTING.md)

## Safety Rules (Non-Negotiable)

- NEVER provide a diagnosis — always say "possible conditions"
- NEVER recommend specific medications or dosages
- ALWAYS include disclaimer that this is not medical advice
- Detect emergency keywords and immediately escalate to RED triage
- Refuse to triage children under 2, pregnancy complications, or lab results
- If uncertain, say "I'm not sure, please consult a doctor"

## Current Progress

- [ ] Phase 1: Foundation & Arabic NLP
- [ ] Phase 2: Knowledge Base & RAG Pipeline
- [ ] Phase 3: Triage Engine & Safety
- [ ] Phase 4: Full-Stack Application
- [ ] Phase 5: Evaluation & Testing
- [ ] Phase 6: Deployment & Polish

## Workflow Orchestration

### 1. Plan Mode Default

- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy

- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop

- After ANY correction from the user: update tasks/lessons.md with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done

- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance （Balanced）

- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it

### 6.Autonomous Bug Fixing

- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, talling tests - then resolve them
- Zero context switching required from the user
- Go fix failing Cl tests without being told how

### Task Management

1. Plan First: Write plan to tasks/todo.md with checkable items
2. Verify Plan: Check in before starting implementation
3. Track Progress: Mark items complete as you go
4. Explain Changes: High-level summary at each step
5. Document Results: Add review section to tasks/todo.md
6. Capture Lessons: Update tasks/lessons.md after corrections ## Core Principles

- Simplicity First: Make every change as simple as possible. Impact minimal code.
- No Laziness: Find root causes. No temporary fixes. Senior developer standards.
- Minimal Impact: Only touch what's necessary. No side effects with new bugs.
