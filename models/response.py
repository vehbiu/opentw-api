from sanic.response import JSONResponse


class Response(JSONResponse):
    def __init__(
        self: "Response",
        ok: bool = False,
        data: dict = None,
        error: str = None,
        status: int = None,
    ):
        body = {"ok": ok, "data": data}
        if error is not None:
            body["error"] = error
        super().__init__(body, status=status or (200 if ok else 400))
