# Architecture

## Overview

Change Data Management Service (CDMS) stores only **new** inventory product
data from three mechanisms:

1. Scheduled polling of an emulated Vietful inventory service
2. Webhook callbacks
3. Excel uploads via REST

All paths converge on one processor that deduplicates before persisting to
PostgreSQL.

## Final design (Phases 1-7 complete)

```text
┌──────────────────────────┐        ┌───────────────────────────┐
│  Mock Inventory (8080)   │        │     Excel client          │
│  FastAPI + Faker         │        │  POST /api/v1/import/     │
│  mutation engine         │        │  products (.xlsx)         │
│  /internal/fault,mutate  │        └─────────────┬─────────────┘
└────────────┬─────────────┘                      │
             │ GET /products (paged)              │
   APScheduler interval                           │
   (POLL_INTERVAL_SECONDS)                        │
             │                                    │
             ▼                                    ▼
      ┌────────────────────────────────────────────────┐
      │                    CDMS (8000)                 │
      │  POST /api/v1/webhooks/products  (optional HMAC)│
      │  POST /api/v1/polling/run   GET .../polling/...│
      │  GET  /api/v1/changes   GET /api/v1/products/{id}│
      │  /healthz  /readyz                              │
      └────────────────────┬───────────────────────────┘
                           │
                process_product()   ← single write path
                 normalize → sha256 → ON CONFLICT DO NOTHING
                           │
      ┌────────────────────▼───────────────────────────┐
      │                  PostgreSQL 16                 │
      │  product_changes  UNIQUE(external_id, data_hash)│
      │  products         latest state per product      │
      └────────────────────────────────────────────────┘
```

Exactly-once uses:

```text
UNIQUE(product_external_id, data_hash)
```

so concurrent identical submissions persist one row — proven live with a
100-concurrent burst (Phase 6) and a 900-request spike ramp (Phase 7).

## Ingestion comparison

| | Polling | Webhook | Excel |
|---|---|---|---|
| Direction | pull | push | file upload |
| Source tag | `polling` | `webhook` | `excel` |
| Trigger | APScheduler (30s) / manual POST | external POST | multipart POST |
| Bad payload | next run retries | 4xx, nothing stored | row-level `errors[]` |
| Downstream | same `process_product()` | same | same |

## Failure matrix (verified)

| Failure | Behaviour | Where proven |
|---------|-----------|--------------|
| Inventory down / 5xx | poll logs `inventory_unavailable`, status counter++, scheduler survives | `test_failure.py`, Phase 4 live |
| PostgreSQL down | `/readyz` → `not_ready`, poll returns `ok:false`, `/healthz` still `ok`; next run recovers | Phase 7 live stop/start |
| Concurrent identical writes | exactly 1 row stored | `test_concurrency.py`, `burst_test.py` |
| Invalid webhook JSON / HMAC | 400 / 401, nothing stored | `test_webhook.py` |
| Excel bad rows | skipped with row number, rest of file processed | `test_excel_import.py` |
| Wrong/empty/corrupt Excel | 415 / 400 / 422 | `test_excel_import.py` |
| CDMS restart | constraints persist; replays store 0 | Phase 3/5 replay demos |

## Deployment

Single Docker Compose file:

- `postgres` — change store (5432, db/user/pass = cdms/cdms/cdms)
- `inventory` — mock Vietful inventory (8080)
- `cdms` — CDMS API (8000)

## Known limitations

- Single-process prototype: no Redis/Kafka/Celery, poller state in memory.
- No Alembic migrations (`create_all` on startup).
- Emulator only, per the assignment ("emulating Vietful Inventory Service");
  real stg credentials (Momena Portal > Developer Settings) were not provided.
- Real Vietful emits no product-CRD webhook (only `INV_CHANGED`), so webhook
  ingestion is demonstrated via partner-style pushes to CDMS.
