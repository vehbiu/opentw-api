---
name: add-endpoint
description: "Add a route, a parsed field, or support for a new TrackWrestling page to opentw-api, with its parser, model, fetch, route, offline tests, live smoke check and README entry. Use for any new feature that reads data from TrackWrestling."
license: MIT
metadata:
  author: "@puremass"
  version: "1.0.0"
---

# Skill Purpose

Take a feature from "TrackWrestling shows X" to a tested, documented endpoint, in the order
that catches silent failures earliest.

## When to Use

- A new route (`/tournaments/{type}/{id}/…`).
- A new field on an existing response.
- Reading a TrackWrestling page the project doesn't read yet.

For a *broken* existing feature, use `fix-trackwrestling-change` instead.

## Usage

### 1. Learn the page before writing code

- Read `docs/agents/trackwrestling.md`. The page may already be described there.
- Find how TrackWrestling's own page requests the data: look at its JavaScript for the URL, the
  method, and **every** parameter. Missing parameters usually give a 200 with an empty page or
  "There has been an error", not a useful error.
- Fetch it through `session_manager.fetch()` (a scratch script is fine) for one of the reference
  tournaments in `docs/agents/trackwrestling.md`. Save pages **outside the repo**.
- Write what you learned into `docs/agents/trackwrestling.md` now: request shape, markup,
  formats, quirks.

### 2. Parser: a pure function, test-first

- Add `parse_<thing>(html) -> Model` to the right module in `parsers/` (or a new
  `parsers/<area>.py`). No I/O.
- In `tests/test_<area>.py`, write hand-built markup: the smallest that has the real shape, with
  invented people. Add one `pytest.mark.parametrize` case per format you saw, plus the unhappy
  paths (an unreadable row must be logged, flagged or raised; assert which).
- Run `python -m pytest tests/test_<area>.py`, see it fail, then implement.

### 3. Model

- A `@dataclass` in `models/ttypes.py` extending `BaseClass`. `Optional[...] = None` for fields a
  page may not carry.
- `as_dict()` is the public JSON. Choose field names you are happy to keep.

### 4. Fetch

```python
async def get_<thing>(tournament_type: EventType, tournament_id: int, ...) -> Model:
    html = await session_manager.fetch(
        "GET",  # or "POST"
        f"https://www.trackwrestling.com/{tournament_type.tournament_type}/<Page>.jsp",
        tournament_id,
        tournament_type,
        params={"TIM": _get_timestamp(), "twSessionId": "zyxwvutsrq", ...},
    )
    return parse_<thing>(html)
```

In `tests/test_fetchers.py`, use the `site` fixture to assert the method, the path, and every
parameter that matters, above all the ones that fail silently.

### 5. Route

In `server.py`:

```python
@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/<thing>")
async def thing(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type = _resolve(tournament_type, tournament_id)
    parsed = await get_<thing>(tourney_type, tournament_id)
    return Response(ok=True, data=parsed.as_dict())
```

Parse id lists with `_ids(request.args.get(...))`. Raise `BadRequest` for bad input. In
`tests/test_server.py`, stub the fetch with `stub(monkeypatch, "get_<thing>", ...)` and assert
the arguments passed through and the response.

### 6. Live check, docs, finish

- Add a value check to `smoke_test.py` against a reference tournament: assert values, not only
  counts. Keep it to one or two requests.
- Document the route in `README.md` under "API Endpoints". `tests/test_docs.py` enforces this.
- Run `python -m pytest` and `python smoke_test.py`. Report both results.
- Work through the Definition of done in `AGENTS.md`.
