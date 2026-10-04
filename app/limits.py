"""Single-worker admission limits. These intentionally reset on process restart."""
from collections import deque
from time import monotonic
from fastapi import HTTPException
from starlette.responses import JSONResponse
from app.config import settings

class Admission:
    def __init__(self):
        self.active = 0
        self.arrivals = deque()

    def enter(self):
        now = monotonic()
        while self.arrivals and self.arrivals[0] <= now - 60:
            self.arrivals.popleft()
        if self.active >= settings.max_concurrent_runs or len(self.arrivals) >= settings.requests_per_minute:
            raise HTTPException(429, 'Run limit reached. Retry shortly.', headers={'Retry-After': '60'})
        self.arrivals.append(now)
        self.active += 1

    def leave(self):
        self.active -= 1

class BodyLimit:
    def __init__(self, app, max_bytes=240000):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in ('POST', 'PUT', 'PATCH'):
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            size += len(message.get('body', b''))
            if size > self.max_bytes:
                return await JSONResponse({'detail': 'Request body exceeds 240000 bytes.'}, status_code=413)(scope, receive, send)
            chunks.append(message)
            if not message.get('more_body'):
                break
        async def replay():
            return chunks.pop(0) if chunks else await receive()
        await self.app(scope, replay, send)

