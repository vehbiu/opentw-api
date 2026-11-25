# OpenTW API

OpenTW API is a service that reads wrestling tournament data from TrackWrestling and FloWrestling and returns it in one simplified, structured format. This API makes it easier for developers to access and utilize wrestling tournament data.

## Overview

The OpenTW API serves as a middleware between applications and TrackWrestling's website, providing a cleaner interface to access tournament information, match details, brackets, and more. It handles the scraping and parsing of data, allowing developers to focus on building features rather than dealing with data extraction.

### TrackWrestling and FloWrestling

Since autumn 2026 TrackWrestling hands tournament pages over to FloWrestling: opening a
tournament redirects to `flowrestling.org/events/<id>`. The API decides per tournament,
automatically:

- **Search** still runs on TrackWrestling, and tournaments keep their TrackWrestling ids and
  types in every route.
- For each tournament the API checks once (then remembers for a few hours) whether
  TrackWrestling now sends it to FloWrestling. If it does, everything is read from
  FloWrestling's event data; if not, from TrackWrestling's pages as before.
- Responses have the same shape either way. Differences on FloWrestling tournaments:
  - ids of teams, wrestlers, weights, rounds and brackets are strings, not numbers;
  - tournament info has `source: "flowrestling"`, `flowrestling_event_id` and
    `flowrestling_url`;
  - `/brackets/{weight_class_id}` returns the bracket as data rather than HTML;
  - statistics use FloWrestling's stat names.
- A tournament TrackWrestling has handed over but FloWrestling has no page for returns 404.

## Features

- Search for tournaments
- Get detailed tournament information
- Retrieve live match assignments and status
- Access bracket information
- Team scores
- Teams, wrestlers and weight classes
- Placements, results and round-by-round bouts
- Statistics leaderboards
- Monitor match status changes
- RESTful API with JSON responses

## API Endpoints

### Search Tournaments
```
GET /tournaments?query={search_term}
```
Returns a list of tournaments matching the search term, with dates, venue (name, street,
city, state, zip), logo, flyer, website and pre-registration links where TrackWrestling has
them.

`tournament_type` in the routes below is one of `predefined`, `open`, `team`, `freestyle` or
`season`, as returned in each search result's `event_type`.

### Tournament Information
```
GET /tournaments/{tournament_type}/{tournament_id}
```
Returns detailed information about a specific tournament: name, dates, venue (name, street,
city, state, zip), logo, flyer, website and registration links, and `source`.

### Match Assignments
```
GET /tournaments/{tournament_type}/{tournament_id}/matches
```
Returns current match assignments and statuses for a tournament. Only populated while the
tournament is running. On TrackWrestling, team tournaments don't have mat assignments and
return 404. On FloWrestling this reads the live mat feed, which hasn't yet been checked
against a running tournament.

### Team Scores
```
GET /tournaments/{tournament_type}/{tournament_id}/team-scores
```
Returns team standings: `rank`, `team`, `score`, and `abbreviation` for open tournaments. On
FloWrestling also `team_id`, and `group` when a tournament scores several standings tables
(one per division on open tournaments).

### Teams
```
GET /tournaments/{tournament_type}/{tournament_id}/teams
```
Every team entered: `id`, `name`, `abbreviation`, `season_team`, `wrestler_count`, `points`.

### Wrestlers
```
GET /tournaments/{tournament_type}/{tournament_id}/wrestlers?team={team_id}&weight={weight_class_id}
```
Every wrestler entered, with `id`, `name`, `first_name`, `last_name`, `team`/`team_id`,
`weight_class`/`weight_class_id`, and, where the tournament records them, `division` (open and
freestyle classes), `weight`, `grade`, `record`, `scoring`, `qualifying_tournament` and
`qualifying_place`; on FloWrestling also `placement` (final place, if the wrestler placed).
Both filters are optional. Returns 404 when the organiser hasn't released the entry list.

### Weight Classes and Classes
```
GET /tournaments/{tournament_type}/{tournament_id}/weights
GET /tournaments/{tournament_type}/{tournament_id}/classes
```
Predefined and team tournaments have weight classes (`id`, `name`, `max_weight`,
`wrestler_count`, `bracket_type`, `seeds_saved`, `bracket_built`). Open and freestyle
tournaments group weights into classes (`id`, `name`, `wrestler_count`, `birth_date_range`,
`style`, fees, `match_length`; FloWrestling gives only `id`, `name` and `wrestler_count`); the
other endpoint returns 404.

