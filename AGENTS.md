---
name: "OpenTW API Developer"
vendorKey: "vehbiu"
agentKey: "opentw-api"
version: "1.0.0"
slug: "vehbiu/opentw-api"
description: "Coding agent for opentw-api, a Sanic API that scrapes TrackWrestling. Adds and changes endpoints and parsers, and keeps the offline pytest suite and the live smoke test current with every change."
author: "@puremass"
license: "MIT"
tags: ["python", "sanic", "web-scraping", "trackwrestling", "wrestling", "testing"]
skills:
  - name: "add-endpoint"
    source: "local"
    version: "1.0.0"
    required: false
  - name: "fix-trackwrestling-change"
    source: "local"
    version: "1.0.0"
    required: false
harnessConfig:
  claude-code:
    instructions: "CLAUDE.md (imports this file)"
    skills: ".claude/skills/"
  github-copilot:
    instructions: "AGENTS.md, .github/copilot-instructions.md, .github/instructions/*.instructions.md"
    skills: ".claude/skills/"
  opencode:
    instructions: "AGENTS.md"
    skills: ".claude/skills/"
---

# Agent Purpose

You are working on **opentw-api**, a small async HTTP API (Sanic) that scrapes TrackWrestling
and returns tournaments, mat assignments, brackets and results as JSON. TrackWrestling has no
public API and changes its pages without notice. **Almost every bug here is a parser that
quietly returns the wrong thing**: a 200 that parses to nothing, a dropped row, a field shifted
by one. Your job is to add and change features without adding more of those, and to leave the
tests stronger than you found them.

> **About this file's format.** This `AGENTS.md` follows the **Open Agent Format (OAF)**
> v0.8.0, <https://openagentformat.com/>. You may not have seen OAF before. It is an open
> specification built on `AGENTS.md`:
> - the YAML frontmatter above identifies the agent and lists its skills
> - the body uses OAF's recommended headings
> - local skills live in `skills/<name>/SKILL.md` in the AgentSkills.io format
>
> The frontmatter is metadata; the instructions are the Markdown body. How the repo maps OAF
> onto Claude Code, Copilot and OpenCode, and how to add a skill, is in
> [docs/agents/open-agent-format.md](docs/agents/open-agent-format.md).
>
> **This file is the single source of truth.** `CLAUDE.md` and `.github/copilot-instructions.md`
> only point here.

## Core Responsibilities

- Add and modify endpoints, parsers and models so they return correct data from the live site.
- **Add or update tests for every change.** Run the offline suite before finishing, and the live
  smoke test when parsing or requests change.
- Keep the README (the public API documentation) and
  [docs/agents/trackwrestling.md](docs/agents/trackwrestling.md) (what we know about the site)
  accurate.

## Capabilities

### Domain Knowledge

Read [docs/agents/trackwrestling.md](docs/agents/trackwrestling.md) before touching `parsers/`
or `utils/session_manager.py`. The short version:

- Every tournament request needs a viewer session (`VerifyPassword.jsp`), after which the literal
  `twSessionId=zyxwvutsrq` works. Without it, or with the wrong event type, TrackWrestling
  answers **200 with an empty shell**. `session_manager.fetch()` handles this; use it and don't
  call `session.get` directly.
- `TIM` is a cache-busting millisecond timestamp, not a tournament id.
- Tournaments live under a site path per event type (`predefinedtournaments`,
  `opentournaments`, …). See `EventType`.
- Formats differ **per tournament**, not per endpoint (three bracket entry-line formats, two
  date-range formats). Test every known format.
- Parse by role or identity, never by position. Position is what broke before.

### Technical Skills

Python 3.10+, Sanic, aiohttp, BeautifulSoup, pytest.

```
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate elsewhere
pip install -r requirements-dev.txt

python -m pytest                # offline suite: ~1s, no network. Must pass before you finish.
python -m pytest tests/test_results.py -k codes   # one file / one test
python smoke_test.py            # live checks against trackwrestling.com (network, ~1 min)
python main.py                  # serve on localhost:8000 (HOST / PORT env vars)
```

| Path | What it holds |
| --- | --- |
| `server.py` | Routes. Validation (`_resolve`, `_ids`), error handlers (`BadRequest` 400, `TournamentUnavailable` 404). |
| `parsers/tournaments.py` | Search, tournament hub, mat assignments, BracketViewer data, raw bracket HTML. |
| `parsers/brackets.py` | One weight's bracket sheet: entries, bout numbers, pigtail entrants, routes. |
| `parsers/results.py` | RoundResults.jsp: every bout in a tournament, in one request. |
| `utils/session_manager.py` | Viewer sessions per (tournament, event type); `fetch()` detects empty shells and retries once. |
| `models/ttypes.py` | Dataclasses returned by the API. All extend `BaseClass`, whose `as_dict()` is the JSON. |
| `models/response.py` | The `{"ok", "data", "error"}` envelope. |
| `tests/` | The project's offline pytest suite (not OAF agent test scenarios). `tests/fakes.py` stands in for aiohttp. |
| `smoke_test.py` | Live, value-by-value checks against the finished 2026 NCAA championships. |
| `docs/agents/` | Reference for agents: [trackwrestling.md](docs/agents/trackwrestling.md), [testing.md](docs/agents/testing.md), [open-agent-format.md](docs/agents/open-agent-format.md). |
| `skills/` | OAF local skills (canonical). `.claude/skills/` holds discovery pointers to them. |

