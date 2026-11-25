import asyncio
import json
import re
import time
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

from aiohttp import ClientError, ClientSession, ClientTimeout, CookieJar, TCPConnector

from . import _get_timestamp
from models.ttypes import EventType

__all__ = ["session_manager", "UpstreamError"]

BASE_URL = "https://www.trackwrestling.com"

# Since autumn 2026 TrackWrestling hands tournament viewing to FloWrestling: the viewer login
# redirects to flowrestling.org/events/<id>, whose pages read this JSON API.
FLO_API_URL = "https://prod-web-api.flowrestling.org/api"

# Identify honestly. TrackWrestling's CDN rejects (HTTP 406) a client that claims to be a
# browser but doesn't connect like one, so a browser user agent here gets every request blocked.
HEADERS = {
    "User-Agent": "opentw-api (+https://github.com/vehbiu/opentw-api)",
}

# Viewer sessions time out on TrackWrestling's side, so re-verify well before that happens.
SESSION_TTL = 15 * 60
MAX_SESSIONS = 256

# TrackWrestling's CDN blocks an IP that sends bursts of requests (HTTP 406), and the block
# lasts a while. Space every outgoing request at least this far apart, across all clients.
MIN_REQUEST_INTERVAL = 0.5

# FloWrestling's API serves its own single-page app, which makes a dozen calls per page view;
# a few a second from us is well within that.
FLO_MIN_REQUEST_INTERVAL = 0.15

# How long to remember where a tournament lives. A tournament that is still on TrackWrestling
# may move, so that answer is kept for less time.
FLO_RESOLVED_TTL = 6 * 60 * 60
TW_RESOLVED_TTL = 15 * 60

# A retired session may still be mid-request; close it once those requests have had time to end.
RETIRED_SESSION_GRACE = 60


class _Throttle:
    def __init__(self, interval: float):
        self._interval = interval
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._next > now:
                await asyncio.sleep(self._next - now)
            self._next = max(now, self._next) + self._interval


