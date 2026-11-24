"""Per-user log buffer behind the Logs button: each user only sees lines produced by their own sessions."""
import logging
from collections import defaultdict, deque
from contextvars import ContextVar

from chainlit.auth import get_current_user
from chainlit.server import app as chainlit_server
from fastapi import Depends

from logger import configure_logging

MAX_LINES = 300
_log_user: ContextVar[str | None] = ContextVar("log_user", default=None)
_buffers: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=MAX_LINES))


def tag_logs(user_id: str) -> None:
    """Attribute log lines emitted from this context (and tasks started from it) to `user_id`."""
    _log_user.set(user_id)


class _UserBufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        uid = _log_user.get()
        if uid:
            time = self.formatter.formatTime(record, "%H:%M:%S") if self.formatter else ""
            _buffers[uid].append(f"{time} {record.levelname:<7} {record.name}: {record.getMessage().strip()}")


def install() -> None:
    configure_logging()
    root = logging.getLogger()
    if not any(isinstance(h, _UserBufferHandler) for h in root.handlers):
        handler = _UserBufferHandler(level=logging.INFO)
        handler.setFormatter(logging.Formatter())
        root.addHandler(handler)


async def _session_logs(user=Depends(get_current_user)):
    return {"lines": list(_buffers.get(user.identifier if user else "anonymous", []))}


def register_logs_route() -> None:
    before = len(chainlit_server.router.routes)
    chainlit_server.add_api_route("/session-logs", _session_logs, methods=["GET"], include_in_schema=False)
    ours = chainlit_server.router.routes[before:]
    del chainlit_server.router.routes[before:]
    chainlit_server.router.routes[0:0] = ours
