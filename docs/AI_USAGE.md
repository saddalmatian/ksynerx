# Code ownership & AI assistance

This note answers the assignment requirement (*FullStack_BaiTest.md*,
"Assignment Outcomes"): explain which code was written by the candidate and
which code was created using AI tools.

## How the build ran

Review-driven loop: the candidate scoped each phase and defined acceptance
criteria → an AI coding assistant produced a first draft → the candidate read
the diff, corrected what was wrong, ran it in the live environment, and only
then moved to the next phase. Nothing was merged into the final state without
being executed and verified locally.

## Breakdown

| Area | Candidate (owner) | AI assistant |
|------|-------------------|--------------|
| Assignment interpretation, 8-phase plan, scope cuts | decided scope, priorities, acceptance criteria | structured the plan, estimated dependencies |
| Tech stack (Python 3.12, FastAPI, SQLAlchemy 2 async, PostgreSQL 16, APScheduler, openpyxl, pytest, Docker Compose) | chose and approved each option | proposed options with trade-off analysis |
| Emulator vs real Vietful stg API | decided "emulator only" per the assignment wording | read the public OpenAPI spec for field/endpoint fidelity; a real-API adapter was built, then removed on request |
| Architecture: one shared write path, DB-level dedup | chose this design over application-level checks | drafted the implementation |
| Core logic (`hashing.py`, `change_processor.py`, dedup constraints) | reviewed line by line, corrected edge cases, proved with tests | drafted first version |
| API layer, inventory mock, mutation engine, fault injection | reviewed, drove the failure scenarios to cover | drafted |
| Tests (51: hashing, processor, webhook, polling, Excel, concurrency, failure) | specified what must be proven, ran them, interpreted failures | drafted the cases |
| Demo / burst / spike scripts | chose the load profiles and PASS criteria, executed them, quoted results in the README | drafted the harness code |
| Debugging (Docker COPY, `python-multipart`, multipart encoding, lifespan/NullPool) | reported symptoms from the live environment | diagnosed and patched |
| Documentation (README, architecture) | reviewed and corrected every claim against actual runs | drafted |

## What the candidate owns

- Every design decision and its trade-offs — `docs/architecture.md` and the
  README phase notes and lessons were checked against real command output
  before being written down.
- The final state of the repository: each change was read, corrected where it
  was wrong, and re-verified.
- All verification evidence: `pytest` (51 passed), the 100-request burst and
  the 900-request spike ramp were run in the candidate's environment.

## What the AI assistant did

Produced first-draft code, boilerplate, documentation drafts and debugging
hypotheses. Its output was treated as a draft, not as finished work.

## Boundaries

- No requirements were invented beyond `FullStack_BaiTest.md`.
- No live Vietful credentials were used (none were provided); the stg API was
  only read publicly, for spec fidelity.
- Every result quoted in the README was produced by a command the candidate
  ran locally.
