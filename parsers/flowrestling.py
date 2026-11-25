"""Tournaments TrackWrestling has handed to FloWrestling, read from FloWrestling's JSON API.

Since autumn 2026 TrackWrestling's viewer login redirects tournaments to
flowrestling.org/events/<id>. Those pages are a single-page app reading
prod-web-api.flowrestling.org/api/event-hub/<id>/..., which this module reads and maps onto
the same models the TrackWrestling parsers return, so clients see one API whichever site
holds a tournament.

FloWrestling ids are strings ("32DB3iFXozO08ZuIdr"), where TrackWrestling's are numbers.
"""
import asyncio
import json
import logging
import re
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from models.details import (
    BracketBout, BracketSheet, BracketSide, Competitor, MatchResult, Option, Participant,
    Placement, RoundOptions, StatsTable, TournamentClass, TournamentTeam, WeightClass,
    WeightResults,
)
from models.ttypes import (
    BracketData, Division, EventType, Match, Team, TeamScore, Tournament, Weight, Wrestler,
)
from utils.cache import ttl_cache
from utils.session_manager import UpstreamError, session_manager

_log = logging.getLogger(__name__)

PAGE_SIZE = 100
MAX_PAGES = 100

FLO_EVENT_URL = "https://www.flowrestling.org/nextgen/events/{}"


def _hub(event_id: str, *parts: str) -> str:
    return "/".join(["event-hub", event_id, *parts])


def _group_filter(kind: str, value: str) -> str:
    return json.dumps({"id": kind, "type": "string", "value": value}, separators=(",", ":"))


async def _paged(event_id: str, what: str) -> List[dict]:
    """POST event-hub/<id>/<what> page by page until `meta.total` rows are in."""
    rows: List[dict] = []
    for page in range(MAX_PAGES):
        body = {"filters": [], "search": None, "limit": PAGE_SIZE, "offset": page * PAGE_SIZE}
        reply = await session_manager.flo(_hub(event_id, what), body=body)
        data = reply.get("data") or {}
        batch = data.get("results", []) if isinstance(data, dict) else data
        rows += batch
        total = (reply.get("meta") or {}).get("total", 0)
        if not batch or len(rows) >= total:
            break
    return rows


# ---------------------------------------------------------------------------------------------
# Results vocabulary
# ---------------------------------------------------------------------------------------------

# FloWrestling result codes, first word of "DEC SV", "F 5:38", "TF 5:45", "MD".
_WIN_CODES = {
    "DEC": "decision",
    "MD": "major_decision",
    "TF": "tech_fall",
    "F": "fall",
    "FALL": "fall",
    "FF": "forfeit",
    "FOR": "forfeit",
    "MFF": "medical_forfeit",
    "MFOR": "medical_forfeit",
    "INJ": "injury_default",
    "IJ": "injury_default",
    "DEF": "injury_default",
    "DQ": "disqualification",
    "BYE": "bye",
    "NC": "no_contest",
    "DFF": "double_forfeit",
}


def _win_type(result: Optional[str]) -> Optional[str]:
    """"DEC SV" is a sudden-victory decision; overtime outcomes outrank the base code."""
    if not result:
        return None
    words = result.upper().replace(".", "").split()
    if any(w.startswith("SV") for w in words[1:]):
        return "sudden_victory"
    if any(w.startswith("TB") or w.startswith("UTB") for w in words[1:]):
        return "tie_breaker"
    if any(w.endswith("OT") for w in words[1:]):
        return "overtime"
    if words[0] == "M" and len(words) > 1 and words[1].startswith(("FOR", "FF")):  # "M FOR", "M FOR-L"
        return "medical_forfeit"
    if words[0] == "WIN":  # a dual meet between teams
        return "dual"
    return _WIN_CODES.get(words[0])


def _time(*texts: Optional[str]) -> Optional[str]:
    for text in texts:
        match = re.search(r"\b(\d+:\d\d)\b", text or "")
        if match:
            return match.group(1)
    return None


