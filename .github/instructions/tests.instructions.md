---
applyTo: "tests/**,smoke_test.py"
---

Follow `docs/agents/testing.md`. In short:

- Offline tests only in `tests/`: no network, no saved TrackWrestling pages, invented wrestler
  names, and the smallest markup that reproduces the format.
- Test what a request *sends* as well as what is parsed (`tests/test_fetchers.py`).
- A bug-fix test must fail without the fix.
- Never weaken or delete a test to make it pass.
- `smoke_test.py` is live and gentle: a few requests per tournament, only finished 2026 NCAA
  championships, and checks of values rather than status codes.
