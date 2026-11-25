"""End-to-end smoke test against the live TrackWrestling and FloWrestling sites.

Run it after any change here, and before believing the library still works:

    python smoke_test.py

It hits the real sites, so it needs network, and it is deliberately gentle: a few finished
tournaments, every request throttled. Every check prints PASS or FAIL and the script exits
non-zero if anything failed, so it is usable from CI or a cron.

Search still runs on TrackWrestling. Tournament pages have moved to FloWrestling, so the
fixed tournaments (finished, so their results won't change under the test) are resolved
there the way the API does it. Checks of TrackWrestling's own tournament pages run only while
some tournament still lives there.
"""
import asyncio
import sys
from datetime import date

from models.ttypes import EventType
from parsers import flowrestling as flo
from parsers.tournaments import (
    get_brackets,
    search_tournaments,
    _parse_date_range,
    _parse_tournament_matches,
    _parse_weights,
    _split_js_args,
)
from parsers.details import parse_match_line
from utils.session_manager import UpstreamError, session_manager

# 2026 NCAA Division I Championships, a past open tournament, and a past team tournament.
TOURNAMENT_ID = 931299132
TOURNAMENT_TYPE = EventType.PREDEFINED
OPEN_ID = 974420132
TEAM_ID = 961054132

failures: list[str] = []

# One mat-assignment row in TrackWrestling's markup, with made-up wrestlers. The live page
# only exists while a tournament is running, so the parser is checked against this instead.
MAT_ASSIGNMENT_ROW = """
<table><tr>
  <td style="background-color: #00FF66; width: 4px;"></td>
  <td style="text-align: center;"><div>Mat 1</div><div><div>Bout</div><div>255</div></div></td>
  <td valign="top">
    <div><div style="display: table; width: 100%;">
      <div data-short-title="106" style="display: table-cell;"><span>106</span></div>
      <div style="display: table-cell; text-align: right;">Round 3</div>
    </div></div>
    <div>
      <font data-team-id="1" data-wrestler-id="11">
        <span data-short-title="J."><span>John</span></span>
        <span data-short-title="Doe"><span>Doe</span></span>, 0-2 (
        <span data-short-title="CH"><span>Central High</span></span>)
      </font>
      vs
      <font data-team-id="2" data-wrestler-id="22">
        <span data-short-title="S."><span>Sam</span></span>
        <span data-short-title="Smith"><span>Smith</span></span>, 1-1 (
        <span data-short-title="WV"><span>West Valley</span></span>)
      </font>
    </div>
  </td>
</tr></table>
"""


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {label}{f'  - {detail}' if detail else ''}")
    if not condition:
        failures.append(label)


def offline_checks() -> None:
    print("parsers (offline)")
    check(
        "open-tournament weights keep the 4-field shape",
        [(w.division_id, w.weight_id, w.weight_name) for w in
         _parse_weights("1~11~125~5~1~12~133~5~1~13~141~5", has_divisions=True)]
        == [(1, 11, "125"), (1, 12, "133"), (1, 13, "141")],
    )
    check(
        "predefined weights use the 3-field shape",
        [(w.division_id, w.weight_id, w.weight_name) for w in
         _parse_weights("11~125~5~12~133~5~13~141~5~14~149~5", has_divisions=False)]
        == [(None, 11, "125"), (None, 12, "133"), (None, 13, "141"), (None, 14, "149")],
    )
    check(
        "escaped quotes in names",
        _split_js_args(r"1,'St. Mary\'s Open',2,'l.png'") == ["1", "St. Mary's Open", "2", "l.png"],
    )
    start, end = _parse_date_range("12/30 - 01/02/2027")
    check("range across new year", (start, end) == (date(2026, 12, 30), date(2027, 1, 2)), f"{start} - {end}")

    # One of each result line shape TrackWrestling prints.
    lines = {
        "Luke Lilledahl (Penn State) 25-0, . over Marc-Anthony McGowan (Princeton) 19-7, . (Dec 2-1)":
            ("decision", "Luke Lilledahl", "Penn State", 2, 1, None),
        "Champ. Round 1 - Tyler Klinsky (Rider) 30-6 won by tech fall over Davis Motyka (Penn) 17-7 (TF-1.5 5:45 (19-3))":
            ("tech_fall", "Tyler Klinsky", "Rider", 19, 3, "5:45"),
        "Round 1 - Layne Vaughan (Tonganoxie Wrestling) won by fall over Natalia Cadena (NW Grapplers) Fall 0:25":
            ("fall", "Layne Vaughan", "Tonganoxie Wrestling", None, None, "0:25"),
        "Carter Nogle (Air Force) 31-10, . over Anthony Echemendia (Iowa State) 23-5, . (M. For.)":
            ("medical_forfeit", "Carter Nogle", "Air Force", None, None, None),
        "Champ. Round 1 - Maverick Villarreal (Ray-Pec Wrestling Club) received a bye () Bye":
            ("bye", "Maverick Villarreal", "Ray-Pec Wrestling Club", None, None, None),
        "Lyons defeated Southeast Of Saline 59-23.":
            ("dual", "Lyons", None, 59, 23, None),
    }
    for text, expected in lines.items():
        m = parse_match_line(text)
        got = (m.win_type, m.winner and m.winner.name, m.winner and m.winner.team,
               m.winner_score, m.loser_score, m.time)
        check(f"match line: {expected[0]}", got == expected, str(got))