def _division_label(division: Optional[str], weight: str) -> str:
    return f"{division} - {weight}" if division else weight


# ---------------------------------------------------------------------------------------------
# Tournament
# ---------------------------------------------------------------------------------------------

def _local_date(stamp: Optional[str], zone: Optional[str]) -> Optional[date]:
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        return moment.astimezone(ZoneInfo(zone)).date() if zone else moment.date()
    except (ValueError, KeyError):
        return None


def _parse_event(data: dict, event_type: EventType, tournament_id: int, event_id: str) -> Tournament:
    location = data.get("location") or {}
    address = location.get("address") or {}
    zone = data.get("timeZone")
    start = _local_date(data.get("startDate"), zone)
    end = _local_date(data.get("endDate"), zone)
    registration = data.get("registration") or next(iter(data.get("registrations") or []), None) or {}
    flyer = next(iter(data.get("flyers") or []), None)
    flyer_url = flyer.get("url") if isinstance(flyer, dict) else flyer if isinstance(flyer, str) else None

    return Tournament(
        id=tournament_id,
        name=data.get("title", ""),
        event_type=event_type,
        start_date=start,
        end_date=end if end and end != start else None,
        venue_name=location.get("name"),
        venue_city=address.get("city"),
        venue_state=address.get("state"),
        venue_zip=address.get("zipCode"),
        logo_url=data.get("imageUrl") or data.get("fallbackImageUrl"),
        event_flyer_url=flyer_url,
        website_url=None,
        venue_street=address.get("line1"),
        registration_url=registration.get("url"),
        source="flowrestling",
        flowrestling_event_id=event_id,
        flowrestling_url=FLO_EVENT_URL.format(event_id),
    )


@ttl_cache(300)
async def get_tournament_info(event_type: EventType, tournament_id: int, event_id: str) -> Tournament:
    reply = await session_manager.flo(_hub(event_id))
    return _parse_event(reply.get("data") or {}, event_type, tournament_id, event_id)


# ---------------------------------------------------------------------------------------------
# Brackets, weights, divisions
# ---------------------------------------------------------------------------------------------

@ttl_cache(300)
async def _bracket_index(event_id: str) -> Tuple[List[Division], List[Weight]]:
    """Divisions and weight brackets, from the bracket picker's data.

    Brackets are grouped by division on open tournaments; otherwise by the tournament itself,
    whose id isn't a division.
    """
    reply = await session_manager.flo(_hub(event_id, "brackets", "divisions"),
                                      {"filter": "null", "search": "null", "tab": "null"})
    data = reply.get("data") or {}
    division_groups = (data.get("divisionContent") or {}).get("divisions") or {}
    options = (data.get("bracketOptionsContent") or {}).get("bracketOptions") or {}

    divisions = [
        Division(division_index=i, division_id=d["divisionId"], division_name=d.get("text", ""))
        for i, d in enumerate(d for group in division_groups.values() for d in group)
    ]
    division_ids = {d.division_id for d in divisions}

    weights = []
    for group_id, brackets in options.items():
        for bracket in brackets:
            weights.append(Weight(
                weight_index=len(weights),
                weight_id=bracket["bracketId"],
                weight_name=bracket.get("text", ""),
                bracket_id=bracket["bracketId"],
                division_id=group_id if group_id in division_ids else None,
            ))
    return divisions, weights


async def get_brackets(event_id: str) -> BracketData:
    divisions, weights = await _bracket_index(event_id)
    return BracketData(divisions=divisions, weights=weights, templates=[], bracket_types=[])


async def get_weight_classes(event_id: str, team_tournament: bool = False) -> List[WeightClass]:
    participants = await get_participants(event_id)
    if team_tournament:
        # The bracket is one team bracket; the weight classes are the dual meets' weights,
        # which the results lists know by id.
        counts = _count(participants, lambda p: p.weight_class)
        options = (await get_round_options(event_id)).weight_classes
        return [WeightClass(id=o.id, name=o.name, wrestler_count=counts.get(o.name, 0)) for o in options]

    _, weights = await _bracket_index(event_id)
    counts = _count(participants, lambda p: p.weight_class_id)
    return [WeightClass(id=w.weight_id, name=w.weight_name, wrestler_count=counts.get(w.weight_id, 0))
            for w in weights]


