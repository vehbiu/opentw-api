"""Date ranges, JavaScript argument splitting and venue addresses."""
from datetime import date

import pytest

from parsers.tournaments import (
    _parse_date_range,
    _parse_venue_address,
    _split_js_args,
    determine_event_type,
    parse_venue_info,
)


@pytest.mark.parametrize("text, expected", [
    ("03/19/2026 - 03/21/2026", (date(2026, 3, 19), date(2026, 3, 21))),
    # The hub omits the start's year; it is borrowed from the end.
    ("03/19 - 03/21/2026", (date(2026, 3, 19), date(2026, 3, 21))),
    # Borrowing the year across New Year would put the start after the end.
    ("12/30 - 01/02/2027", (date(2026, 12, 30), date(2027, 1, 2))),
    ("03/19/2026", (date(2026, 3, 19), None)),
    ("  03/19/2026  -  03/21/2026  ", (date(2026, 3, 19), date(2026, 3, 21))),
    ("TBD", (None, None)),
    ("", (None, None)),
    # One bad half does not throw away the other.
    ("03/19/2026 - soon", (date(2026, 3, 19), None)),
])
def test_parse_date_range(text, expected):
    assert _parse_date_range(text) == expected


@pytest.mark.parametrize("raw, expected", [
    ("123,'Plain Open',1,'logo.png'", ["123", "Plain Open", "1", "logo.png"]),
    ("123,'Some Open, 3rd-4th Grade',1,'logo.png'", ["123", "Some Open, 3rd-4th Grade", "1", "logo.png"]),
    ("5,'NCAA League Tournament (Boys)',1,'null'", ["5", "NCAA League Tournament (Boys)", "1", "null"]),
    (r"7,'St. Mary\'s Open',2,'null'", ["7", "St. Mary's Open", "2", "null"]),
    (r"8,'A\\B',2,'null'", ["8", "A\\B", "2", "null"]),
    ('9,"Double \'quoted\'",3,"x"', ["9", "Double 'quoted'", "3", "x"]),
    ("10, 'spaced' , 4 ,'x'", ["10", "spaced", "4", "x"]),
    ("", [""]),
])
def test_split_js_args(raw, expected):
    assert _split_js_args(raw) == expected


def test_parse_venue_address():
    text = "Rocket Arena\n1 Center Court\nCleveland, OH 44115\n"
    assert _parse_venue_address(text) == ("Rocket Arena", "1 Center Court", "Cleveland", "OH", "44115")


def test_parse_venue_address_partial():
    assert _parse_venue_address("Just A Gym") == ("Just A Gym", None, None, None, None)
    assert _parse_venue_address("") == (None, None, None, None, None)


def test_parse_venue_info():
    info = parse_venue_info("Rocket Arena\n1 Center Court\nCleveland, OH 44115")
    assert info == {"name": "Rocket Arena", "city": "Cleveland", "state": "OH", "zip": "44115"}


def test_parse_venue_info_without_location():
    assert parse_venue_info("Rocket Arena") == {"name": "Rocket Arena", "city": None, "state": None, "zip": None}


@pytest.mark.parametrize("markup, expected", [
    ('<span class="bg-purple-500">', 1),
    ('<span class="bg-green-500">', 2),
    ('<span class="bg-blue-500">', 3),
    ('<span class="bg-orange-500">', 4),
    ('<span class="bg-pink-500">', 5),
    ('<span class="plain">', 1),
])
def test_determine_event_type(markup, expected):
    assert determine_event_type(markup) == expected
