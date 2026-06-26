# QueueStorm Investigator

> **SUST CSE Carnival 2026 · Codex Community Hackathon · Online Preliminary Round**  
> Team: CUET_TriForce

A fintech support copilot that investigates customer complaints, cross-references transaction history, classifies cases, routes them to the correct department, and generates safe official replies — all through a clean HTTP API.

> **✅ Fully self-contained — no external API, no API keys, no secrets.** Classification, evidence reasoning, safety, and replies are 100% in-process using a deterministic rule engine and templated text generation. The result: sub-millisecond responses, no cost, no rate limits, no network dependency, and identical output every time.

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Tech Stack](#tech-stack)
3. [AI / Model Usage](#ai--model-usage)
4. [Safety Logic](#safety-logic)
5. [Quick Start (Local)](#quick-start-local)
6. [Docker](#docker)
7. [API Reference](#api-reference)
8. [Sample Request & Response](#sample-request--response)
9. [Known Limitations](#known-limitations)
10. [Architecture](#architecture)

---

## What It Does

Given a customer complaint and up to 5 recent transactions, QueueStorm Investigator:

| Step | What happens |
|------|-------------|
| 1 | Matches the complaint to the relevant transaction by amount, type, timing, and counterparty |
| 2 | Determines `evidence_verdict`: does the data **support**, **contradict**, or is it **insufficient** to judge the complaint? |
| 3 | Classifies the `case_type` and routes to the right `department` |
| 4 | Assigns `severity` (low → critical) |
| 5 | Flags for `human_review_required` if the case is a dispute, suspicious, or ambiguous |
| 6 | Generates a concise `agent_summary`, practical `recommended_next_action`, and a safe `customer_reply` |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11 |
| Framework | FastAPI + Uvicorn |
| Schema validation | Pydantic v2 |
| Reasoning engine | Deterministic Python rules (no ML, no external API) |
| Text generation | Rule-based templates (English + Bangla) |
| Containerisation | Docker (python:3.11-slim) |

---

## AI / Model Usage

### Approach: Deterministic Rule Engine

The entire pipeline is **rule-based** — no external API, no LLM, no ML model, no secrets. The problem statement explicitly allows and encourages this (*"rule-based logic — allowed and encouraged; an LLM is not required to score well"*), and it is the strongest fit for a fintech task where every decision must be reliable, auditable, and repeatable.

Every output field is produced by transparent logic over the complaint text and the provided transaction history:

| Component | Method | Why |
|-----------|--------|-----|
| Transaction matching | Scoring algorithm (amount, type, timing, counterparty) | Deterministic, instant, no cost |
| Evidence verdict | Contradiction detection over the history | Must be 100% reliable |
| Case classification | Keyword scoring + transaction-type signals | All enum values guaranteed correct |
| Department routing | Deterministic `case_type → department` map | No ambiguity allowed |
| Severity | Rules (case_type + amount + status) | Consistent and fast |
| Human review flag | Rules (severity + verdict + amount) | Critical escalation decision |
| Text generation | Safety-aware templates (English + Bangla) | Useful, professional, always safe |

**No GPU, no model weights, no runtime training, no network calls.** Responses are sub-millisecond and identical on every run, which maximises the automated Performance & Reliability score and eliminates timeout and rate-limit risk.

---

## Safety Logic

Safety is enforced at two layers:

### Layer 1 — Safety-First Templates
The text templates are authored to comply with every safety rule by construction: they never request credentials, never promise a refund/reversal, use approved language (*"any eligible amount will be returned through official channels"*), and always include the PIN/OTP reminder.

### Layer 2 — Post-Processing Guardrails (`safety_checker.py`)
Every generated text field still passes through a regex-based sanitiser **before** it is returned, as a defence-in-depth backstop. It also detects and neutralises prompt-injection attempts embedded in the complaint text.

| Rule | Enforcement |
|------|------------|
| Never ask for PIN, OTP, password, card number | Regex detection + removal + warning log |
| Never promise refund/reversal/unblock without authority | Regex replacement with approved language: *"any eligible amount will be returned through official channels"* |
| Never direct to suspicious third parties | Regex detection + removal |
| Prompt injection in complaint text | Detected and complaint sanitised before processing |
| Always include PIN/OTP safety reminder | Added if missing |

---

## Quick Start (Local)

### Prerequisites
- Python 3.11+
- pip

### Setup

```bash
# 1. Clone the repo and navigate to the service directory
cd queuestorm

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the service (no configuration or API key required)
python main.py
# OR
uvicorn main:app --host 0.0.0.0 --port 8000
```

> No environment variables are required. `PORT` (default `8000`) is the only optional setting.

### Verify

```bash
curl http://localhost:8000/health
# → {"status":"ok"}

curl -X POST http://localhost:8000/analyze-ticket \
  -H "Content-Type: application/json" \
  -d '{"ticket_id":"TKT-001","complaint":"I sent 5000 taka to a wrong number","transaction_history":[{"transaction_id":"TXN-9101","timestamp":"2026-04-14T14:08:22Z","type":"transfer","amount":5000,"counterparty":"+8801719876543","status":"completed"}]}'
```

### Run Tests

```bash
python tests/test_sample_cases.py   # 10 public sample cases
python tests/test_edge_cases.py     # 10 hardening cases (edge/adversarial)
```

---

## Docker

### Build

```bash
docker build -t queuestorm-team .
```

### Run

```bash
docker run -p 8000:8000 queuestorm-team
```

No API keys or secrets are required. The container binds to `0.0.0.0` and respects the `$PORT` environment variable (default `8000`), so it drops onto Render, Railway, Fly, EC2, or any host with no changes.

---

## API Reference

### GET /health

Returns `{"status": "ok"}` within 60 seconds of service start.

```
GET /health HTTP/1.1
Host: localhost:8000
```

Response:
```json
{"status": "ok"}
```

### POST /analyze-ticket

Accepts one support ticket and returns a full structured analysis.

**Request body:**
```json
{
  "ticket_id": "TKT-001",
  "complaint": "I sent 5000 taka to a wrong number around 2pm today...",
  "language": "en",
  "channel": "in_app_chat",
  "user_type": "customer",
  "campaign_context": "boishakh_bonanza_day_1",
  "transaction_history": [
    {
      "transaction_id": "TXN-9101",
      "timestamp": "2026-04-14T14:08:22Z",
      "type": "transfer",
      "amount": 5000,
      "counterparty": "+8801719876543",
      "status": "completed"
    }
  ]
}
```

**Response body:**
```json
{
  "ticket_id": "TKT-001",
  "relevant_transaction_id": "TXN-9101",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "Customer reports sending 5000 BDT via TXN-9101 to +8801719876543, which they believe was the wrong recipient.",
  "recommended_next_action": "Verify TXN-9101 details and initiate the wrong-transfer dispute workflow per policy.",
  "customer_reply": "We have noted your concern about transaction TXN-9101. Our dispute team will review the case and any eligible amount will be returned through official channels. Please do not share your PIN or OTP with anyone.",
  "human_review_required": true,
  "confidence": 0.9,
  "reason_codes": ["wrong_transfer", "transaction_match", "dispute_initiated"]
}
```

**HTTP Status Codes:**

| Code | Meaning |
|------|---------|
| 200 | Successful analysis |
| 400 | Malformed input (invalid JSON, missing required fields) |
| 422 | Semantically invalid (empty complaint, empty ticket_id) |
| 500 | Internal error (non-sensitive message only) |

---

## Sample Request & Response

See [`tests/SUST_Preli_Sample_Cases.json`](tests/SUST_Preli_Sample_Cases.json) for 10 fully worked examples, and [`sample_output_SAMPLE-01.json`](sample_output_SAMPLE-01.json) for a response generated by this service.

---

## Known Limitations

1. **Transaction matching is heuristic**: The algorithm scores transactions by amount, type, timing, and counterparty. In rare edge cases with very similar amounts and no phone number in the complaint, the match may be ambiguous — in which case it safely returns `relevant_transaction_id: null` and `evidence_verdict: "insufficient_data"`.

2. **Banglish (mixed Bengali-English)**: Bangla Unicode text is handled; romanised Bangla (Banglish) is treated as English. Detection relies on Unicode character ranges.

3. **Templated wording**: Customer/agent text is generated from per-case templates. They are safe, correct, and professional, but the phrasing is fixed per case type rather than freely re-worded for each complaint. This is a deliberate trade for determinism, speed, and guaranteed safety.

4. **No persistent state**: Each ticket is analysed independently. Historical patterns across tickets are not considered (only the provided `transaction_history` per request).

5. **Merchant settlement SLA**: The service flags settlement delays based on complaint keywords; it does not have access to real settlement batch data.

---

## Architecture

```
POST /analyze-ticket
        │
        ▼
┌─────────────────────────────────────┐
│  main.py (FastAPI)                  │
│  - Request validation               │
│  - Error handling (400/422/500)     │
│  - Route to response_builder        │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  response_builder.py (Orchestrator) │
│                                     │
│  1. detect_prompt_injection()       │
│  2. find_relevant_transaction()     │
│  3. classify_case()                 │
│  4. determine_evidence_verdict()    │
│  5. should_require_human_review()   │
│  6. generate_text_fields()  ──────► Rule-based templates (EN/BN)
│  7. check_safety()          ──────► Safety guardrails
│  8. compute_confidence()            │
│  9. return AnalyzeTicketResponse    │
└─────────────────────────────────────┘
```

---

## Models Section

**No machine-learning model or external AI API is used.** This service is built entirely from deterministic, in-process logic — there are no model weights, no inference calls, and no third-party API keys anywhere in the project.

| Component | Where it runs | Why chosen |
|-----------|--------------|------------|
| Rule-based classifier & router | In-process (Python) | Deterministic, free, instant, correct enums every time |
| Evidence-reasoning engine | In-process (Python) | Auditable contradiction checks — essential for fintech trust |
| Template text generator (EN/BN) | In-process (Python) | Zero cost, works offline, safe by construction |

No model weights are downloaded at runtime. No GPU. No network calls. No secrets.

---

*No real customer data was used. All test cases are synthetic.*  
*No real secrets are committed to this repository.*
