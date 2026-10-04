# Change Data Management Service (CDMS)

Prototype CDMS for the kSynerX full-stack assignment: store only **new** product
changes from three ingestion mechanisms into PostgreSQL.

## Architecture

```text
Mock Inventory API (FastAPI + Faker)
        │
   Scheduled polling
        │
Excel Upload ──────► CDMS (FastAPI) ──► PostgreSQL
Webhook ───────────►
```

All three mechanisms call one write path with database-level deduplication
(exactly-once).

## Technology stack

- Python 3.12, FastAPI, SQLAlchemy 2 (async), asyncpg
- PostgreSQL 16, APScheduler, openpyxl, pytest, httpx
- Docker Compose (single machine)

## Quick start

```bash
docker-compose up --build
# or, if the Docker Compose v2 plugin is on PATH:
docker compose up --build
```

| Service        | URL                      |
|----------------|--------------------------|
| CDMS API       | http://localhost:8000/docs |
| CDMS health    | http://localhost:8000/healthz |
| CDMS readiness | http://localhost:8000/readyz |
| Inventory mock | http://localhost:8080/docs |
| Inventory list | http://localhost:8080/products |

PostgreSQL: `localhost:5432`, db/user/password = `cdms` / `cdms` / `cdms`.

## Repository layout

```text
cdms/           CDMS FastAPI service (+ cdms/tests)
inventory_mock/ Vietful-style inventory mock (Faker) (+ tests)
scripts/        Demo + verification scripts (webhook, burst, spike, xlsx gen)
sample/         Generated sample Excel (products.xlsx)
docs/           Architecture, code ownership
```

## Phase status

| Phase | Status |
|-------|--------|
| 1. Docker + Postgres + FastAPI skeletons | **Done** |
| 2. Product schema + `process_product()` + dedup | **Done** |
| 3. Webhook ingestion | **Done** |
| 4. Mock inventory + polling | **Done** |
| 5. Excel upload | **Done** |
| 6. Concurrency / exactly-once tests | **Done** |
| 7. Failure + spike testing | **Done** |
| 8. Full documentation / code ownership / lessons | **Done** |

## Phase 7 — failure + spike testing

Spike ramp (concurrent webhook load, latency percentiles, integrity check):

```powershell
python scripts\spike_test.py --ramp 50,100,250,500
# level=50..500, 900 requests total, 0 errors
# aggregate p50/p95/p99 reported; PASS requires:
#   - every distinct payload stored exactly once
#   - /healthz + /readyz healthy after the spike
#   - replay of 50 payloads = 0 new rows
```

Failure scenarios covered by `cdms/tests/test_failure.py` + live demos:

| Scenario | Expected | Verified |
|----------|----------|----------|
| DB stopped | `/readyz` → `not_ready`, `/healthz` stays `ok` | live |
| Poll during DB outage | `ok:false` + error, scheduler survives | live |
| DB restart | next poll recovers, `consecutive_errors` resets | live |
| Inventory 500/503 | poll records error, no crash | tests + live |
| Malformed JSON webhook | 400 | tests |
| DB down on webhook write | 5xx, never 200 | tests |
| Corrupt/empty/wrong-ext Excel | 422 / 400 / 415 | tests |
| Bad inventory payload shape | poll fails cleanly | tests |

## Phase 6 — concurrency / exactly-once

`cdms/tests/test_concurrency.py` (SQLite, shared file DB, `asyncio.gather`):

- 20 concurrent identical payloads → exactly 1 stored
- 30 concurrent distinct payloads → all stored
- webhook/polling/excel racing on one payload → 1 row (shared hash)
- 50+50 burst then a real change → 2 rows total

Live burst against Postgres (`scripts/burst_test.py`):

```powershell
python scripts\burst_test.py --n 100
# [1] 100 identical concurrent posts -> sum(stored)=1, rows=1
# [2] 100 distinct concurrent posts  -> sum(stored)=100
# [3] cross-mechanism replay         -> stored=0, rows=1
# PASS: exactly-once holds under concurrent webhook burst
```

## Phase 5 — Excel upload

`POST /api/v1/import/products` (multipart, `.xlsx`, max 5 MB):

```text
first row = headers (partnerSKU, sku, productName, stock, price, isActive, ...)
each row  → process_product(..., source="excel")
bad row   → reported in errors[] with row number (never blocks the file)
```

Generate the demo file (20 unique + 1 duplicate + 1 invalid row):

```powershell
python scripts\generate_sample_xlsx.py
curl.exe -X POST http://localhost:8000/api/v1/import/products -F "file=@sample\products.xlsx"
curl.exe "http://localhost:8000/api/v1/changes?source=excel&limit=5"
```

Demo result: first upload `stored=20, skipped=1, invalid=1`; replay
`stored=0, skipped=21` — dedup works across all three mechanisms because
they share the same write path.

Rejects: wrong extension (415), empty file (400), corrupt xlsx (422),
file > 5 MB (413).

## Phase 4 — polling

