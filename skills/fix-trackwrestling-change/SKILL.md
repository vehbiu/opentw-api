---
name: fix-trackwrestling-change
description: "Diagnose and fix opentw-api when TrackWrestling changes its pages: the smoke test fails, a parser returns empty or wrong data, rows go missing, or requests start returning empty pages. Reproduces live, reduces the page to a minimal offline test, then fixes."
license: MIT
metadata:
  author: "@puremass"
  version: "1.0.0"
---

# Skill Purpose

Turn "the data is wrong" into a failing offline test and a fix, without committing a scraped
page and without guessing at the cause.

## When to Use

- `python smoke_test.py` fails while `python -m pytest` passes. The site has changed.
- An endpoint returns empty lists, nulls, or values in the wrong fields.
- A route returns 404 "TrackWrestling returned an empty page".
- A user reports a tournament missing from search, or a wrestler with the wrong team.

## Usage

### 1. Reproduce live, and name the failure precisely

- Run `python smoke_test.py` and read which *values* are wrong, not just which checks failed.
- Call the specific `get_*` function from a scratch script for the affected tournament. Save the
  raw HTML **outside the repo** (never in `htmls/` or `tests/`).
- Decide which of these it is:
  - **Empty shell** (under 4KB, no visible text): the session, the event type, or a wrong id.
    See "Sessions and empty shells" in `docs/agents/trackwrestling.md`.
  - **Request changed**: the page now wants different parameters. Read the page's own
    JavaScript for how it builds the request.
  - **Markup changed**: the data is in the page, but the parser no longer finds it.

### 2. Reduce to a minimal offline test

- Cut the saved page down to the few lines that show the new shape. Replace every real person's
  name with an invented one.
- Add it as a new `pytest.mark.parametrize` case (or test) in the matching `tests/test_*.py`.
  **Keep the old format's case** unless the old format is provably gone: formats vary per
  tournament, and old tournaments stay online.
- Run it and see it fail for the reason you identified.

### 3. Fix

- Prefer identifying data by role or identity (a `data-*` attribute, "the block after the
  templates") over position or count.
- If a row still can't be parsed, surface it (log, flag or raise). Never drop it silently.
- Keep the change in public JSON to what the fix needs, and call out any shape change.

### 4. Record and verify

- Update `docs/agents/trackwrestling.md` with what changed and when, so the next agent starts
  from the truth.
- Run `python -m pytest`, then `python smoke_test.py`. Both must pass. If a smoke check's
  *expected value* was wrong, fix it and say so explicitly; don't loosen checks to get green.
