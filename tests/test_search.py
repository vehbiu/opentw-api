"""Tournament search results (Login.jsp)."""
import logging
from datetime import date

from models.ttypes import EventType
from parsers.tournaments import _parse_tournaments


def row(args: str, dates: str = "03/19 - 03/21/2026", venue: str = "", links: str = "") -> str:
    return f"""<li>
      <div><a href="javascript:eventSelected({args});">logo</a></div>
      <div><span>Dates</span><span>{dates}</span></div>
      <div><span>{venue}</span></div>
      <div>{links}</div>
    </li>"""


def page(*rows: str) -> str:
    return f'<ul class="tournament-ul">{"".join(rows)}</ul>'


def test_full_row():
    [t] = _parse_tournaments(page(row(
        "931299132,'2026 NCAA Division I Championships',1,'https://x/logo.png'",
        venue="Rocket Arena\n1 Center Court\nCleveland, OH 44115",
        links='<a href="https://x/uploads/flyer.pdf">Flyer</a><a href="https://x/Website">Site</a>',
    )))
    assert t.id == 931299132
    assert t.name == "2026 NCAA Division I Championships"
    assert t.event_type == EventType.PREDEFINED
    assert (t.start_date, t.end_date) == (date(2026, 3, 19), date(2026, 3, 21))
    assert (t.venue_name, t.venue_city, t.venue_state, t.venue_zip) == ("Rocket Arena", "Cleveland", "OH", "44115")
    assert t.logo_url == "https://x/logo.png"
    assert t.event_flyer_url == "https://x/uploads/flyer.pdf"
    assert t.website_url == "https://x/Website"


def test_names_with_commas_brackets_and_quotes_survive():
    found = _parse_tournaments(page(
        row("1,'Some Open, 3rd-4th Grade',2,'null'"),
        row("2,'NCAA League Tournament (Boys)',1,'null'"),
        row(r"3,'St. Mary\'s Open',3,'null'"),
    ))
    assert [t.name for t in found] == ["Some Open, 3rd-4th Grade", "NCAA League Tournament (Boys)", "St. Mary's Open"]
    assert [t.event_type for t in found] == [EventType.OPEN, EventType.PREDEFINED, EventType.TEAM]


def test_backtick_is_an_apostrophe():
    # TrackWrestling escapes apostrophes inside these arguments as backticks.
    [t] = _parse_tournaments(page(row("965471132,'2026 NCAA Women`s National Championships',1,'x', 0")))
    assert t.name == "2026 NCAA Women's National Championships"


def test_null_logo():
    [t] = _parse_tournaments(page(row("1,'Open',2,'null'")))
    assert t.logo_url is None


def test_bad_row_is_logged_and_skipped_not_fatal(caplog):
    with caplog.at_level(logging.WARNING):
        found = _parse_tournaments(page(
            row("1,'Good',1,'x'"),
            row("not-a-number,'Bad',1,'x'"),
            row("2,'Too few'"),
            row("3,'Also good',2,'x'"),
        ))
    assert [t.id for t in found] == [1, 3]
    assert len([r for r in caplog.records if "skipped a tournament row" in r.message]) == 2


def test_empty_page():
    assert _parse_tournaments("<html></html>") == []
