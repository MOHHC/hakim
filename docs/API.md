# API Reference

**Base URL:** `https://hakim-vywt.onrender.com` (production) or `http://localhost:8000` (local)

Interactive docs available at `/docs` (Swagger) and `/redoc` (ReDoc).

---

## POST /api/chat

Conversational triage with streaming response via Server-Sent Events.

### Request

```bash
curl -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "عندي وجع راس من يومين وحرارة",
    "conversation_history": [],
    "language_preference": "auto",
    "response_script": "arabic"
  }'
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `message` | string (1-2000) | Yes | — | Symptom description in Arabic, Franco-Arab, or English |
| `conversation_history` | ChatMessage[] (max 20) | No | `[]` | Previous conversation turns |
| `language_preference` | `"arabic"` \| `"english"` \| `"auto"` | No | `"auto"` | Response language; `auto` detects from input |
| `response_script` | `"arabic"` \| `"franco"` | No | `"arabic"` | Arabic script or Franco-Arab Latin output |

**ChatMessage format:**

```json
{ "role": "user" | "assistant", "content": "message text" }
```

### Response (SSE Stream)

Content-Type: `text/event-stream`

Events are sent in this order:

**1. `start` — Pipeline accepted the request**
```
event: start
data: {}
```

**2. `blocked` — Safety guardrail triggered (stream ends)**
```
event: blocked
data: {"reason": "SCOPE_INFANT", "message": "خدي ابنك عالدكتور فوراً..."}
```

**3. `triage_classified` — Triage level determined**
```
event: triage_classified
data: {"triage_level": "YELLOW"}
```

**4. `chunk` — Response text token (repeated)**
```
event: chunk
data: {"text": "هيدا "}

event: chunk
data: {"text": "ممكن "}

event: chunk
data: {"text": "يكون..."}
```

**5. `complete` — Final metadata**
```
event: complete
data: {
  "triage_level": "YELLOW",
  "possible_conditions": ["tension headache", "viral infection"],
  "recommended_actions": ["rest", "fluids", "see doctor if fever persists 3+ days"],
  "sources": [{"title": "...", "content": "...", "relevance": 0.87}],
  "disclaimer": "⚠️ هيدا المعلومات ما بتغني عن زيارة الطبيب..."
}
```

**6. `[DONE]` — Stream terminator**
```
data: [DONE]
```

### Example: Franco-Arab Input

```bash
curl -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "3endi waja3 ras w 7arara",
    "response_script": "franco"
  }'
```

### Example: English Input

```bash
curl -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I have a headache and fever for two days",
    "language_preference": "english"
  }'
```

---

## POST /api/triage

Direct structured triage — single JSON response (non-streaming).

### Request

```bash
curl -X POST http://localhost:8000/api/triage \
  -H "Content-Type: application/json" \
  -d '{"query": "عندي وجع بطن وغثيان"}'
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string (1-2000) | Yes | Symptom description |

### Response (Success)

```json
{
  "triage_level": "YELLOW",
  "response_text": "هيدا ممكن يكون التهاب بالمعدة...",
  "possible_conditions": [
    "gastritis",
    "food poisoning",
    "gastroenteritis"
  ],
  "recommended_actions": [
    "Stay hydrated",
    "Avoid heavy food",
    "See a doctor if vomiting persists 24h+"
  ],
  "sources": [
    {
      "title": "Gastrointestinal Disorders",
      "content": "Nausea combined with abdominal pain...",
      "relevance": 0.91
    }
  ],
  "disclaimer": "⚠️ هيدا المعلومات ما بتغني عن زيارة الطبيب...",
  "needs_clarification": false,
  "clarification_question": null
}
```

### Response (Safety Block)

HTTP 200 (not 4xx):

```json
{
  "blocked": true,
  "reason": "SCOPE_PREGNANCY",
  "message": "هيدا الموضوع لازم تحكي فيه مع دكتور/ة النسائية..."
}
```

### Response (Vague Input)

```json
{
  "triage_level": "GREEN",
  "response_text": "...",
  "possible_conditions": [],
  "recommended_actions": [],
  "sources": [],
  "disclaimer": "...",
  "needs_clarification": true,
  "clarification_question": "ممكن توصفلي أكتر شو عم تحس فيه بالزبط؟"
}
```

### Example: Emergency

```bash
curl -X POST http://localhost:8000/api/triage \
  -H "Content-Type: application/json" \
  -d '{"query": "عندي وجع صدر قوي وخدران بإيدي الشمال"}'
```

```json
{
  "triage_level": "RED",
  "response_text": "هيدي أعراض خطيرة كتير...",
  "possible_conditions": ["myocardial infarction", "angina"],
  "recommended_actions": ["Call 140 immediately", "Go to nearest ER"],
  "sources": [...],
  "disclaimer": "🚨 هيدي الأعراض بتحتاج عناية طبية فورية..."
}
```

---

## GET /api/health

System health check. Used by Render for deployment health monitoring.

### Request

```bash
curl http://localhost:8000/api/health
```

### Response

```json
{
  "status": "ok",
  "version": "0.1.0",
  "timestamp": "2025-01-15T10:30:00Z",
  "components": {
    "llm": {
      "status": "ok",
      "details": "Gemini key present"
    },
    "vector_store": {
      "status": "ok",
      "details": "142 documents"
    },
    "arabic_processor": {
      "status": "ok",
      "details": "246 lexicon entries"
    }
  }
}
```

**Status values:**
- `"ok"` — All components healthy
- `"degraded"` — Some components unavailable (e.g., no Gemini key, empty vector store)

---

## Error Responses

### Rate Limited (429)

```json
{
  "detail": "Rate limit exceeded. Please try again later."
}
```

Headers: `Retry-After: 42` (seconds until next allowed request)

Rate limit: **10 requests / 60 seconds** per IP.

### Validation Error (422)

```json
{
  "detail": [
    {
      "loc": ["body", "message"],
      "msg": "String should have at most 2000 characters",
      "type": "string_too_long"
    }
  ]
}
```

### Internal Error (500)

```json
{
  "detail": "Internal server error"
}
```

---

## CORS

The API accepts requests from origins configured in the `ALLOWED_ORIGINS` environment variable (comma-separated). Default: `http://localhost:3000`.

All methods and headers are allowed. Credentials are supported.

---

## Rate Limiting

Sliding window algorithm, per-IP:

- **Window:** 60 seconds
- **Max requests:** 10
- **Exempt:** OPTIONS (CORS preflight)
- **Response:** HTTP 429 with `Retry-After` header
