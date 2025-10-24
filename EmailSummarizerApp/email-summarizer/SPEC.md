# SPEC — Email Summarizer (MVP → Prod)

## Problem
Summarize Gmail threads via LLM and expose stable JSON through HTTP API. Secure, scalable, and observable.

## Use Cases
1) Summarize one thread (sync)  
2) Search & summarize many (async – later)  
3) Store / retrieve summaries (later)

## Non‑Negotiables
- OAuth2 (Gmail read‑only), JWT for clients (later), secrets in vault (later)
- Schema‑validated JSON output (v1)
- Structured logs + basic metrics
- No PII in logs, data retention policy

## API v1
- POST /v1/summarize/thread → { summary: <schema v1>, cost: {tokens:int} }
- GET /health

## Schema (email_summary.v1)
- See libs/schema/email_summary_v1.py (Pydantic model)

## Roadmap
Step 1: Schema + API stub + tests  
Step 2: Gmail client + Groq LLM adapter + validation  
Step 3: Persistence (Postgres), Auth, Observability  
Step 4: Async jobs (Celery/Redis), Bulk summarization