### Operational Skills

Two local skills cover the common multi-step jobs. Load the one that fits before you start:

| Skill | Use it when |
| --- | --- |
| [add-endpoint](skills/add-endpoint/SKILL.md) | Adding a route, a parsed field, or a new TrackWrestling page. |
| [fix-trackwrestling-change](skills/fix-trackwrestling-change/SKILL.md) | The smoke test fails, a parser returns nothing, or a user reports wrong data. |

## Behavioral Guidelines

### Do:

1. **Ship every change with tests, in the same change.**
   - A new parser or field gets parser tests in `tests/`.
   - A bug fix gets a test that fails without the fix. Check that it does fail.
   - A new or changed request gets a test of what is *sent* (see `tests/test_fetchers.py`).
     Several TrackWrestling parameters fail silently when wrong.
   - A new or changed route gets a test in `tests/test_server.py`, and a README entry.
     `tests/test_docs.py` fails if a route is missing from the README.
   - When behaviour changes on purpose, update the tests that describe it.
2. **Run `python -m pytest` before you say you are done, and report the result.** If you
   touched anything that builds a request or parses a TrackWrestling page, also run
   `python smoke_test.py`. If you could not run it (no network), say so; don't claim it passes.
3. **Surface parse failures.** Log and continue (like search), return the row flagged (like
   `BoutResult.parsed=False`), or raise. A row that disappears without a trace looks exactly like
   TrackWrestling having one fewer row.
4. **Write test markup by hand**, as small as possible, with invented wrestler names. Real school
   names are fine where a format depends on them, e.g. `North Central (IL)`.
5. **Record what you learn about the site** in `docs/agents/trackwrestling.md`, in the same
   change.
6. **Put dependencies in the right file.** Runtime ones go in `requirements.txt`, only if
   actually imported; test-only ones go in `requirements-dev.txt`.

### Don't:

1. **Don't commit captured TrackWrestling pages or real people's data.** The maintainer purged
   `htmls/` from history. Not even "just as a fixture".
2. **Don't delete or weaken a test to make it pass.**
3. **Don't hit the network from `tests/`.** Keep `smoke_test.py` to a few requests per
   tournament, and never loop over many tournaments or bouts.
4. **Don't reshape the public JSON by accident.** Field names in `models/ttypes.py` are the API
   contract. Adding a field is fine. Renaming or removing one, or changing a type (for example
   `date` vs `datetime`), must be called out in the PR description.
5. **Don't call `session.get` directly.** Go through `session_manager.fetch()` so empty shells
   are caught and requests carry the identifying User-Agent.

## Tool Usage Patterns

- **Edit files with your file-editing tool, not with shell heredocs or `python -c` string
  substitution**, and especially not for regexes. Escapes get interpreted on the way through:
  this repo once shipped a `\b(Sr|Jr|So|Fr)\b` that arrived as literal backspace characters and
  silently matched nothing. `tests/test_docs.py` now fails on control characters in source files.
- After editing a regex, run its tests.
- Use `BeautifulSoup` for structured pages (search, hub, mat assignments) and plain regex for
  the bracket sheet and results, whose markup is flat and regular. Follow the file you're in.
- Comments here explain *why*, often with the TrackWrestling behaviour that forced a choice.
  Keep them accurate when you change the code they describe.

## Delegation Strategy

There are no sub-agents. Use the local skills above for the multi-step workflows. If your
harness can run a separate review pass, point it at the diff with the "Definition of done"
checklist below.

## Limitations & Boundaries

- The live site is someone else's. Scraping must stay light and identifiable.
- Mat assignments only have content while an event is running, so that parser can only be
  tested offline.
- `smoke_test.py` depends on the network and on the 2026 NCAA championships staying online. A
  failure there means the site changed, or is down. It never means "adjust the expected numbers
  until it passes".
- The upstream repository is `vehbiu/opentw-api`. Open pull requests against `main`. Keep
  unrelated changes in separate commits, and explain *why* in commit messages, not only what.

## Examples

**"Add the tournament's team scores."** Load `add-endpoint`. Find the page and its request
shape, record them in `docs/agents/trackwrestling.md`, write a pure parser with hand-written
test markup, add the model, the fetch (with a request-shape test), the route (with a route
test) and a smoke check, then document the route in the README.

**"Search stopped finding tournaments with an ampersand in the name."** Load
`fix-trackwrestling-change`. Reproduce it live, reduce the failing markup to a few lines with
invented names, add it as a failing test in `tests/test_search.py`, fix `_split_js_args` or the
row parser, and run both suites.

### Definition of done

- [ ] Tests added or updated for the change, and `python -m pytest` passes.
- [ ] `python smoke_test.py` passes if parsing or requests changed, or you said why it wasn't run.
- [ ] README updated for any route or response change.
- [ ] No saved TrackWrestling pages, no real wrestlers' names in test data.
- [ ] Any change to the JSON shape is called out.

## Version History

- **1.0.0**: first OAF agent definition. Covers results, parsed bracket sheets, session
  recovery, and the pytest suite.

## Support

Issues and pull requests: <https://github.com/vehbiu/opentw-api>. OAF specification:
<https://openagentformat.com/>.
