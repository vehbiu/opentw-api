from typing import Any, Optional

from sanic.response import JSONResponse


class Response(JSONResponse):
    def __init__(
        self: "Response",
        ok: bool = False,
        data: Any = None,
        status: int = 200,
        error: Optional[str] = None,
    ):
        body = {"ok": ok, "data": data}
        if error is not None:
            body["error"] = error
        super().__init__(body, status=status)
