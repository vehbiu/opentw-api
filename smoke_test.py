"""End-to-end smoke test against the live TrackWrestling site.

Run it after any change here, and before believing the library still works:

    python smoke_test.py

It hits the real site, so it needs network and it is deliberately gentle — a few requests per
tournament. Every check prints PASS or FAIL and the script exits non-zero if anything failed,
so it is usable from CI or a cron. The offline suite is `python -m pytest`.

The tournaments are the 2026 NCAA championships, which are finished and therefore stable:
their brackets and results will not change under the test.
"""
import asyncio
import sys

from aiohttp import ClientSession

from models.ttypes import EventType
from parsers.results import get_results
from parsers.tournaments import (
    generate_bracket_url,
    get_bracket_data_html,
    get_bracket_sheet,
    get_brackets,
    get_mat_assignment,
    get_tournament_info,
    search_tournaments,
)
from utils.session_manager import TournamentUnavailable, session_manager

TOURNAMENT_ID = 931299132
TOURNAMENT_TYPE = EventType.PREDEFINED

# The other championships print their bracket entries in the other two line formats - D2 and
# women's as "Name<br>School, record", D3 as "Name<br>School (rank)" - and women's is freestyle,
# with a different set of result codes. Each: bout count across the whole tournament.
OTHER_DIVISIONS = {
    "D2": (954920132, 340),
    "D3": (954922132, 400),
    "women": (965471132, 340),
}

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {label}{f'  - {detail}' if detail else ''}")
    if not condition:
        failures.append(label)


async def main() -> int:
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
    # Fetch it, and fetch it again at double size: if Bracket.jsp ignored the dimension
    # parameters the two pages would be laid out identically.
    async with session_manager.get_session(TOURNAMENT_ID, TOURNAMENT_TYPE) as session:
        async with session.get(url) as response:
            page = await response.text()
        big = url.replace(f"bracketWidth={data.templates[0].bracket_width}", "bracketWidth=1400")
        async with session.get(big) as response:
            big_page = await response.text()
    check("bracket url renders results", any(k in page for k in ("Dec ", "Fall", "MD ", "TF-")))
    check("bracket url respects bracketWidth", page != big_page and "1400" in big_page)

    print("bracket sheet")
    sheet = await get_bracket_sheet(TOURNAMENT_TYPE, TOURNAMENT_ID, lightest.weight_id)
    check("32 entries, all seeded", len(sheet.entries) == 32 and all(e.seed for e in sheet.entries),
          f"{len(sheet.entries)} entries")
    check("top seed parsed", sheet.entries[0].seed == 1 and bool(sheet.entries[0].school),
          f"({sheet.entries[0].seed}) {sheet.entries[0].name}, {sheet.entries[0].school}")
    check("bout numbers parsed", len(sheet.bout_numbers) == 64, f"{len(sheet.bout_numbers)} bouts")
    check("pigtail routing parsed", any(r.kind == "to_bottom_of" for r in sheet.routes),
          f"{len(sheet.routes)} routes")

    print("results")
    results = await get_results(TOURNAMENT_TYPE, TOURNAMENT_ID, [w.weight_id for w in data.weights])
    check("whole tournament in one request", results.bout_count == 640, f"{results.bout_count} bouts")
    check("every line parsed", results.unparsed == 0, f"{results.unparsed} unparsed")

    for label, (other_id, bouts) in OTHER_DIVISIONS.items():
        print(label)
        other = await get_brackets(TOURNAMENT_TYPE, other_id)
        check("weights parsed", len(other.weights) == 10, f"{len(other.weights)} weights")
        other_sheet = await get_bracket_sheet(TOURNAMENT_TYPE, other_id, other.weights[0].weight_id)
        first = other_sheet.entries[0] if other_sheet.entries else None
        check("sheet entries split name from school",
              len(other_sheet.entries) == 16 and all(e.name and e.school and "<" not in e.name for e in other_sheet.entries),
              f"{len(other_sheet.entries)} entries, e.g. {first.name} / {first.school}" if first else "none")
        check("pigtail entrants found", len(other_sheet.pigtail_entrants) > 0,
              f"{len(other_sheet.pigtail_entrants)} entrants")
        other_results = await get_results(TOURNAMENT_TYPE, other_id, [w.weight_id for w in other.weights])
        check("every result line parsed", (other_results.bout_count, other_results.unparsed) == (bouts, 0),
              f"{other_results.bout_count} bouts, {other_results.unparsed} unparsed")

    print("empty pages")
    # Plant a session that never logged in: TrackWrestling answers it with an empty shell, and
    # the fetch should notice, re-open, and still return the real page.
    key = (TOURNAMENT_ID, TOURNAMENT_TYPE)
    old = session_manager.sessions.pop(key, None)
    if old:
        await old.close()
    session_manager.sessions[key] = ClientSession()
    recovered = await get_brackets(TOURNAMENT_TYPE, TOURNAMENT_ID)
    check("recovers from an expired session", len(recovered.weights) > 0, f"{len(recovered.weights)} weights")

    try:
        await get_brackets(EventType.OPEN, TOURNAMENT_ID)
        check("wrong event type is reported", False, "returned data")
    except TournamentUnavailable:
        check("wrong event type is reported", True)

    print("mat assignments")
    live = await get_mat_assignment(TOURNAMENT_TYPE, TOURNAMENT_ID)
    check("call succeeds", isinstance(live, list), f"{len(live)} live matches (0 expected - event is over)")

    # The parser itself is checked offline in tests/test_matches.py - the live call only
    # returns matches DURING an event.

    await session_manager.cleanup()

    print()
    if failures:
        print(f"{len(failures)} FAILED: " + "; ".join(failures))
        return 1

    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
