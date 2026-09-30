"""One weight's bracket sheet (AjaxFunctions.jsp?function=getBracket). Invented wrestlers.

The entry line differs per TOURNAMENT, in three formats seen on the 2026 championships:

    D1     (1) Luke <a>Lilledahl</a>, PSU, 25-0          name ends at the first comma
    D2/W   (1) Isaiah Gamez<br>Adams St., 27-3          name ends at the <br>
    D3     (1) Christian Guzman<br>North Central (IL) (5)  no record; "(5)" is a qualifying rank
"""
import pytest

from parsers.brackets import (
    parse_bout_numbers,
    parse_bracket_sheet,
    parse_entries,
    parse_pigtail_entrants,
    parse_routes,
)


def line(kind: str, wrestler: int, body: str, team: int = 9) -> str:
    return (f"<td><div class='{kind}-line' data-wrestler-id='{wrestler}' data-team-id='{team}'>"
            f"{body}</div></td><td nowrap valign='center'></td>")


def bout(n: int, page: int = 1) -> str:
    return f"""<a href="javascript:openBoutSheet({page},'N')">{n}</a>"""


def profile(surname: str) -> str:
    return f"<a class='plain' href='javascript:viewProfile(5)'>{surname}</a>"


def one(body: str):
    [entry] = parse_entries(line("full", 1, body))
    return entry.seed, entry.name, entry.school, entry.record, entry.qualifying_rank


@pytest.mark.parametrize("body, expected", [
    # D1: the surname is a profile link and everything is comma-separated.
    (f"(1) Alex {profile('Sample')}, NHS, 25-0", (1, "Alex Sample", "NHS", "25-0", None)),
    # D2 and women's: <br> between the name and the school.
    ("(16) Jordan Example<br>Adams St., 27-3", (16, "Jordan Example", "Adams St.", "27-3", None)),
    # A wrestler with no profile link must not fuse name and school.
    ("(2) Jordan Example<br/>Adams St., 27-3", (2, "Jordan Example", "Adams St.", "27-3", None)),
    # D3: no record, a trailing qualifying rank, and a state in brackets that must survive.
    ("(4) Casey Test<br>North Central (IL) (5)", (4, "Casey Test", "North Central (IL)", None, 5)),
    ("(4) Casey Test<br>North Central (IL)", (4, "Casey Test", "North Central (IL)", None, None)),
    # Unseeded: a non-breaking space where the seed goes.
    ("&nbsp;Riley Demo<br>West Tech, 10-5", (None, "Riley Demo", "West Tech", "10-5", None)),
    (" Riley Demo, WT, 10-5", (None, "Riley Demo", "WT", "10-5", None)),
    # Entities decoded.
    ("(3) Sam O&#39;Neil<br>St. Mary&#39;s, 5-5", (3, "Sam O'Neil", "St. Mary's", "5-5", None)),
])
def test_entry_formats(body, expected):
    assert one(body) == expected


def test_entries_keep_ids_and_bracket_order():
    entries = parse_entries(line("full", 11, "(1) A One, X, 1-0", team=91) + line("full", 12, "(16) B Two, Y, 0-1", team=92))
    assert [(e.wrestler_id, e.team_id, e.seed) for e in entries] == [("11", "91", 1), ("12", "92", 16)]


def test_bout_numbers_come_from_link_text_distinct_and_sorted():
    # openBoutSheet's first argument repeats across pages and is not a bout number.
    html = bout(26, page=1) + bout(11, page=1) + bout(11, page=3) + bout(631, page=1)
    assert parse_bout_numbers(html) == [11, 26, 631]


def test_pigtail_entrants():
    html = "".join([
        line("full", 1, f"(1) Alex {profile('Sample')}, NHS, 25-0"),
        line("half", 1, f"{profile('Sample')}, NHS"),            # seated: not a pigtail entrant
        line("half", 7, f"{profile('Doe')}, NHS"),               # D1: surname and team only
        line("half", 7, f"{profile('Doe')}, NHS"),               # mentioned twice, listed once
        line("half", 8, "&nbsp;Sam Full<br>East St., 3-2"),      # D2: a whole entry line
        line("half", 9, "&nbsp;Vanier, AUGS"),                   # D3: seed slot, still surname only
    ])
    entrants = parse_pigtail_entrants(html)
    assert [(p.wrestler_id, p.entry.name, p.partial) for p in entrants] == [
        ("7", "Doe", True), ("8", "Sam Full", False), ("9", "Vanier", True),
    ]
    assert entrants[1].entry.school == "East St."
    assert entrants[0].text == "Doe, NHS"


def test_routes_in_document_order():
    html = f"To bottom of {bout(11)} ... Loser of {bout(19)} ... To top of {bout(265)} ... To top of 7"
    assert [(r.kind, r.bout) for r in parse_routes(html)] == [
        ("to_bottom_of", 11), ("loser_of", 19), ("to_top_of", 265), ("to_top_of", 7),
    ]


def test_whole_sheet():
    sheet = parse_bracket_sheet(
        line("full", 1, "(1) A One, X, 1-0") + bout(11) + line("half", 7, profile("Doe") + ", X")
        + f"To bottom of {bout(11)}"
    )
    assert len(sheet.entries) == 1
    assert sheet.bout_numbers == [11]
    assert [p.wrestler_id for p in sheet.pigtail_entrants] == ["7"]
    assert [(r.kind, r.bout) for r in sheet.routes] == [("to_bottom_of", 11)]
    assert sheet.as_dict()["entries"][0]["name"] == "A One"


def test_empty_sheet():
    sheet = parse_bracket_sheet("<html>There has been an error</html>")
    assert (sheet.entries, sheet.bout_numbers, sheet.pigtail_entrants, sheet.routes) == ([], [], [], [])
