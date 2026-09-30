# Testing

Two layers, and every change touches at least the first.

| | Offline: `python -m pytest` | Live: `python smoke_test.py` |
| --- | --- | --- |
| Hits the network | never | yes, gently |
| Speed | about a second | about a minute |
| Proves | the code does what we think with the markup we think the site sends | the site still sends that markup |
| Run | on every change, and in CI | when parsing or requests change, or something looks wrong |

A passing offline suite with a failing smoke test means **TrackWrestling changed**. Fix the
understanding first (update `docs/agents/trackwrestling.md`), then the offline test, then the
code.

## Where tests go

| File | Covers |
| --- | --- |
| `tests/test_helpers.py` | date ranges, JS argument splitting, venue addresses |
| `tests/test_search.py` | search result rows |
| `tests/test_bracket_viewer.py` | BracketViewer blocks, weights shapes, `generate_bracket_url` |
| `tests/test_matches.py` | mat-assignment rows |
| `tests/test_bracket_sheet.py` | bracket sheet entries, bout numbers, pigtails, routes |
| `tests/test_results.py` | RoundResults lines and result codes |
| `tests/test_session_manager.py` | shell detection, session caching, retry |
| `tests/test_fetchers.py` | what each `get_*` sends, and that it parses what comes back |
| `tests/test_server.py` | routes, validation, error codes |
| `tests/test_docs.py` | README covers every route; no control characters in source; agent docs link to real files; `AGENTS.md` is a valid OAF manifest and its skills match their `.claude/skills/` pointers |

A new area gets a new `tests/test_<area>.py`.

## Writing parser tests

- **Hand-write the smallest markup that has the shape.** Each test file has small builders
  (`row()`, `line()`, `bout()`, `match_row()`). Reuse them; add parameters rather than copying
  markup.
- **Invented people only.** "Alex Sample", "Jordan Example". Real school names are fine where
  the format depends on them ("North Central (IL)").
- **One case per known format**, with `pytest.mark.parametrize`. If you find a new format on the
  live site, add it as a case *before* changing the parser, and watch it fail.
- Test the **unhappy paths** as well: a row that can't be parsed must be logged, flagged or
  raised, never silently dropped. Assert which one happens.
- Assert on **values**, not just counts or types.

## Testing requests without the network

- **Fetch functions:** the `site` fixture in `tests/test_fetchers.py` replaces
  `session_manager.fetch`, returns `site.page`, and records every call in `site.calls`. Assert
  the method, URL path and parameters, especially the ones that fail silently (for example
  `displayFormatBox`).
- **Session manager:** `tests/fakes.py` has `FakeSession` (answers with a function, records
  requests, tracks `closed`) and the two empty-shell pages. `manager_with([...])` in
  `tests/test_session_manager.py` hands out fake sessions in order.
- **Routes:** `stub(monkeypatch, "get_...", result=..., error=...)` in
  `tests/test_server.py` replaces a scraping function as `server.py` sees it. Use
  `server.app.test_client`.
- Async code is run with `asyncio.run(...)` inside ordinary tests; there is no pytest-asyncio.

## Bug fixes

1. Write the test that reproduces the bug.
2. Run it and **see it fail** for the reason you expect.
3. Fix the code and see it pass.
4. Run the whole suite.

## The live smoke test

- It checks the four finished 2026 NCAA championships (ids in `trackwrestling.md`), whose data
  no longer changes. Don't point it at events that are still running.
- Checks compare **values** ("640 bouts, 0 unparsed", "(1) Luke Lilledahl, PSU"), because a 200
  and a server that starts prove nothing about parsing.
- Keep it to a few requests per tournament. Don't loop over weights or bouts.
- Add a check when you add an endpoint or a parsed field.
- To investigate a live failure, save the page **locally** (for example in your scratch
  directory, never in the repo), reduce it to the smallest markup that shows the new shape, and
  write that as an offline test.
