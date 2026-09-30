"""Stand-ins for aiohttp, so the request side can be tested without the network."""
from typing import Callable, List, Tuple


class FakeResponse:
    def __init__(self, body: str):
        self._body = body

    async def text(self) -> str:
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """Answers every request with `respond(method, url, kwargs)` and records it."""

    def __init__(self, respond: Callable[[str, str, dict], str]):
        self.respond = respond
        self.requests: List[Tuple[str, str, dict]] = []
        self.closed = False

    def request(self, method: str, url: str, **kwargs) -> FakeResponse:
        self.requests.append((method, url, kwargs))
        return FakeResponse(self.respond(method, url, kwargs))

    async def close(self):
        self.closed = True


NO_SESSION_SHELL = "<html><head><script src='../GoToLogin.js?TIM=1'></script></head></html>"
WRONG_TYPE_SHELL = "<html><head><script>dataLayer = [];</script><!-- comScore --></head>"