### Results
```
GET /tournaments/{tournament_type}/{tournament_id}/results
```
Per weight class (or per bracket for team tournaments): `placements` (`place`, `name`,
`team`) and `matches`. Each match has `round`, `weight_class`, `winner` and `loser`
(`name`, `team`, `record`; on FloWrestling also `id`, `team_id`, `team_abbreviation`, `seed`),
`win_type` (`decision`, `major_decision`, `tech_fall`, `fall`, `forfeit`, `medical_forfeit`,
`injury_default`, `disqualification`, `sudden_victory`, `tie_breaker`, `overtime`, `bye`,
`no_contest`, `double_forfeit`, or `dual` for team tournaments), `result` as the site prints it
(`Dec 2-1`, `Fall 4:11`, `DEC SV 4-1`), `winner_score`, `loser_score`, `time`, the original
`text`, and on FloWrestling the bout `id` and `bout_number`. Bouts not yet wrestled are left
out. FloWrestling ranks round-robin team brackets with every team "1st"; those placements are
left empty rather than reported.

### Round Results
```
GET /tournaments/{tournament_type}/{tournament_id}/rounds
GET /tournaments/{tournament_type}/{tournament_id}/rounds/results?round={round_id}&weight={weight_class_id}
```
`/rounds` lists the round and weight class ids. `/rounds/results` returns every bout for a
round, a weight class, or both (at least one is required), in the same match format as
`/results`. Not available for team tournaments on TrackWrestling; on FloWrestling a team
tournament's weights give its individual bouts.

### Statistics
```
GET /tournaments/{tournament_type}/{tournament_id}/stats/{individual|team|weight|division}?stat={stat}&team={team_id}&weight={weight_class_id}
```
A leaderboard as `rows`, plus the `available_stats` to pass as `stat`. TrackWrestling's include
`mostPinsLeastTime`, `fastestFall` and `mostTeamPoints`; FloWrestling's are `pins` (pins and
tech falls, the default), `points` and `seeding`. `team` and `weight` filter the rows.

### Brackets
```
GET /tournaments/{tournament_type}/{tournament_id}/brackets
```
Returns bracket information for all weight classes in a tournament.

### Specific Bracket
```
GET /tournaments/{tournament_type}/{tournament_id}/brackets/{weight_class_id}
```
On TrackWrestling, returns the bracket for one weight class as TrackWrestling's HTML.
`?pages=2,3` selects bracket pages by the page ids listed in the tournament's templates.
Returns 404 when TrackWrestling isn't publishing the bracket yet.

On FloWrestling, `weight_class_id` is a weight's id from `/brackets`, and the bracket comes
back as data: `name`, `wrestler_count`, `placements`, and every `bouts` entry with
`bout_number`, `round`, `mat`, `state`, `result`, `win_type`, `time`, the `top` and `bottom`
wrestlers (`name`, `team`, `seed`, `score`, `winner`), `winner_to`/`loser_to` (the bout ids
the winner and loser go to next) and `x`/`y` (FloWrestling's bracket layout).

### Responses
Every response is `{"ok": bool, "data": ..., "error": "..."}`, with `error` only on failure:

| Status | Meaning |
| --- | --- |
| 400 | Bad tournament type, stats kind or `stat`; a non-numeric TrackWrestling id; `pages`; `/rounds/results` with neither `round` nor `weight` |
| 404 | Not available for this tournament (page doesn't exist for its type, not released yet, or no FloWrestling page) |
| 502 | The site returned something the parsers couldn't read, or couldn't be reached (timeout, connection error) |
| 503 | TrackWrestling is refusing requests (rate limited); back off and retry later |

Responses are cached briefly: search, tournament info, teams, wrestlers, weights, classes and
round lists 5 minutes; results 1 minute (2 on FloWrestling); team scores, brackets, round
results and stats 1 minute; bracket HTML 30 seconds; mat assignments 5 seconds. Where each
tournament lives is remembered for 6 hours (15 minutes while it's still on TrackWrestling).
Requests are spaced at least 0.5 seconds apart to TrackWrestling, whose CDN blocks clients that
send bursts, and 0.15 seconds apart to FloWrestling, so don't lower these without a reason.

The first `/results` for a large FloWrestling tournament reads every weight's bracket, about one
request per weight, so it can take 10 to 20 seconds before it's cached.

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
   Host and port come from `HOST` and `PORT` (defaults `localhost:8000`). `WORKERS` sets the
   number of worker processes (default 1). Each worker has its own cache and request
   throttle, so more workers means more traffic to TrackWrestling.

4. Check it still works against the live site:
   ```
   python smoke_test.py
   ```

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
- `smoke_test.py` - End-to-end checks against the live sites
- `models/` - Data models and types
- `parsers/` - TrackWrestling page parsers (`tournaments.py`, `details.py`) and the FloWrestling event reader (`flowrestling.py`)
- `utils/` - Request sessions, throttling and the FloWrestling lookup (`session_manager.py`), and the response cache (`cache.py`)

## Live Demo

A live version of the API is available at: https://opentw-api.vehbi.me

## Related Projects

- [OpenTW](https://github.com/vehbiu/opentw) - Frontend interface for this API

## License

[MIT License](LICENSE)

## Contact

For issues and contributions, please visit the [GitHub repository](https://github.com/vehbiu/opentw-api).