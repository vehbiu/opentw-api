import re
from typing import Dict, Tuple
from . import _get_timestamp
from aiohttp import ClientSession
from models.ttypes import EventType
from contextlib import asynccontextmanager

__all__ = ["session_manager", "is_stub", "TournamentUnavailable"]

# Who we say we are, so anyone reading TrackWrestling's logs has somewhere to look.
USER_AGENT = "opentw-api (+https://github.com/vehbiu/opentw-api)"


_INVISIBLE = re.compile(r"(?is)<(script|style|noscript)\b.*?</\1>|<!--.*?-->|<[^>]+>")


def is_stub(html: str) -> bool:
    """Whether TrackWrestling sent an empty shell instead of the page.

    It does this with a 200 in two cases: without a viewer session (a ~1.2KB page that loads
    GoToLogin.js), and when the tournament is asked for under the wrong event type (a ~1.1KB
    page of analytics scripts). Neither has any visible content, and both parse as a tournament
    with no data unless recognised. Real pages, even an empty mat assignment, are larger and
    carry text.
    """
    return len(html) < 4000 and not _INVISIBLE.sub("", html).strip()


class TournamentUnavailable(Exception):
    """TrackWrestling kept sending an empty shell even after a fresh session."""


class _SessionManager:
    def __init__(self):
        # Keyed by event type too: the session is opened against one site path, and a session
        # opened against the wrong one would otherwise be reused for the tournament forever.
        self.sessions: Dict[Tuple[int, EventType], ClientSession] = {}

    async def cleanup(self):
        for session in self.sessions.values():
            if not session.closed:
                await session.close()
        self.sessions.clear()

    async def _open(self, tournament_id: int, event_type: EventType) -> ClientSession:
        session = ClientSession(headers={"User-Agent": USER_AGENT})
        await session.get(
            f"https://www.trackwrestling.com/{event_type.tournament_type}/VerifyPassword.jsp",
            params={
                "TIM": _get_timestamp(),
                "twSessionId": "zyxwvutsrq",
                "tournamentId": tournament_id,
                "userType": "viewer",
                "userName": "",
                "password": "",
            }
        )
        return session

    async def _drop(self, key: Tuple[int, EventType]) -> None:
        session = self.sessions.pop(key, None)
        if session and not session.closed:
            await session.close()

    @asynccontextmanager
    async def get_session(self, tournament_id: int = None, event_type: EventType = EventType.PREDEFINED):
        if tournament_id is None:
            async with ClientSession(headers={"User-Agent": USER_AGENT}) as session:
                yield session
            return

        key = (tournament_id, event_type)
        try:
            if key not in self.sessions:
                self.sessions[key] = await self._open(tournament_id, event_type)
            yield self.sessions[key]
        except Exception:
            await self._drop(key)
            raise

    async def fetch(
            self,
            method: str,
            url: str,
            tournament_id: int,
            event_type: EventType,
            **kwargs) -> str:
        """Request a tournament page, re-opening the session once if it has died.

        Sessions are cached per tournament and TrackWrestling expires them, after which every
        page is an empty shell. One retry with a fresh session; a second shell - an expired
        tournament, a wrong id or a wrong type - raises rather than being handed to a parser
        as an empty tournament.
        """
        for attempt in range(2):
            async with self.get_session(tournament_id, event_type) as session:
                async with session.request(method, url, **kwargs) as response:
                    html = await response.text()

            if not is_stub(html):
                return html

            await self._drop((tournament_id, event_type))

        raise TournamentUnavailable(
            f"TrackWrestling returned an empty page for tournament {tournament_id} as "
            f"'{event_type.alias}'. Check the id, and that '{event_type.alias}' is its type."
        )

session_manager = _SessionManager()