async def get_classes(event_id: str) -> List[TournamentClass]:
    divisions, _ = await _bracket_index(event_id)
    counts = _count(await get_participants(event_id), lambda p: p.division)
    return [TournamentClass(id=d.division_id, name=d.division_name, wrestler_count=counts.get(d.division_name, 0))
            for d in divisions]


def _count(items, key) -> Dict:
    counts: Dict = {}
    for item in items:
        counts[key(item)] = counts.get(key(item), 0) + 1
    return counts


def _side(raw: Optional[dict]) -> Optional[BracketSide]:
    if not raw or not (raw.get("name") or raw.get("displayName")):
        return None
    return BracketSide(
        id=raw.get("id"),
        name=raw.get("name") or raw.get("displayName"),
        team=raw.get("team"),
        team_abbreviation=raw.get("displayTeamName"),
        seed=raw.get("seed"),
        score=raw.get("score"),
        winner=bool(raw.get("winner")),
    )


def _bracket_bout(raw: dict) -> BracketBout:
    return BracketBout(
        id=raw.get("id"),
        bout_number=raw.get("matchNumber"),
        round=raw.get("roundName"),
        mat=raw.get("matName"),
        state=raw.get("state"),
        result=raw.get("result") or None,
        win_type=_win_type(raw.get("result") or raw.get("winType")),
        time=raw.get("resultTime") or _time(raw.get("result")),
        top=_side(raw.get("topParticipant")),
        bottom=_side(raw.get("bottomParticipant")),
        winner_to=raw.get("winnerTo"),
        loser_to=raw.get("loserTo"),
        x=raw.get("x"),
        y=raw.get("y"),
    )


def _bout_number(bout) -> Tuple[int, str]:
    number = bout.bout_number or ""
    return (int(number) if number.isdigit() else 10 ** 9, number)


@ttl_cache(60)
async def _bracket(event_id: str, bracket_id: str) -> Tuple[dict, List[BracketBout]]:
    reply = await session_manager.flo(_hub(event_id, "brackets", bracket_id),
                                      {"filter": "null", "search": "null", "tab": "null", "refresh": "false"})
    data = reply.get("data") or {}
    return data, sorted((_bracket_bout(m) for m in (data.get("matches") or {}).values()), key=_bout_number)


@ttl_cache(60)
async def get_bracket_sheet(event_id: str, bracket_id: str) -> BracketSheet:
    data, bouts = await _bracket(event_id, bracket_id)

    placed = await session_manager.flo(_hub(event_id, "brackets", "placements", bracket_id))
    placements = [
        # Team brackets place teams: no wrestler name, just the team.
        Placement(place=p["placeNumber"], name=p.get("name") or p.get("teamName") or "",
                  team=p.get("teamName"), id=p.get("participantId"))
        for p in placed.get("data") or [] if p.get("placeNumber")
    ]
    # Round-robin team brackets come back with every team "1st": that isn't a ranking.
    if len(placements) > 1 and len({p.place for p in placements}) == 1:
        placements = []
    return BracketSheet(
        id=bracket_id,
        name=data.get("name", ""),
        participant_type=data.get("participantType"),
        wrestler_count=data.get("count"),
        bouts=bouts,
        placements=placements,
    )


# ---------------------------------------------------------------------------------------------
# Teams, wrestlers, team scores
# ---------------------------------------------------------------------------------------------