class UpstreamError(Exception):
    """TrackWrestling or FloWrestling could not be reached or refused the request."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class _SessionManager:
    """Shares one connection pool, with a cookie jar per tournament.

    Tournament pages only work after a viewer "login" (VerifyPassword.jsp) sets a cookie, so
    each tournament gets its own jar. The connections underneath are shared.
    """

    def __init__(self):
        self._connector: Optional[TCPConnector] = None
        self._anonymous: Optional[ClientSession] = None
        self._sessions: "OrderedDict[Tuple[EventType, int], Tuple[ClientSession, float]]" = OrderedDict()
        self._locks: Dict[Tuple[EventType, int], asyncio.Lock] = {}
        self._throttle = _Throttle(MIN_REQUEST_INTERVAL)
        self._flo_throttle = _Throttle(FLO_MIN_REQUEST_INTERVAL)
        self._flo_events: Dict[Tuple[EventType, int], Tuple[Optional[str], float]] = {}

    def _new_session(self) -> ClientSession:
        if self._connector is None or self._connector.closed:
            self._connector = TCPConnector(limit=20, ttl_dns_cache=300)
        return ClientSession(
            connector=self._connector,
            connector_owner=False,
            cookie_jar=CookieJar(),
            headers=HEADERS,
            timeout=ClientTimeout(total=20),
        )

    async def _tournament_session(self, event_type: EventType, tournament_id: int) -> ClientSession:
        key = (event_type, tournament_id)
        lock = self._locks.setdefault(key, asyncio.Lock())

        async with lock:
            cached = self._sessions.get(key)
            if cached and time.monotonic() - cached[1] < SESSION_TTL:
                self._sessions.move_to_end(key)
                return cached[0]

            if cached:
                self._sessions.pop(key, None)
                self._retire(cached[0])

            session = self._new_session()
            try:
                await self._request(
                    session,
                    f"{event_type.tournament_type}/VerifyPassword.jsp",
                    {
                        "tournamentId": tournament_id,
                        "userType": "viewer",
                        "userName": "",
                        "password": "",
                    },
                )
            except BaseException:
                await session.close()
                # Nothing is cached for this key, so don't keep its lock either: failed ids would
                # otherwise pile up a lock each. Anyone already waiting holds their own reference.
                self._locks.pop(key, None)
                raise

            self._sessions[key] = (session, time.monotonic())
            self._sessions.move_to_end(key)

            while len(self._sessions) > MAX_SESSIONS:
                old_key, (old_session, _) = self._sessions.popitem(last=False)
                old_lock = self._locks.get(old_key)
                if old_lock is not None and not old_lock.locked():
                    self._locks.pop(old_key, None)
                self._retire(old_session)

            return session

    def _retire(self, session: ClientSession) -> None:
        """Close a session later rather than now: another request may still be using it."""
        loop = asyncio.get_running_loop()
        loop.call_later(RETIRED_SESSION_GRACE, lambda: loop.create_task(session.close()))

    async def _request(self, session: ClientSession, path: str, params: dict) -> str:
        await self._throttle.wait()
        params = {"TIM": _get_timestamp(), "twSessionId": "zyxwvutsrq", **params}
        try:
            async with session.get(f"{BASE_URL}/{path}", params=params) as response:
                if response.status != 200:
                    raise UpstreamError(
                        f"TrackWrestling returned HTTP {response.status} for {path}",
                        response.status,
                    )
                return await response.text(errors="replace")
        except (ClientError, asyncio.TimeoutError) as exc:
            raise UpstreamError(f"Could not reach TrackWrestling: {type(exc).__name__}") from exc
        except RuntimeError as exc:  # "Session is closed": retired under us after cleanup()
            raise UpstreamError(f"TrackWrestling session ended mid-request: {exc}") from exc

    async def fetch(
        self,
        path: str,
        params: Optional[dict] = None,
        tournament_id: Optional[int] = None,
        event_type: EventType = EventType.PREDEFINED,
    ) -> str:
        """GET a TrackWrestling page and return its text.

        With a tournament id, the request goes through that tournament's viewer session.
        """
        if tournament_id is None:
            session = self._anonymous_session()
        else:
            session = await self._tournament_session(event_type, tournament_id)

        try:
            return await self._request(session, path, params or {})
        except UpstreamError as exc:
            # A stale or broken session is the usual cause; start over next time. Only if the
            # cached session is still the one this request used: another request may already
            # have replaced it. A 404 is the page, not the session.
            key = (event_type, tournament_id)
            if tournament_id is not None and exc.status != 404:
                cached = self._sessions.get(key)
                if cached and cached[0] is session:
                    del self._sessions[key]
                    self._retire(session)
            raise

    # -----------------------------------------------------------------------------------------
    # FloWrestling
    # -----------------------------------------------------------------------------------------

    def _anonymous_session(self) -> ClientSession:
        if self._anonymous is None or self._anonymous.closed:
            self._anonymous = self._new_session()
        return self._anonymous

    async def flowrestling_event(self, event_type: EventType, tournament_id: int) -> Optional[str]:
        """The FloWrestling event id a TrackWrestling tournament now lives at, or None.

        TrackWrestling's viewer login answers with a redirect to flowrestling.org/events/<id>
        for tournaments it has handed over; tournaments still on TrackWrestling get no redirect.
        The answer is remembered, so this costs one request per tournament every few hours.
        """
        key = (event_type, tournament_id)
        cached = self._flo_events.get(key)
        if cached:
            event_id, at = cached
            if time.monotonic() - at < (FLO_RESOLVED_TTL if event_id else TW_RESOLVED_TTL):
                return event_id

        await self._throttle.wait()
        url = f"{BASE_URL}/{event_type.tournament_type}/VerifyPassword.jsp"
        params = {"TIM": _get_timestamp(), "twSessionId": "zyxwvutsrq", "tournamentId": tournament_id,
                  "userType": "viewer", "userName": "", "password": ""}
        try:
            async with self._anonymous_session().get(url, params=params, allow_redirects=False) as response:
                location = response.headers.get("Location", "") if response.status in (301, 302, 303, 307, 308) else ""
                if response.status >= 400:
                    raise UpstreamError(f"TrackWrestling returned HTTP {response.status} for VerifyPassword.jsp", response.status)
        except (ClientError, asyncio.TimeoutError) as exc:
            raise UpstreamError(f"Could not reach TrackWrestling: {type(exc).__name__}") from exc

        event_id = None
        if "flowrestling.org" in location:
            match = re.search(r"/events/(\d+)", location)
            if not match:
                raise UpstreamError(
                    "TrackWrestling now sends this tournament to FloWrestling, which has no page for it", 404
                )
            event_id = match.group(1)

        self._flo_events[key] = (event_id, time.monotonic())
        if len(self._flo_events) > 4096:
            self._flo_events.pop(next(iter(self._flo_events)))
        return event_id

    async def flo(self, path: str, params: Optional[dict] = None, body: Optional[dict] = None) -> Any:
        """GET (or with `body`, POST) FloWrestling's JSON API and return the decoded JSON."""
        await self._flo_throttle.wait()
        url = f"{FLO_API_URL}/{path}"
        headers = {"Accept": "application/json"}
        try:
            session = self._anonymous_session()
            request = (session.post(url, params=params, json=body, headers=headers) if body is not None
                       else session.get(url, params=params, headers=headers))
            async with request as response:
                text = await response.text(errors="replace")
                if response.status != 200:
                    raise UpstreamError(f"FloWrestling returned HTTP {response.status} for {path}", response.status)
        except (ClientError, asyncio.TimeoutError) as exc:
            raise UpstreamError(f"Could not reach FloWrestling: {type(exc).__name__}") from exc
        except RuntimeError as exc:
            raise UpstreamError(f"FloWrestling session ended mid-request: {exc}") from exc
        try:
            return json.loads(text)
        except ValueError as exc:
            raise UpstreamError(f"FloWrestling returned something other than JSON for {path}") from exc

    async def cleanup(self):
        for session, _ in self._sessions.values():
            await session.close()
        self._sessions.clear()
        self._locks.clear()
        if self._anonymous is not None:
            await self._anonymous.close()
            self._anonymous = None
        if self._connector is not None:
            await self._connector.close()
            self._connector = None


session_manager = _SessionManager()
