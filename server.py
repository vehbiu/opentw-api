import logging

from sanic_ext import Extend
from sanic import Sanic, Request
from sanic.exceptions import SanicException
from models.response import Response
from models.ttypes import EventType
from parsers.tournaments import search_tournaments, get_tournament_info, get_mat_assignment, get_brackets, get_bracket_data_html, get_team_scores
from parsers.details import (
    CLASS_TYPES, STATS_PAGES, get_classes, get_participants, get_results, get_round_options,
    get_round_results, get_stats, get_teams, get_weight_classes,
)
from parsers import flowrestling as flo
from utils.session_manager import session_manager, UpstreamError


app = Sanic("trackwrestling-parser")
app.config.CORS_ORIGINS = "*"
Extend(app)

_log = logging.getLogger(__name__)


class BadRequest(Exception):
    pass


def _int_arg(request: Request, name: str) -> int | None:
    value = request.args.get(name)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError:
        raise BadRequest(f"{name} must be a number")


def _event_type(alias: str) -> EventType:
    try:
        return EventType.from_alias(alias)
    except ValueError:
        valid = ", ".join(e.alias for e in EventType)
        raise BadRequest(f"Invalid tournament type '{alias}'. Expected one of: {valid}")


@app.exception(BadRequest)
async def bad_request(_: Request, exc: BadRequest) -> Response:
    return Response(ok=False, error=str(exc), status=400)


@app.exception(UpstreamError)
async def upstream_error(_: Request, exc: UpstreamError) -> Response:
    if exc.status == 400:  # FloWrestling rejected a parameter we passed through
        return Response(ok=False, error=str(exc), status=400)
    if exc.status == 404:
        # The page doesn't exist for this tournament type (team tournaments have no mat
        # assignments), or TrackWrestling isn't showing it (unreleased brackets).
        return Response(ok=False, error=str(exc), status=404)
    # 406 is TrackWrestling rate limiting us; tell the client to back off rather than retry.
    status = 503 if exc.status in (403, 406, 429) else 502
    return Response(ok=False, error=str(exc), status=status)


@app.exception(SanicException)
async def sanic_error(_: Request, exc: SanicException) -> Response:
    return Response(ok=False, error=str(exc), status=exc.status_code)


@app.exception(Exception)
async def unexpected_error(request: Request, exc: Exception) -> Response:
    # Almost always TrackWrestling or FloWrestling changing what they send under a parser.
    _log.exception("Unhandled error for %s", request.path)
    return Response(ok=False, error=f"Could not read the upstream response ({type(exc).__name__})", status=502)


@app.after_server_stop
async def close_sessions(*_) -> None:
    await session_manager.cleanup()


@app.get("/")
async def index(_: Request) -> Response:
    return Response(ok=True)

@app.get("/tournaments")
async def tournaments(request: Request) -> Response:
    parsed = await search_tournaments(request.args.get("query"))
    return Response(ok=True, data=[t.as_dict() for t in parsed])

# Every tournament route below picks its source per tournament: TrackWrestling hands most
# tournaments to FloWrestling now, and `flowrestling_event` says whether (and where) it has.
# The response shapes are the same either way; FloWrestling ids are strings.

async def _flo_event(tourney_type: EventType, tournament_id: int) -> str | None:
    return await session_manager.flowrestling_event(tourney_type, tournament_id)


def _id_arg(request: Request, name: str, on_flo: bool) -> int | str | None:
    """A query id: FloWrestling's are strings, TrackWrestling's numbers."""
    if on_flo:
        return request.args.get(name) or None
    return _int_arg(request, name)


