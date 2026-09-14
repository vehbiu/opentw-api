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

from models.ttypes import EventType
from parsers.tournaments import (
    generate_bracket_url,
    get_bracket_data_html,
    get_brackets,
    get_mat_assignment,
    get_tournament_info,
    search_tournaments,
    _parse_tournament_matches,
)
from utils.session_manager import session_manager

TOURNAMENT_ID = 931299132
TOURNAMENT_TYPE = EventType.PREDEFINED

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
    check("bracket url uses bracketWidth", "bracketWidth=" in url)
    check("bracket url uses groupId", f"groupId={lightest.weight_id}" in url)

    print("mat assignments")
    live = await get_mat_assignment(TOURNAMENT_TYPE, TOURNAMENT_ID)
    check("call succeeds", isinstance(live, list), f"{len(live)} live matches (0 expected - event is over)")

    # The live call can only return matches DURING an event, so the parser itself is checked
    # against the captured page instead. Without this the mat parser is untested out of season.
    with open("htmls/mat-schedule.html", encoding="utf-8", errors="replace") as fh:
        parsed = _parse_tournament_matches(fh.read())

    check("fixture parses", len(parsed) > 0, f"{len(parsed)} matches")
    if parsed:
        first = parsed[0]
        check("bout number parsed", first.bout > 0, str(first.bout))
        check("status parsed", first.status in ("in_progress", "on_deck", "in_hole"), first.status)
        check(
            "team is the team, not an initial",
            all(
                len(m.wrestler1.team.shortName) > 0 and not m.wrestler1.team.shortName.endswith(".")
                for m in parsed
            ),
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
