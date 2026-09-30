"""The fetch-and-parse functions, with TrackWrestling replaced by canned pages.

These check what is ASKED FOR as well as what is parsed: the parameter sets are not guessable,
and several fail silently when wrong (RoundResults.jsp without displayFormatBox is an empty page).
"""
import asyncio
from datetime import date

import pytest

import parsers.results as results_module
import parsers.tournaments as tournaments_module
from models.ttypes import EventType


@pytest.fixture
def site(monkeypatch):
    """Replaces session_manager.fetch; set `site.page` to what TrackWrestling should answer."""

    class Site:
        page = ""
        calls = []

    async def fetch(method, url, tournament_id, event_type, **kwargs):
        Site.calls.append({"method": method, "url": url, "id": tournament_id, "type": event_type, **kwargs})
        return Site.page

    Site.calls = []
    monkeypatch.setattr(tournaments_module.session_manager, "fetch", fetch)
    return Site


HUB = """<html><body>
<span class="bg-green-500">Open</span>
<div class="hub-nav"><ul><li><div class="content">
  <div class="logo-icon"><img src="https://x/logo.png"></div>
  <h3>Winter Open</h3>
  <p>12/30 - 01/02/2027</p>
  <p>Big Gym
     1 Main St
     Springfield, IL 62701</p>
</div></li></ul></div>
<a href="https://x/event_flyer.pdf">Flyer</a>
<a href="https://x/website">Website</a>
</body></html>"""


def test_tournament_info(site):
    site.page = HUB
    t = asyncio.run(tournaments_module.get_tournament_info(EventType.OPEN, 42))

    assert (t.id, t.name, t.event_type) == (42, "Winter Open", EventType.OPEN)
    assert (t.start_date, t.end_date) == (date(2026, 12, 30), date(2027, 1, 2))
    assert (t.venue_name, t.venue_city, t.venue_state, t.venue_zip) == ("Big Gym", "Springfield", "IL", "62701")
    assert (t.logo_url, t.event_flyer_url, t.website_url) == ("https://x/logo.png", "https://x/event_flyer.pdf", "https://x/website")
    assert t.as_dict()["start_date"] == "2026-12-30"

    [call] = site.calls
    assert call["url"].endswith("/opentournaments/TournamentHub.jsp")
    assert call["params"]["tournamentId"] == "42"


def test_tournament_info_missing_content(site):
    site.page = "<html><body>nothing</body></html>"
    assert asyncio.run(tournaments_module.get_tournament_info(EventType.PREDEFINED, 1)) is None


def test_mat_assignment_uses_the_tournament_type(site):
    site.page = "<table></table>"
    assert asyncio.run(tournaments_module.get_mat_assignment(EventType.TEAM, 7)) == []
    assert site.calls[0]["url"].endswith("/teamtournaments/MB_MatAssignmentDisplay.jsp")
    assert site.calls[0]["type"] == EventType.TEAM


def test_brackets(site):
    site.page = 'x<script>new Pile(); str = "4~0~T~700~590~8~0,Prelims"; str = "11~125~4"; str = "4";</script>'
    data = asyncio.run(tournaments_module.get_brackets(EventType.PREDEFINED, 5))
    assert [w.weight_name for w in data.weights] == ["125"]
    assert site.calls[0]["url"].endswith("/predefinedtournaments/BracketViewer.jsp")


def test_bracket_html_sends_the_full_parameter_set(site):
    site.page = "<html>bracket</html>"
    html = asyncio.run(tournaments_module.get_bracket_data_html(EventType.PREDEFINED, 5, 123, (0, 2)))
    assert html == "<html>bracket</html>"
    params = site.calls[0]["params"]
    # An incomplete set answers "There has been an error" rather than naming what is missing.
    assert {"function", "groupId", "chartId", "width", "height", "font", "includePages", "templateId"} <= params.keys()
    assert (params["function"], params["groupId"], params["includePages"]) == ("getBracket", 123, "0,2")


def test_bracket_sheet(site):
    site.page = "<div class='full-line' data-wrestler-id='1' data-team-id='2'>(1) A One, X, 1-0</div>"
    sheet = asyncio.run(tournaments_module.get_bracket_sheet(EventType.PREDEFINED, 5, 123))
    assert [e.name for e in sheet.entries] == ["A One"]


def test_results_request_shape(site):
    site.page = ("<section class='tw-list'><h1>R1</h1><h2>125</h2><ul><li>R1 - A (X) 1-0 won by decision "
                 "over B (Y) 0-1 (Dec 1-0)</li></ul></section>")
    results = asyncio.run(results_module.get_results(EventType.PREDEFINED, 5, [11, 12], [3]))
    assert results.bout_count == 1

    [call] = site.calls
    assert call["method"] == "POST"
    assert call["url"].endswith("/predefinedtournaments/RoundResults.jsp")
    # Ids in the query string, box fields in the body - how the page's own viewSchedule() asks.
    assert (call["params"]["groupId"], call["params"]["roundId"]) == ("11,12", "3")
    assert (call["data"]["groupIdBox"], call["data"]["roundIdBox"]) == ("11,12", "3")
    # Without this the page renders an empty results container and no error.
    assert call["data"]["displayFormatBox"] == "1"


def test_results_every_round(site):
    site.page = ""
    asyncio.run(results_module.get_results(EventType.PREDEFINED, 5, [11]))
    assert site.calls[0]["params"]["roundId"] == ""