@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>")
async def tournament(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type = _event_type(tournament_type)
    event = await _flo_event(tourney_type, tournament_id)
    parsed = (await flo.get_tournament_info(tourney_type, tournament_id, event) if event
              else await get_tournament_info(tourney_type, tournament_id))
    if parsed is None:
        return Response(ok=False, error="Tournament not found", status=404)
    return Response(ok=True, data=parsed.as_dict())

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/matches")
async def matches(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type = _event_type(tournament_type)
    event = await _flo_event(tourney_type, tournament_id)
    parsed = (await flo.get_mat_assignments(event) if event
              else await get_mat_assignment(tourney_type, tournament_id))
    return Response(ok=True, data=[m.as_dict() for m in parsed])

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/team-scores")
async def team_scores(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type = _event_type(tournament_type)
    event = await _flo_event(tourney_type, tournament_id)
    parsed = (await flo.get_team_scores(event) if event
              else await get_team_scores(tourney_type, tournament_id))
    return Response(ok=True, data=[s.as_dict() for s in parsed])

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/teams")
async def teams(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type = _event_type(tournament_type)
    event = await _flo_event(tourney_type, tournament_id)
    parsed = await flo.get_teams(event) if event else await get_teams(tourney_type, tournament_id)
    return Response(ok=True, data=[t.as_dict() for t in parsed])

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/wrestlers")
async def wrestlers(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type = _event_type(tournament_type)
    event = await _flo_event(tourney_type, tournament_id)
    team_id = _id_arg(request, "team", bool(event))
    weight_class_id = _id_arg(request, "weight", bool(event))
    parsed = await flo.get_participants(event) if event else await get_participants(tourney_type, tournament_id)
    parsed = [
        p for p in parsed
        if (team_id is None or p.team_id == team_id)
        and (weight_class_id is None or p.weight_class_id == weight_class_id)
    ]
    return Response(ok=True, data=[p.as_dict() for p in parsed])

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/weights")
async def weights(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type = _event_type(tournament_type)
    event = await _flo_event(tourney_type, tournament_id)
    if event and tourney_type in CLASS_TYPES:
        raise UpstreamError(f"{tourney_type.alias.title()} tournaments list classes, not weight classes; see /classes", 404)
    parsed = (await flo.get_weight_classes(event, tourney_type == EventType.TEAM) if event
              else await get_weight_classes(tourney_type, tournament_id))
    return Response(ok=True, data=[w.as_dict() for w in parsed])

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/classes")
async def classes(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type = _event_type(tournament_type)
    event = await _flo_event(tourney_type, tournament_id)
    if event and tourney_type not in CLASS_TYPES:
        raise UpstreamError("Only open and freestyle tournaments have classes; see /weights", 404)
    parsed = await flo.get_classes(event) if event else await get_classes(tourney_type, tournament_id)
    return Response(ok=True, data=[c.as_dict() for c in parsed])

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/results")
async def results(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type = _event_type(tournament_type)
    event = await _flo_event(tourney_type, tournament_id)
    parsed = await flo.get_results(event) if event else await get_results(tourney_type, tournament_id)
    return Response(ok=True, data=[r.as_dict() for r in parsed])

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/rounds")
async def rounds(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type = _event_type(tournament_type)
    event = await _flo_event(tourney_type, tournament_id)
    parsed = await flo.get_round_options(event) if event else await get_round_options(tourney_type, tournament_id)
    return Response(ok=True, data=parsed.as_dict())

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/rounds/results")
async def round_results(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type = _event_type(tournament_type)
    event = await _flo_event(tourney_type, tournament_id)
    round_id = _id_arg(request, "round", bool(event))
    weight_class_id = _id_arg(request, "weight", bool(event))
    if round_id is None and weight_class_id is None:
        raise BadRequest("Pass round and/or weight; ids are listed at /rounds")
    parsed = (await flo.get_round_results(event, round_id, weight_class_id) if event
              else await get_round_results(tourney_type, tournament_id, round_id, weight_class_id))
    return Response(ok=True, data=[m.as_dict() for m in parsed])

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/stats/<kind:str>")
async def stats(request: Request, tournament_type: str, tournament_id: int, kind: str) -> Response:
    tourney_type = _event_type(tournament_type)
    if kind not in STATS_PAGES:
        raise BadRequest(f"Unknown stats '{kind}'. Expected one of: {', '.join(STATS_PAGES)}")
    event = await _flo_event(tourney_type, tournament_id)
    stat = request.args.get("stat") or None
    team = _id_arg(request, "team", bool(event))
    weight = _id_arg(request, "weight", bool(event))
    parsed = (await flo.get_stats(event, kind, stat, team, weight) if event
              else await get_stats(tourney_type, tournament_id, kind, stat, team, weight))
    return Response(ok=True, data=parsed.as_dict())

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/brackets")
async def brackets(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type = _event_type(tournament_type)
    event = await _flo_event(tourney_type, tournament_id)
    parsed = await flo.get_brackets(event) if event else await get_brackets(tourney_type, tournament_id)
    return Response(ok=True, data=parsed.as_dict())

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/brackets/<weight_class_id:str>")
async def bracket(request: Request, tournament_type: str, tournament_id: int, weight_class_id: str) -> Response:
    """FloWrestling brackets come back as data (bouts, seeds, placements); TrackWrestling's as HTML."""
    tourney_type = _event_type(tournament_type)
    event = await _flo_event(tourney_type, tournament_id)
    if event:
        return Response(ok=True, data=(await flo.get_bracket_sheet(event, weight_class_id)).as_dict())

    if not weight_class_id.isdigit():
        raise BadRequest("weight_class_id must be a number for TrackWrestling tournaments")
    _pages: str | None = request.args.get("pages")
    try:
        pages = tuple(int(i) for i in _pages.split(",")) if _pages else None
    except ValueError:
        raise BadRequest("pages must be a comma-separated list of page ids, e.g. pages=2,3")
    parsed = await get_bracket_data_html(tourney_type, tournament_id, int(weight_class_id), pages)
    return Response(ok=True, data=parsed)

if __name__ == "__main__":
    app.run(host="localhost", port=8000, debug=True, dev=True)