@ttl_cache(300)
async def get_participants(event_id: str) -> List[Participant]:
    participants = []
    for r in await _paged(event_id, "participants"):
        first, last = r.get("firstName"), r.get("lastName")
        placement = r.get("currentPlacement")
        participants.append(Participant(
            id=r.get("id"),
            name=" ".join(n for n in (first, last) if n),
            first_name=first,
            last_name=last,
            team=r.get("teamName"),
            team_id=r.get("teamId"),
            weight_class=r.get("weightClass"),
            weight_class_id=next(iter(r.get("bracketIds") or []), None),
            division=r.get("division"),
            weight=str(r["actualWeight"]) if r.get("actualWeight") is not None else None,
            grade=r.get("grade"),
            placement=placement if placement and placement.isdigit() else None,
        ))
    return participants


@ttl_cache(60)
async def get_team_scores(event_id: str) -> List[TeamScore]:
    groups = (await session_manager.flo(_hub(event_id, "team-scores"))).get("results") or []
    scores = []
    for group in groups:
        reply = await session_manager.flo(_hub(event_id, "team-scores", "group"),
                                          {"groupFilter": _group_filter("teamScoreGroup", group["id"])})
        for item in reply.get("items") or []:
            scores.append(TeamScore(
                rank=item.get("place"),
                team=item.get("teamName", ""),
                score=item.get("score"),
                team_id=item.get("teamId"),
                group=group.get("title") if len(groups) > 1 else None,
            ))
    return scores


@ttl_cache(300)
async def get_teams(event_id: str) -> List[TournamentTeam]:
    scores = await get_team_scores(event_id)
    # One score per team when the tournament keeps a single standings table.
    points = {s.team_id: s.score for s in scores} if not any(s.group for s in scores) else {}
    return [
        TournamentTeam(
            id=t.get("id"),
            name=f"{t['name']}, {t['state']}" if t.get("state") else t.get("name", ""),
            abbreviation=t.get("abbreviation"),
            wrestler_count=t.get("participantCount"),
            points=points.get(t.get("id")),
        )
        for t in await _paged(event_id, "teams")
    ]


# ---------------------------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------------------------

def _competitor(side: Optional[BracketSide]) -> Optional[Competitor]:
    if side is None:
        return None
    return Competitor(name=side.name, team=side.team, id=side.id,
                      team_abbreviation=side.team_abbreviation, seed=side.seed)


def _match_from_bout(bout: BracketBout, weight_class: str, duals: bool = False) -> Optional[MatchResult]:
    """A bracket bout as a result; None for bouts not wrestled.

    In a team tournament's bracket each "bout" is a dual meet and the sides are teams.
    """
    sides = [s for s in (bout.top, bout.bottom) if s]
    winner = next((s for s in sides if s.winner), None)
    if winner is None:
        return None
    loser = next((s for s in sides if s is not winner), None)
    win_type = "bye" if loser is None else "dual" if duals else bout.win_type
    scored = loser is not None and win_type not in ("forfeit", "medical_forfeit", "injury_default",
                                                    "disqualification", "double_forfeit", "bye")
    result = bout.result or ("Bye" if loser is None else None)
    if duals and scored:
        result = f"{winner.score}-{loser.score}"
    elif (scored and win_type != "fall" and result and not re.search(r"\d+-\d+", result)
          and winner.score is not None):
        result = f"{result} {winner.score}-{loser.score}"  # "DEC" -> "DEC 4-1", as TrackWrestling printed it

    def who(side: BracketSide) -> str:
        return f"{side.name} ({side.team})" if side.team else side.name
    text = (f"{who(winner)} {'defeated' if duals else 'over'} {who(loser)} ({result})" if loser
            else f"{who(winner)} received a bye")
    return MatchResult(
        round=bout.round,
        weight_class=weight_class,
        winner=_competitor(winner),
        loser=_competitor(loser),
        win_type=win_type,
        result=result,
        winner_score=winner.score if scored else None,
        loser_score=loser.score if scored else None,
        time=bout.time,
        text=text,
        id=bout.id,
        bout_number=bout.bout_number,
    )


