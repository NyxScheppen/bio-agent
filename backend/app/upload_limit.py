"""ASGI request-body limit for the multipart upload endpoint."""

from starlette.responses import JSONResponse


class UploadRequestTooLarge(Exception):
    pass


class UploadBodyLimitMiddleware:
    def __init__(self, app, max_body_bytes: int, path: str = "/api/upload"):
        self.app = app
        self.max_body_bytes = int(max_body_bytes)
        self.path = path

    async def __call__(self, scope, receive, send):
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != self.path
        ):
            await self.app(scope, receive, send)
            return

        headers = {
            key.lower(): value
            for key, value in scope.get("headers", [])
        }
        try:
            content_length = int(headers.get(b"content-length", b"0"))
        except (TypeError, ValueError):
            content_length = 0
        if content_length > self.max_body_bytes:
            await self._reject(scope, receive, send)
            return

        received = 0
        response_started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise UploadRequestTooLarge
            return message

        async def tracked_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except UploadRequestTooLarge:
            if response_started:
                raise
            await self._reject(scope, receive, send)

    async def _reject(self, scope, receive, send):
        response = JSONResponse(
            status_code=413,
            content={
                "detail": (
                    "上传请求体超过上限 "
                    f"{self.max_body_bytes} 字节（含 multipart 开销）"
                )
            },
        )
        await response(scope, receive, send)
