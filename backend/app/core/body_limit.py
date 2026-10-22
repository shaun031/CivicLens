from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class ComplaintBodyLimit:
    """Bound actual streamed bytes before multipart spooling, not only Content-Length."""

    def __init__(self, app: ASGIApp, max_bytes: int, api_max_bytes: int = 65536):
        self.app, self.max_bytes, self.api_max_bytes = app, max_bytes, api_max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if (
            scope["type"] != "http"
            or scope["method"] not in ("POST", "PUT", "PATCH", "DELETE")
            or not scope["path"].startswith("/api/")
        ):
            return await self.app(scope, receive, send)
        path = scope["path"].rstrip("/")
        upload = scope["method"] == "POST" and (
            path == "/api/complaints"
            or path.startswith("/api/officer/incidents/")
            and path.endswith("/repair-attempts")
            or path.startswith("/api/citizen/verification-requests/")
            and path.endswith("/respond")
        )
        limit = self.max_bytes if upload else self.api_max_bytes
        lengths = [value for key, value in scope["headers"] if key.lower() == b"content-length"]
        try:
            if len(lengths) > 1 or lengths and not lengths[0].isdigit():
                raise ValueError
            length = int(lengths[0]) if lengths else 0
        except ValueError:
            return await JSONResponse({"detail": "Invalid content length."}, status_code=400)(
                scope, receive, send
            )
        if length > limit:
            return await JSONResponse({"detail": "API request is too large."}, status_code=413)(
                scope, receive, send
            )
        content = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            content.extend(message.get("body", b""))
            if len(content) > limit:
                return await JSONResponse({"detail": "API request is too large."}, status_code=413)(
                    scope, receive, send
                )
            if not message.get("more_body", False):
                break
        consumed = False

        async def bounded_receive():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": bytes(content), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)
