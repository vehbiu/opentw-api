"""The HTTP routes, with the scraping functions replaced."""
import pytest

import server
from models.ttypes import BracketData, BracketSheet, EventType, TournamentResults, Weight
from utils.session_manager import TournamentUnavailable


@pytest.fixture
def client():
    return server.app.test_client


def stub(monkeypatch, name, result=None, error=None):
    calls = []

    async def fake(*args):
        calls.append(args)
        if error:
            raise error
        return result

    monkeypatch.setattr(server, name, fake)
    return calls


def test_index(client):
    _, response = client.get("/")
    assert response.status == 200
    assert response.json == {"ok": True, "data": None}


def test_unknown_tournament_type_is_a_400(client):
    _, response = client.get("/tournaments/bogus/931299132")
    assert response.status == 400
    assert response.json["ok"] is False
    assert "predefined, open, team, freestyle, season" in response.json["error"]


def test_a_tim_timestamp_is_not_a_tournament_id(client):
    _, response = client.get("/tournaments/predefined/1790006600106/brackets")
    assert response.status == 400
    assert "TIM" in response.json["error"]


def test_tournament_not_found(client, monkeypatch):
    stub(monkeypatch, "get_tournament_info", None)
    _, response = client.get("/tournaments/predefined/1")
    assert response.status == 404


def test_unavailable_tournament_is_a_404_with_the_reason(client, monkeypatch):
    stub(monkeypatch, "get_brackets", error=TournamentUnavailable("empty page for 1 as 'open'"))
    _, response = client.get("/tournaments/open/1/brackets")
    assert response.status == 404
    assert response.json == {"ok": False, "data": None, "error": "empty page for 1 as 'open'"}


def test_bracket_pages_are_parsed(client, monkeypatch):
    calls = stub(monkeypatch, "get_bracket_data_html", "<html/>")
    _, response = client.get("/tournaments/open/1/brackets/55?pages=0,2")
    assert response.json["data"] == "<html/>"
    assert calls == [(EventType.OPEN, 1, 55, [0, 2])]


def test_bad_ids_are_a_400(client):
    _, response = client.get("/tournaments/open/1/brackets/55?pages=two")
    assert response.status == 400
    assert "two" in response.json["error"]


def test_bracket_sheet(client, monkeypatch):
    calls = stub(monkeypatch, "get_bracket_sheet", BracketSheet([], [11], [], []))
    _, response = client.get("/tournaments/predefined/1/brackets/55/sheet")
    assert response.json["data"] == {"entries": [], "bout_numbers": [11], "pigtail_entrants": [], "routes": []}
    assert calls == [(EventType.PREDEFINED, 1, 55)]


def test_results_default_to_every_weight(client, monkeypatch):
    weights = [Weight(0, 11, "125", 4), Weight(1, 12, "133", 4)]
    stub(monkeypatch, "get_brackets", BracketData([], weights, [], []))
    calls = stub(monkeypatch, "get_results", TournamentResults(0, 0, [], [], []))
    _, response = client.get("/tournaments/predefined/1/results")
    assert response.status == 200
    assert calls == [(EventType.PREDEFINED, 1, [11, 12], None)]


def test_results_for_chosen_weights_and_rounds(client, monkeypatch):
    brackets = stub(monkeypatch, "get_brackets", error=AssertionError("should not enumerate weights"))
    calls = stub(monkeypatch, "get_results", TournamentResults(0, 0, [], [], []))
    client.get("/tournaments/predefined/1/results?weights=11&rounds=3,4")
    assert calls == [(EventType.PREDEFINED, 1, [11], [3, 4])]
    assert brackets == []