@ttl_cache(120)
async def get_results(event_id: str) -> List[WeightResults]:
    """Placements and every wrestled bout, weight by weight, from each weight's bracket.

    One request per weight: the bracket carries seeds, bout numbers and the full result
    ("DEC SV", "F 5:38"), which the per-round results lists flatten.
    """
    divisions, weights = await _bracket_index(event_id)
    division_names = {d.division_id: d.division_name for d in divisions}
    participants = await get_participants(event_id)
    # Started together; the request throttle still spaces them out.
    brackets = await asyncio.gather(*(_bracket(event_id, w.weight_id) for w in weights))

    results = []
    for weight, (data, bouts) in zip(weights, brackets):
        label = _division_label(division_names.get(weight.division_id), weight.weight_name)
        duals = data.get("participantType") == "team"
        matches = [m for m in (_match_from_bout(b, label, duals) for b in bouts) if m]
        placements = sorted(
            (Placement(place=int(p.placement), name=p.name, team=p.team, id=p.id)
             for p in participants if p.placement and p.weight_class_id == weight.weight_id),
            key=lambda p: p.place,
        )
        if not placements:  # team brackets place teams, which the participants don't carry
            placements = (await get_bracket_sheet(event_id, weight.weight_id)).placements
        results.append(WeightResults(weight_class=label, placements=placements, matches=matches))
    return results


@ttl_cache(300)
async def get_round_options(event_id: str) -> RoundOptions:
    async def listing(axis: str) -> List[Option]:
        reply = await session_manager.flo(_hub(event_id, "results", "rounds", axis), {"offset": 0, "limit": 1000})
        return [Option(id=o["id"], name=o.get("title", "")) for o in reply.get("data") or []]
    return RoundOptions(rounds=await listing("event-round"), weight_classes=await listing("event-weight-class"))


def _result_bout(raw: dict) -> Optional[MatchResult]:
    athletes = [a for a in (raw.get("athlete1"), raw.get("athlete2")) if a]
    winner = next((a for a in athletes if a.get("isWinner")), None)
    if winner is None:
        return None
    loser = next((a for a in athletes if a is not winner), None)

    def competitor(a: Optional[dict]) -> Optional[Competitor]:
        if not a:
            return None
        team = a.get("team") or {}
        return Competitor(name=a.get("name", ""), team=team.get("name"), id=a.get("id"),
                          team_id=team.get("id"), team_abbreviation=team.get("abbr"))

    code = raw.get("winType")
    win_type = "bye" if loser is None else _win_type(code)
    scored = loser is not None and win_type in ("decision", "major_decision", "tech_fall", "fall",
                                                "sudden_victory", "tie_breaker", "overtime")
    details = raw.get("details") or ""
    return MatchResult(
        round=raw.get("round"),
        weight_class=raw.get("weightClass"),
        winner=competitor(winner),
        loser=competitor(loser),
        win_type=win_type,
        result=" ".join(x for x in (code, details) if x) or None,
        winner_score=winner.get("score") if scored else None,
        loser_score=loser.get("score") if scored else None,
        time=_time(details),
        text=raw.get("name", ""),
        id=raw.get("boutId") or raw.get("id"),
        bout_number=raw.get("boutNumber"),
    )


@ttl_cache(60)
async def get_round_results(event_id: str, round_id: Optional[str] = None,
                            weight_class_id: Optional[str] = None) -> List[MatchResult]:
    axis, value = ("event-weight-class", weight_class_id) if weight_class_id else ("event-round", round_id)
    reply = await session_manager.flo(_hub(event_id, "results", "rounds", axis, "items"),
                                      {"groupFilter": _group_filter(axis, value)})
    matches = [
        m for group in reply.get("data") or [] for section in group.get("items") or []
        for m in (_result_bout(b) for b in section.get("items") or []) if m
    ]
    if weight_class_id and round_id:
        options = await get_round_options(event_id)
        title = next((o.name for o in options.rounds if o.id == round_id), None)
        matches = [m for m in matches if m.round == title]
    return matches