async def main() -> int:
    offline_checks()

    print("search (TrackWrestling)")
    found = await search_tournaments("NCAA")
    check("returns tournaments", len(found) > 0, f"{len(found)} results")
    named = next((t for t in found if t.id == TOURNAMENT_ID), None)
    check("finds the NCAA D1 championships", named is not None)
    if named:
        check("start date parsed", named.start_date is not None, str(named.start_date))
        check("end date parsed", named.end_date is not None, str(named.end_date))
    check("names containing a comma or bracket survive", all(t.name for t in found), f"{len(found)} names")
    check(
        "search results carry the venue's city and state",
        all(t.venue_city and t.venue_state for t in found if t.venue_name and t.venue_name != "TBA"),
        f"{sum(1 for t in found if t.venue_city)} of {len(found)} with a city",
    )

    print("where tournaments live")
    event = await session_manager.flowrestling_event(TOURNAMENT_TYPE, TOURNAMENT_ID)
    open_event = await session_manager.flowrestling_event(EventType.OPEN, OPEN_ID)
    team_event = await session_manager.flowrestling_event(EventType.TEAM, TEAM_ID)
    check("NCAA resolves to its FloWrestling event", event == "15175319", str(event))
    check("open and team tournaments resolve too", bool(open_event and team_event), f"{open_event}, {team_event}")
    if not (event and open_event and team_event):
        return finish()

    print("tournament info (FloWrestling)")
    info = await flo.get_tournament_info(TOURNAMENT_TYPE, TOURNAMENT_ID, event)
    check("name and dates", info.name.startswith("2026 NCAA") and (info.start_date, info.end_date)
          == (date(2026, 3, 19), date(2026, 3, 21)), f"{info.start_date} - {info.end_date}")
    check("venue", (info.venue_name, info.venue_city, info.venue_state) == ("Rocket Arena", "Cleveland", "OH"))
    check("source is labelled", info.source == "flowrestling" and info.flowrestling_url is not None)

    print("teams, wrestlers, weights")
    teams = await flo.get_teams(event)
    scores = await flo.get_team_scores(event)
    check("all teams across pages", len(teams) == len(scores) == 70, f"{len(teams)} teams")
    check("team standings", scores[0].rank == 1 and scores[0].score == max(s.score for s in scores),
          f"{scores[0].team} {scores[0].score}")
    wrestlers = await flo.get_participants(event)
    weights = await flo.get_weight_classes(event)
    check("every wrestler, once", len(wrestlers) == sum(w.wrestler_count for w in weights)
          == len({w.id for w in wrestlers}) == 330, f"{len(wrestlers)} wrestlers")
    check("wrestlers carry ids", all(w.id and w.team_id and w.weight_class_id for w in wrestlers))
    check("8 placers per weight", sum(1 for w in wrestlers if w.placement) == 80)

    print("results and brackets")
    results = await flo.get_results(event)
    bouts = [m for r in results for m in r.matches]
    check("placements for every weight", len(results) == 10 and all(len(r.placements) == 8 for r in results))
    final = next(m for m in results[0].matches if m.round == "1st Place Match")
    check("final result matches the champion", final.winner.name == results[0].placements[0].name,
          f"{final.winner.name}, {final.result}")
    check("every bout has a win type and a winner", all(b.win_type and b.winner for b in bouts), f"{len(bouts)} bouts")
    sheet = await flo.get_bracket_sheet(event, weights[0].id)
    check("bracket sheet", len(sheet.bouts) > 30 and len(sheet.placements) == 8 and all(b.bout_number for b in sheet.bouts),
          f"{len(sheet.bouts)} bouts")
    options = await flo.get_round_options(event)
    check("round options", len(options.rounds) > 0 and len(options.weight_classes) == 10, f"{len(options.rounds)} rounds")
    weight_bouts = await flo.get_round_results(event, weight_class_id=options.weight_classes[0].id)
    check("every bout at a weight", weight_bouts and all(b.winner for b in weight_bouts), f"{len(weight_bouts)} bouts")
    stats = await flo.get_stats(event, "individual")
    check("individual stats", len(stats.rows) > 0 and len(stats.available_stats) > 0, f"{len(stats.rows)} rows")

    print("open and team tournaments")
    open_wrestlers = await flo.get_participants(open_event)
    check("open tournament wrestlers have classes", open_wrestlers and all(w.division for w in open_wrestlers),
          f"{len(open_wrestlers)} wrestlers")
    check("open tournament classes", len(await flo.get_classes(open_event)) > 0)
    open_bouts = [m for r in await flo.get_results(open_event) for m in r.matches]
    check("open tournament results", open_bouts and all(b.winner and b.win_type for b in open_bouts),
          f"{len(open_bouts)} bouts")
    duals = [m for r in await flo.get_results(team_event) for m in r.matches]
    check("team tournament duals", duals and all(d.win_type == "dual" and d.winner_score is not None for d in duals),
          f"{len(duals)} duals")
    team_weights = await flo.get_weight_classes(team_event, team_tournament=True)
    check("team tournament weight classes", len(team_weights) > 5, f"{len(team_weights)} weights")

    print("mat assignments")
    live = await flo.get_mat_assignments(event)
    check("call succeeds", isinstance(live, list), f"{len(live)} live matches (0 expected - event is over)")
    # The live feeds only fill DURING an event, so the TrackWrestling parser is checked against
    # a made-up row instead. Without this the mat parser is untested out of season.
    parsed = _parse_tournament_matches(MAT_ASSIGNMENT_ROW)
    check("fixture parses", len(parsed) > 0, f"{len(parsed)} matches")
    if parsed:
        first = parsed[0]
        check("bout number parsed", first.bout > 0, str(first.bout))
        check("status parsed", first.status in ("in_progress", "on_deck", "in_hole"), first.status)
        check(
            "team is the team, not an initial",
            (first.wrestler1.team.shortName, first.wrestler1.team.name) == ("CH", "Central High")
            and (first.wrestler2.team.shortName, first.wrestler2.team.name) == ("WV", "West Valley"),
            first.wrestler1.team.shortName,
        )

    print("TrackWrestling tournament pages")
    still_there = None
    for t in found[:10]:
        if not t.start_date or t.start_date < date.today():
            continue
        try:
            if not await session_manager.flowrestling_event(t.event_type, t.id):
                still_there = t
                break
        except UpstreamError:  # handed over, but FloWrestling has no page for it: moved all the same
            continue
    if still_there is None:
        print("  SKIP  every tournament checked has moved to FloWrestling")
    else:
        data = await get_brackets(still_there.event_type, still_there.id)
        check("bracket viewer parses", data is not None, f"{still_there.name}: {len(data.weights)} weights")

    return finish()


def finish() -> int:
    print()
    if failures:
        print(f"{len(failures)} FAILED: " + "; ".join(failures))
        return 1
    print("all checks passed")
    return 0


async def run() -> int:
    try:
        return await main()
    finally:
        await session_manager.cleanup()


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