CDMS schedules `poll_once()` with APScheduler every `POLL_INTERVAL_SECONDS`
(default 30s):

```text
GET {EMULATOR_BASE_URL}/products  (paged)
  → process_product(..., source="polling")
  → ON CONFLICT DO NOTHING
```

Inventory mock also mutates products in the background (default every 10s,
3 products per tick) so polling sees real deltas.

Manual endpoints:

```http
POST /api/v1/polling/run
GET  /api/v1/polling/status
```

Inventory test helpers:

```http
POST /internal/mutate?partnerSKU=P001&count=3
POST /internal/fault?enabled=true&status_code=503
```

Demo:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/polling/run
Invoke-RestMethod -Method Post 'http://localhost:8080/internal/mutate?partnerSKU=P001&count=3'
Invoke-RestMethod http://localhost:8000/api/v1/polling/status
```

## Phase 3 — webhook

```http
POST /api/v1/webhooks/products
Content-Type: application/json
```

Body can be a single product, a list, or a Vietful-like envelope:

```json
{
  "event": "INV_CHANGED",
  "items": [{"partnerSKU": "P001", "stock": 20, "price": 500000}]
}
```

Optional HMAC (when `WEBHOOK_SECRET` is set):

```text
x-vf-hmacsha256: Base64(HMACSHA256(body, secret))
```

Demo scripts:

```powershell
python scripts\send_webhook.py --partnerSKU P001 --stock 20
python scripts\query_changes.py --partnerSKU P001
```

Query APIs:

```text
GET /api/v1/changes?partnerSKU=&source=&limit=
GET /api/v1/products/{external_id}
```

## Phase 2 — exactly-once core

All ingestion mechanisms (webhook / Excel / polling) call:

```python
await process_product(session, product, source=source)
```

Flow: validate → normalize → sha256 hash → `INSERT ... ON CONFLICT DO NOTHING`
on `product_changes(product_external_id, data_hash)` → upsert latest `products` row.

Run processor tests:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest cdms\tests -q
```

Key files:

- `cdms/app/services/change_processor.py` — single write path
- `cdms/app/services/hashing.py` — canonical JSON + deterministic hash
- `cdms/app/models/product.py`, `product_change.py`
- `cdms/tests/test_change_processor.py`

## API (Phase 1)

### CDMS

- `GET /healthz` — liveness
- `GET /readyz` — database connectivity

### Inventory mock

- `GET /products` — paginated product list (Vietful-like fields)
- `GET /products/{partnerSKU}` — product detail

## Assumptions

- Single-machine containerized prototype (no Redis/Kafka/Celery).
- Emulated Vietful Products API subset (not live stg credentials), per the
  assignment wording "emulating Vietful Inventory Service".
- Exactly-once is enforced by Postgres unique constraints (Phase 2).
- In-memory poller/scheduler state (single process).

## Known limitations

- No Alembic migrations (`create_all` on startup).
- Real Vietful stg API not called by design: the assignment says "emulating
  Vietful Inventory Service", and credentials come from Momena Portal
  (Developer Settings) which were not provided. The mock mirrors the real
  Products endpoints from the public OpenAPI spec.
- Horizontal scaling / multi-instance deployment out of scope.

## Verification (final)

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest cdms\tests inventory_mock\tests -q     # 51 passed
python scripts\burst_test.py --n 100                    # exactly-once live
python scripts\spike_test.py --ramp 50,100,250,500      # 900-req spike
```

## Code ownership

This prototype was built with AI pair-programming assistance under the
candidate's review: scope, architecture decisions, code review, and all
verification runs are the candidate's. See `docs/AI_USAGE.md` for the
per-area breakdown required by the assignment.

## Lessons learned

Design:

- One write path for every mechanism. Webhook, polling and Excel all call
  `process_product()`, so exactly-once had to be proven once instead of three
  times.
- DB constraints beat application checks. `UNIQUE(product_external_id,
  data_hash)` + `INSERT ... ON CONFLICT DO NOTHING` is race-proof; a Python
  `if exists` check would have failed the 100-identical-post burst
  (`sum(stored)=1`, rows=1).
- Hash only an explicit canonical field list. Same logical state hashes the
  same across mechanisms, transport noise (timestamps) is excluded.
- Dedup is exact-shape: the polled mock payload carries extra scalars the
  webhook model drops, so the same business state hashes differently per
  mechanism. The fix is to filter every source through the same field set
  before hashing.

Testing:

- SQLite for speed, Postgres for truth. Unit tests run on aiosqlite; the
  concurrency claims are re-proven live with `burst_test.py`.
- Fault-injection endpoints (`/internal/fault`, `/internal/mutate`) turn
  failure and spike demos into one-line commands.

Environment (cost real debugging time):

- New source files must be added to `COPY` in the Dockerfile, otherwise the
  rebuild "succeeds" and the image still misses them.
- FastAPI `UploadFile` needs `python-multipart`, and it fails at import time,
  which breaks the whole test collection rather than one route.
- PowerShell 5.1 mangles binary multipart bodies; use `curl.exe -F`.