# ---------------------------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------------------------

STATS_DIMENSIONS = {"individual": "individual", "team": "team", "weight": "weightClass", "division": "division"}
# metric -> the field it is ranked by
STATS_METRICS = {"pins": "pins", "points": "matchPoints", "seeding": "seedPlaceDifference"}
_METRIC_NAMES = {"pins": "Pins and tech falls", "points": "Points", "seeding": "Seed vs place"}


@ttl_cache(60)
async def get_stats(event_id: str, kind: str, stat: Optional[str] = None,
                    team: Optional[str] = None, weight: Optional[str] = None) -> StatsTable:
    metric = stat or "pins"
    if metric not in STATS_METRICS:
        raise UpstreamError(f"Unknown stat '{metric}' for FloWrestling tournaments. "
                            f"Expected one of: {', '.join(STATS_METRICS)}", 400)
    body = {"context": "individual", "dimension": STATS_DIMENSIONS[kind], "metric": metric,
            "filters": [], "limit": 1000, "offset": 0, "sort": STATS_METRICS[metric], "sortOrder": "desc"}
    rows = (await session_manager.flo(_hub(event_id, "statistics"), body=body)).get("data") or []

    # FloWrestling filters by ids it doesn't expose, so filter here: by name or by id.
    if team:
        teams = {t.id: t.name.split(",")[0] for t in await get_teams(event_id)}
        name = teams.get(team, team)
        rows = [r for r in rows if r.get("team") == name or (kind == "team" and r.get("name") == name)]
    if weight:
        _, weights = await _bracket_index(event_id)
        name = next((w.weight_name for w in weights if w.weight_id == weight), weight)
        rows = [r for r in rows if r.get("weightClass") == name or (kind == "weight" and r.get("name") == name)]

    return StatsTable(
        stat=metric,
        available_stats=[Option(id=k, name=v) for k, v in _METRIC_NAMES.items()],
        rows=rows,
    )


# ---------------------------------------------------------------------------------------------
# Live mats
# ---------------------------------------------------------------------------------------------

def _wrestler(athlete: Optional[dict]) -> Optional[Wrestler]:
    if not athlete:
        return None
    team = athlete.get("team") or {}
    first, _, last = (athlete.get("name") or "").partition(" ")
    return Wrestler(id=athlete.get("id", ""), first_name=first, last_name=last,
                    team=Team(id=team.get("id", ""), name=team.get("name", ""), shortName=team.get("abbr", "")))


@ttl_cache(5)
async def get_mat_assignments(event_id: str) -> List[Match]:
    """Bouts on each mat while the tournament is running (FloWrestling "areas").

    Built from FloWrestling's bout schema, which its results use; the live feed couldn't be
    checked against a running tournament yet, so unknown shapes are logged and skipped.
    """
    reply = await session_manager.flo(_hub(event_id, "areas", "live"))
    matches = []
    for index, area in enumerate(reply.get("data") or [], start=1):
        name = str(area.get("name") or area.get("title") or index)
        number = re.search(r"\d+", name)
        bouts = next((area[k] for k in ("bouts", "items", "upcomingBouts", "matches") if isinstance(area.get(k), list)), None)
        if bouts is None:
            _log.warning("unrecognised FloWrestling area: %s", sorted(area)[:10])
            continue
        for position, bout in enumerate(bouts):
            if not isinstance(bout, dict) or "athlete1" not in bout:
                continue
            number_text = str(bout.get("boutNumber") or "")
            matches.append(Match(
                mat=int(number.group()) if number else index,
                bout=int(number_text) if number_text.isdigit() else 0,
                status="in_progress" if position == 0 else "on_deck" if position == 1 else "in_hole",
                weight_class=bout.get("weightClass") or "",
                round=bout.get("round") or "",
                wrestler1=_wrestler(bout.get("athlete1")),
                wrestler2=_wrestler(bout.get("athlete2")),
            ))
    return matches
