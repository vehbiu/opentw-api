"""Session caching, and recognising TrackWrestling's empty shells."""
import asyncio

import pytest

from models.ttypes import EventType
from utils.session_manager import TournamentUnavailable, _SessionManager, is_stub

from .fakes import NO_SESSION_SHELL, WRONG_TYPE_SHELL, FakeSession


@pytest.mark.parametrize("html, expected", [
    (NO_SESSION_SHELL, True),
    (WRONG_TYPE_SHELL, True),
    ("<html><head><style>x{}</style><noscript>n</noscript></head></html>", True),
    # An empty mat assignment page is small but still has text.
    ("<html><body>Mat Assignment Display LOADING...</body></html>", False),
    # A big page is never a shell, whatever it loads.
    ("<script src='GoToLogin.js'></script>" + "<p>x</p>" * 1000, False),
    ("", True),
])
def test_is_stub(html, expected):
    assert is_stub(html) is expected


def manager_with(sessions):
    """A manager whose _open hands out the given fake sessions in order."""
    manager = _SessionManager()
    opened = []

    async def _open(tournament_id, event_type):
        session = sessions[len(opened)]
        opened.append((tournament_id, event_type))
        return session

    manager._open = _open
    return manager, opened


def run(coro):
    return asyncio.run(coro)


def test_fetch_returns_the_page_and_reuses_the_session():
    session = FakeSession(lambda *_: "<html><body>real page</body></html>")
    manager, opened = manager_with([session])

    async def go():
        a = await manager.fetch("GET", "u1", 1, EventType.PREDEFINED, params={"a": 1})
        b = await manager.fetch("POST", "u2", 1, EventType.PREDEFINED, data={"b": 2})
        return a, b

    a, b = run(go())
    assert a == b == "<html><body>real page</body></html>"
    assert opened == [(1, EventType.PREDEFINED)]
    assert [(m, u) for m, u, _ in session.requests] == [("GET", "u1"), ("POST", "u2")]
    assert session.requests[1][2] == {"data": {"b": 2}}


def test_sessions_are_per_tournament_and_type():
    sessions = [FakeSession(lambda *_: "<p>ok</p>") for _ in range(3)]
    manager, opened = manager_with(sessions)

    async def go():
        await manager.fetch("GET", "u", 1, EventType.PREDEFINED)
        await manager.fetch("GET", "u", 1, EventType.OPEN)
        await manager.fetch("GET", "u", 2, EventType.PREDEFINED)
        await manager.fetch("GET", "u", 1, EventType.PREDEFINED)

    run(go())
    assert opened == [(1, EventType.PREDEFINED), (1, EventType.OPEN), (2, EventType.PREDEFINED)]


def test_expired_session_is_reopened_once():
    dead = FakeSession(lambda *_: NO_SESSION_SHELL)
    fresh = FakeSession(lambda *_: "<p>real page</p>")
    manager, opened = manager_with([dead, fresh])

    assert run(manager.fetch("GET", "u", 1, EventType.PREDEFINED)) == "<p>real page</p>"
    assert len(opened) == 2
    assert dead.closed
    assert manager.sessions[(1, EventType.PREDEFINED)] is fresh


def test_shell_twice_raises_instead_of_returning_an_empty_tournament():
    manager, opened = manager_with([FakeSession(lambda *_: WRONG_TYPE_SHELL) for _ in range(2)])

    with pytest.raises(TournamentUnavailable, match="'open'"):
        run(manager.fetch("GET", "u", 1, EventType.OPEN))
    assert len(opened) == 2
    assert (1, EventType.OPEN) not in manager.sessions


def test_a_failed_request_drops_the_session():
    def boom(*_):
        raise ConnectionError("reset")

    session = FakeSession(boom)
    manager, _ = manager_with([session])

    with pytest.raises(ConnectionError):
        run(manager.fetch("GET", "u", 1, EventType.PREDEFINED))
    assert session.closed
    assert manager.sessions == {}


def test_cleanup_closes_everything():
    sessions = [FakeSession(lambda *_: "<p>ok</p>") for _ in range(2)]
    manager, _ = manager_with(sessions)

    async def go():
        await manager.fetch("GET", "u", 1, EventType.PREDEFINED)
        await manager.fetch("GET", "u", 2, EventType.PREDEFINED)
        await manager.cleanup()

    run(go())
    assert all(s.closed for s in sessions)
    assert manager.sessions == {}
