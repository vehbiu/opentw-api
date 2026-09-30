# OpenTW API

OpenTW API is a service that parses data from TrackWrestling's website and returns it in a simplified, structured format. This API makes it easier for developers to access and utilize wrestling tournament data.

## Overview

The OpenTW API serves as a middleware between applications and TrackWrestling's website, providing a cleaner interface to access tournament information, match details, brackets, and more. It handles the scraping and parsing of data, allowing developers to focus on building features rather than dealing with data extraction.

## Features

- Search for tournaments
- Get detailed tournament information
- Retrieve live match assignments and status
- Access bracket information, raw or parsed into entries, seeds and bout numbers
- Every result in a tournament in one request
- Monitor match status changes
- RESTful API with JSON responses

## API Endpoints

### Search Tournaments
```
GET /tournaments?query={search_term}
```
Returns a list of tournaments matching the search term.

### Tournament Information
```
GET /tournaments/{tournament_type}/{tournament_id}
```
Returns detailed information about a specific tournament.

### Match Assignments
```
GET /tournaments/{tournament_type}/{tournament_id}/matches
```
Returns current match assignments and statuses for a tournament.

### Brackets
```
GET /tournaments/{tournament_type}/{tournament_id}/brackets
```
Returns bracket information for all weight classes in a tournament.

### Specific Bracket
```
GET /tournaments/{tournament_type}/{tournament_id}/brackets/{weight_class_id}
```
Returns the bracket sheet's HTML for a specific weight class. `?pages=0,2` limits it to those
pages of the template; by default every page is returned.

### Parsed Bracket Sheet
```
GET /tournaments/{tournament_type}/{tournament_id}/brackets/{weight_class_id}/sheet
```
The same sheet, parsed:
- `entries`: first-round slots in bracket order, each with seed (null when unseeded), name,
  school, record, and for Division III the regional qualifying rank.
- `bout_numbers`: the published bout numbers.
- `pigtail_entrants`: wrestlers who hold no first-round slot. `partial` is true when the sheet
  prints only a surname and team.
- `routes`: routing hints (`loser_of`, `to_top_of`, `to_bottom_of`, each with a bout number)
  for pigtails and consolation feeds.

It handles the entry formats used by the 2026 NCAA D1, D2, D3 and women's championships.

### Results
```
GET /tournaments/{tournament_type}/{tournament_id}/results[?weights=id,id][&rounds=id,id]
```
Every completed bout, from one request to TrackWrestling. The default is all weights and all
rounds. Each result has round, weight, winner and loser with school and record, the method
("decision", "fall"…), and the result code exactly as the site writes it (`Dec`, `MD`, `Fall`,
`TF-1.5`, `SV-1`, `TB-2`, `2-OT`, `Inj.`, `DQ`, `M. For.`, `MFFL`, `For`) with its detail.
A line that cannot be read is returned with `parsed: false` and its text, and counted in
`unparsed`. It is never dropped.

### Errors
Errors come back as `{"ok": false, "data": null, "error": "..."}`:
- **400** for an unknown tournament type, a non-numeric id list, or a 13-digit `TIM` timestamp
  used as a tournament id.
- **404** when TrackWrestling returns an empty page, which usually means the tournament id or
  type is wrong.

## Installation

### Prerequisites
- Python 3.10+
- pip
- asyncio support

### Setup
1. Clone the repository:
   ```
   git clone https://github.com/vehbiu/opentw-api.git
   cd opentw-api
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Run the server:
   ```
   python main.py
   ```
   Host and port come from `HOST` and `PORT` (defaults `localhost:8000`).

4. Check it still works against the live site:
   ```
   python smoke_test.py
   ```

## Testing

```
pip install -r requirements-dev.txt
python -m pytest          # offline: every parser, the session handling and the routes
python smoke_test.py      # live: the 2026 NCAA championships, checked value by value
```

The offline suite uses hand-built markup with invented wrestlers, not captured pages, and runs
in about a second. CI runs it on every push. The smoke test needs network and is the one to run
when TrackWrestling may have changed something.

The server will start on `localhost:8000` by default.

## Development

The API is built using:
- Sanic - Async Python web server
- aiohttp - Async HTTP client for fetching data
- Custom parsers for extracting data from TrackWrestling HTML

### A warning about the parsers

This scrapes a site nobody here controls, and TrackWrestling changes it. The failures are
quiet ones: a page that returns 200 with a different shape, a row silently dropped, a field
that shifts one position. `smoke_test.py` exists because "it imports and the server starts"
says nothing at all about whether the parsing still works.

If something looks wrong, run the smoke test first - it checks the values, not just the
status codes.

### Project Structure
- `main.py` - Entry point; reads HOST/PORT and runs the server
- `server.py` - Sanic app and route definitions
- `smoke_test.py` - End-to-end checks against the live site
- `tests/` - Offline pytest suite
- `models/` - Data models and types
- `parsers/tournaments.py` - Search, tournament hub, mat assignments, bracket viewer
- `parsers/brackets.py` - A weight's bracket sheet: entries, bout numbers, routing
- `parsers/results.py` - RoundResults.jsp: every result in a tournament
- `utils/session_manager.py` - Viewer sessions, and recovery when TrackWrestling expires them
- `AGENTS.md`, `skills/`, `docs/agents/` - Instructions for AI coding agents, in the
  [Open Agent Format](https://openagentformat.com/). They are read by Claude Code (through
  `CLAUDE.md`), GitHub Copilot and OpenCode.

## Live Demo

A live version of the API is available at: https://opentw-api.vehbi.me

## Related Projects

- [OpenTW](https://github.com/vehbiu/opentw) - Frontend interface for this API

## License

[MIT License](LICENSE)

## Contact

For issues and contributions, please visit the [GitHub repository](https://github.com/vehbiu/opentw-api).