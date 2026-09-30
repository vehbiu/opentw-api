---
applyTo: "parsers/**,utils/**,models/**,server.py"
---

Before changing this code, read `docs/agents/trackwrestling.md`. It records how TrackWrestling
actually behaves, and most of that behaviour fails silently when you get it wrong.

- Keep parsers pure (HTML in, model out) so they can be tested offline. I/O belongs in the
  `get_*` functions, which go through `session_manager.fetch()`.
- Identify data by role or identity (a `data-*` attribute, the first/last block), not by index.
- Formats vary per tournament. Handle every known format and add a test case for each.
- A row you cannot parse is logged, flagged, or raised, never silently dropped.
- Changing a model field name or type changes the public JSON. Call it out.
- Add or update tests in `tests/` for every change (see `docs/agents/testing.md`), then run
  `python -m pytest`, and `python smoke_test.py` if requests or parsing changed.
