# Safety

## Philosophy

Hakim operates on one principle: **when in doubt, escalate**. A false alarm (telling someone to see a doctor when they didn't need to) is always preferable to a missed emergency. The system is designed to be conservative — it will never tell someone they're fine when there's any possibility they're not.

Hakim is **not** a diagnostic tool. It is a triage assistant that helps people understand urgency and take appropriate next steps. Every response includes a disclaimer, and the app itself displays a persistent warning banner.

## What Hakim Will Never Do

### 1. Provide a Diagnosis

Hakim never says "you have [condition]." It says "possible conditions" or "this may suggest." This is enforced at two levels:

- **Prompt engineering:** The LLM system prompt explicitly forbids diagnosis language
- **Post-processing:** Output sanitization catches and softens any diagnosis assertions that slip through (e.g., "you have pneumonia" -> "you may have pneumonia")

### 2. Recommend Medications or Dosages

No drug names, no dosages, no "take ibuprofen." This is enforced by:

- **Prompt engineering:** System prompt forbids medication recommendations
- **Post-processing:** Regex-based stripping removes medication names and dosage patterns from LLM output (e.g., "take 500mg paracetamol" -> "[medication advice removed]")

### 3. Triage Certain Cases

Hakim refuses to process and redirects to professionals for:

| Category | Why | Response |
|----------|-----|----------|
| **Infants < 2 years** | Symptoms in infants are too ambiguous for AI triage; rapid deterioration risk is high | "Please take your child to a pediatrician or emergency room immediately" |
| **Pregnancy complications** | Pregnancy-related symptoms require specialized obstetric assessment | "Please contact your OB/GYN or go to the nearest hospital" |
| **Lab results** | Interpreting blood tests, imaging, or ECG requires clinical context Hakim doesn't have | "Please discuss these results with your doctor" |
| **Suicidal ideation** | Mental health crises require human intervention, not AI | Crisis helpline referral with emergency number |

## Emergency Detection

### Compound Patterns

Hakim uses compound symptom patterns to detect emergencies. A single symptom like "chest pain" is not enough — it requires a combination:

| Emergency | Pattern A | Pattern B | Triage |
|-----------|-----------|-----------|--------|
| **Cardiac event** | Chest pain (صدر وجع) | + arm numbness, jaw pain, sweating | RED |
| **Anaphylaxis** | Throat swelling (حساسية شديدة) | + difficulty breathing | RED |
| **Head trauma** | Head injury (ضربت راسي) | + vomiting, seizure, unconsciousness | RED |
| **Stroke** | Facial drooping, slurred speech | + limb weakness, confusion | RED |

### Emergency Keywords

Certain phrases trigger immediate RED classification without compound matching:

- Difficulty breathing / صعوبة تنفس / ma be2der etnafs
- Loss of consciousness / فقدان وعي / dayakh w we2e3
- Severe bleeding / نزيف شديد / dam ktir
- "Can't breathe" / "مش قادر اتنفس"
- "Heart attack" / "جلطة"

### Emergency Response

When RED triage is triggered, Hakim:

1. Immediately classifies as RED (no retrieval delay)
2. Generates an urgent response in the user's language
3. Appends emergency disclaimer: "These symptoms require IMMEDIATE emergency care. Call 140 or go to the ER now."
4. The frontend displays a pulsing red badge

## Guardrail Architecture

```
User Input
    |
    v
+---------------------------+
|  PRE-LLM SAFETY GATE      |
|  - Suicidal ideation       |  -> Block + crisis referral
|  - Scope: infant < 2y     |  -> Block + pediatrician referral
|  - Scope: pregnancy       |  -> Block + OB/GYN referral
|  - Scope: lab results     |  -> Block + doctor referral
|  - Emergency compound     |  -> RED fast-path
+---------------------------+
    | (safe)
    v
+---------------------------+
|  LLM GENERATION            |
|  System prompt includes:   |
|  - No diagnosis language   |
|  - No medications          |
|  - Lebanese dialect tone   |
+---------------------------+
    |
    v
+---------------------------+
|  POST-LLM SAFETY GATE     |
|  - Diagnosis softening     |  "you have" -> "you may have"
|  - Medication stripping    |  Drug names -> "[removed]"
|  - Disclaimer injection    |  Standard or emergency
+---------------------------+
    |
    v
  Response to User
```

## Violation Types (Priority Order)

1. **SUICIDAL_IDEATION** — Highest priority. Detected via keyword patterns in Arabic, Franco-Arab, and English. Response gives the Embrace Lifeline (1564) and the Red Cross (140), without the physical-emergency disclaimer.

   **Overdose / poisoning** ("took too many pills", "جرعة زايدة") is checked next and escalates as an EMERGENCY_RED_FLAG with force-RED.

2. **SCOPE_INFANT** — Triggered by a stated age under 2 years: "3 months old", "عمرو 3 أشهر", "3emro 5 ashhor", "عمرها سنة", "1 year old", or "infant", "newborn", "رضيع", "my baby". A duration ("pain for 3 months") is not an age and does not trigger it.

3. **SCOPE_PREGNANCY** — Triggered by pregnancy terms matched as whole words ("حامل", "بالحمل", "pregnant"), so "حملت" (I lifted) and "اتحمل" (bear) are not refused.

4. **SCOPE_LAB_RESULTS** — Triggered by lab/test terminology. Pattern: "blood test", "تحليل دم", "x-ray", "ECG", "MRI".

5. **EMERGENCY_RED_FLAG** — Compound emergency patterns (see table above).

6. **DIAGNOSIS_LANGUAGE** — Post-output only. Catches definitive assertions in LLM output.

7. **MEDICATION_REFERENCE** — Post-output only. Catches drug names and dosages in LLM output.

8. **SCOPE_MEDICATION** — Pre-input. Requests for a medicine or dose ("what dose of…", "شو دوا", "قديش حبة") are referred to a pharmacist or doctor instead of being triaged.

Refusals are returned in the patient's language (Arabic script, Franco-Arab, or English).

Infant and pregnancy refusals are escalated to RED (their replies send the patient to the ER or maternity unit immediately). All rules also match the query with hamza forms folded (أ/إ/آ → ا), so "إنتحار" and "انتحار" are treated alike.

## Emergencies without an LLM

The triage engine's emergency fast path (`_is_emergency`) recognises common red-flag presentations as patients phrase them in Arabic, Franco-Arab and English — chest pain, cyanosis, not breathing or unresponsive, stroke signs, anaphylaxis, coughing or vomiting blood, active seizures, and blood sugar ≥ 400 or ≤ 54 — and answers RED without calling a model. When every LLM provider is down, other queries fall back to YELLOW, or RED if the lexicon marks an extracted symptom critical. The evaluation runner counts fallback answers as a provider outage (inconclusive), never as triage results.

## Disclaimers

Every Hakim response includes a disclaimer. There are two variants:

**Standard (GREEN/YELLOW):**
> This information does not replace a doctor's consultation. If symptoms worsen or persist, please seek medical care.

**Emergency (RED):**
> These symptoms require IMMEDIATE emergency care. Call 140 (Lebanese Red Cross) or go to the nearest emergency room now.

The frontend also displays a persistent banner at the top of the app:
> This app is not a substitute for medical advice. In emergencies, call 140 (Red Cross) or go to the nearest hospital.

## Rate Limiting

To prevent abuse, the API enforces a sliding-window rate limit:

- **10 requests per 60 seconds** per IP address
- CORS preflight (OPTIONS) requests are exempt
- Returns HTTP 429 with `Retry-After` header when exceeded

## Data Privacy

- **No server-side storage of conversations.** All chat history is stored in the browser's localStorage.
- **No user accounts or authentication.** Hakim is anonymous by design.
- **Langfuse observability** logs LLM prompts/responses for quality monitoring but does not log user IP addresses or identifying information.
- **The vector store** contains only medical reference material, never user data.

## Limitations

- Hakim's lexicon covers Lebanese dialect primarily. Other Arabic dialects (Gulf, Egyptian, Moroccan) have limited coverage.
- The 246-term lexicon doesn't cover all medical conditions. Rare or specialized symptoms may not be recognized.
- LLM responses can occasionally be inconsistent despite guardrails. The post-processing layer catches most issues but is not infallible.
- Hakim cannot assess visual symptoms (rashes, swelling appearance) — text-only input.
- Network latency affects streaming response time, especially on Render's free tier (cold starts).
