from sanic_ext import Extend
from typing import Dict, List
from sanic import Sanic, Request
from models.response import Response
from models.ttypes import EventType, Match
from parsers.tournaments import search_tournaments, get_tournament_info, get_mat_assignment, get_brackets, get_bracket_data_html, get_bracket_sheet
from parsers.results import get_results
from utils.session_manager import TournamentUnavailable


app = Sanic("trackwrestling-parser")
app.config.CORS_ORIGINS = "*"
Extend(app)


match_states: Dict[str, List[Match]] = {}

# Real tournament ids are nine or ten digits. Anything from 10^12 up is a millisecond timestamp -
# the TIM parameter, which is the only long number in a TrackWrestling URL and the one people
# paste when asked for an id. The tournament itself is identified by the session, not the URL.
_TIMESTAMP_FLOOR = 1_000_000_000_000


class BadRequest(Exception):
    pass


def _resolve(tournament_type: str, tournament_id: int) -> EventType:
    try:
        event_type = EventType.from_alias(tournament_type)
    except ValueError:
        aliases = ", ".join(t.alias for t in EventType)
        raise BadRequest(f"Invalid tournament type '{tournament_type}'. Expected one of: {aliases}")

    if tournament_id >= _TIMESTAMP_FLOOR:
        raise BadRequest(
            f"{tournament_id} is the TIM timestamp from a TrackWrestling URL, not a tournament "
            "id. Search for the tournament by name to get its id."
        )

    return event_type


def _ids(value: str | None) -> List[int] | None:
    if not value:
        return None
    try:
        return [int(i) for i in value.split(",")]
    except ValueError:
        raise BadRequest(f"Expected comma-separated ids, got '{value}'")


@app.exception(BadRequest)
async def bad_request(_: Request, exc: BadRequest) -> Response:
    return Response(ok=False, error=str(exc), status=400)


@app.exception(TournamentUnavailable)
async def tournament_unavailable(_: Request, exc: TournamentUnavailable) -> Response:
    return Response(ok=False, error=str(exc), status=404)


@app.get("/")
async def index(_: Request) -> Response:
    return Response(ok=True)

@app.get("/tournaments")
async def tournaments(request: Request) -> Response:
    parsed = await search_tournaments(request.args.get("query"))
    return Response(ok=True, data=[t.as_dict() for t in parsed])

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>")
async def tournament(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type = _resolve(tournament_type, tournament_id)
    parsed = await get_tournament_info(tourney_type, tournament_id)
    if parsed is None:
        return Response(ok=False, error="Tournament not found", status=404)
    return Response(ok=True, data=parsed.as_dict())

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/matches")
async def matches(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type = _resolve(tournament_type, tournament_id)
    parsed = await get_mat_assignment(tourney_type, tournament_id)
    return Response(ok=True, data=[m.as_dict() for m in parsed])

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/brackets")
async def brackets(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type = _resolve(tournament_type, tournament_id)
    parsed = await get_brackets(tourney_type, tournament_id)
    return Response(ok=True, data=parsed.as_dict())

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/brackets/<weight_class_id:int>")
async def bracket(request: Request, tournament_type: str, tournament_id: int, weight_class_id: int) -> Response:
    tourney_type = _resolve(tournament_type, tournament_id)
    pages = _ids(request.args.get("pages"))
    parsed = await get_bracket_data_html(tourney_type, tournament_id, weight_class_id, pages)
    return Response(ok=True, data=parsed)

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/brackets/<weight_class_id:int>/sheet")
async def bracket_sheet(request: Request, tournament_type: str, tournament_id: int, weight_class_id: int) -> Response:
    tourney_type = _resolve(tournament_type, tournament_id)
    parsed = await get_bracket_sheet(tourney_type, tournament_id, weight_class_id)
    return Response(ok=True, data=parsed.as_dict())

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/results")
async def results(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type = _resolve(tournament_type, tournament_id)
    weights = _ids(request.args.get("weights"))
    rounds = _ids(request.args.get("rounds"))
    if not weights:
        # "Everything" has to be spelled out as every weight id.
        weights = [w.weight_id for w in (await get_brackets(tourney_type, tournament_id)).weights]
    parsed = await get_results(tourney_type, tournament_id, weights, rounds)
    return Response(ok=True, data=parsed.as_dict())

if __name__ == "__main__":
    app.run(host="localhost", port=8000, debug=True, dev=True)
