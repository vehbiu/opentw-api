"""End-to-end smoke test against the live TrackWrestling site.

Run it after any change here, and before believing the library still works:

    python smoke_test.py

It hits the real site, so it needs network and it is deliberately gentle — a handful of
requests, one tournament. Every check prints PASS or FAIL and the script exits non-zero if
anything failed, so it is usable from CI or a cron.

The fixed tournament is the 2026 NCAA Division I Championships, which is finished and
therefore stable: its brackets and results will not change under the test.
"""
import asyncio
import sys
from datetime import date

from models.ttypes import EventType
from parsers.tournaments import (
    generate_bracket_url,
    get_bracket_data_html,
    get_brackets,
    get_mat_assignment,
    get_tournament_info,
    search_tournaments,
    _parse_date_range,
    _parse_tournament_matches,
    _parse_weights,
    _split_js_args,
)
from utils.session_manager import session_manager

TOURNAMENT_ID = 931299132
TOURNAMENT_TYPE = EventType.PREDEFINED

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


async def main() -> int:
    offline_checks()

    print("search")
    found = await search_tournaments("NCAA")
    check("returns tournaments", len(found) > 0, f"{len(found)} results")
    named = next((t for t in found if t.id == TOURNAMENT_ID), None)
    check("finds the NCAA D1 championships", named is not None)
    if named:
        check("start date parsed", named.start_date is not None, str(named.start_date))
        check("end date parsed", named.end_date is not None, str(named.end_date))
    check(
        "names containing a comma or bracket survive",
        all(t.name for t in found),
        f"{len(found)} names, none empty",
    )

    print("tournament info")
    info = await get_tournament_info(TOURNAMENT_TYPE, TOURNAMENT_ID)
    check("returns a tournament", info is not None)
    if info:
        check("start date parsed", info.start_date is not None, str(info.start_date))
        check("venue parsed", bool(info.venue_name), str(info.venue_name))

    print("brackets")
    data = await get_brackets(TOURNAMENT_TYPE, TOURNAMENT_ID)
    check("weights parsed", len(data.weights) > 0, f"{len(data.weights)} weights")
    check("templates parsed", len(data.templates) > 0, f"{len(data.templates)} templates")
    check(
        "weights look like weight classes",
        all(w.weight_name.strip() for w in data.weights),
        ", ".join(w.weight_name for w in data.weights[:5]) + " ...",
    )

    print("bracket html")
    lightest = min(data.weights, key=lambda w: w.weight_index)
    html = await get_bracket_data_html(
        TOURNAMENT_TYPE, TOURNAMENT_ID, lightest.weight_id, pages=(2,)
    )
    check("bracket returned", len(html) > 2000, f"{len(html)} bytes")
    check("bracket holds results", any(k in html for k in ("Dec ", "Fall", "MD ", "TF-")))

    url = generate_bracket_url(
        TOURNAMENT_TYPE, lightest.weight_id, data.templates[0], pages=[2]
    )
    check("bracket url uses bracketWidth", "bracketWidth=" in url)
    check("bracket url uses groupId", f"groupId={lightest.weight_id}" in url)

    print("mat assignments")
    live = await get_mat_assignment(TOURNAMENT_TYPE, TOURNAMENT_ID)
    check("call succeeds", isinstance(live, list), f"{len(live)} live matches (0 expected - event is over)")

    # The live call can only return matches DURING an event, so the parser itself is checked
    # against a made-up row instead. Without this the mat parser is untested out of season.
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

    await session_manager.cleanup()

    print()
    if failures:
        print(f"{len(failures)} FAILED: " + "; ".join(failures))
        return 1

    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
