"""Logging helpers for the WebUI WebSocket server surface."""

from __future__ import annotations

import logging

from websockets.exceptions import ConnectionClosed

OPENING_HANDSHAKE_FAILED_MESSAGE = "opening handshake failed"

# websockets' http11 parser rejects non-GET methods before process_request
# runs, raising ValueError("unsupported HTTP method; expected GET; got HEAD").
# These come from platform health checks / uptime monitors (e.g. HEAD, OPTIONS
# probes) and are benign — the WebSocket surface only speaks GET upgrades.
_UNSUPPORTED_METHOD_PREFIX = "unsupported HTTP method"


def _exception_chain_has_unsupported_method(exc: BaseException | None) -> bool:
    seen: set[int] = set()
    while exc is not None:
        ident = id(exc)
        if ident in seen:
            return False
        seen.add(ident)
        if isinstance(exc, ValueError) and str(exc).startswith(_UNSUPPORTED_METHOD_PREFIX):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def _exception_chain_has_disconnect(exc: BaseException | None) -> bool:
    seen: set[int] = set()
    while exc is not None:
        ident = id(exc)
        if ident in seen:
            return False
        seen.add(ident)
        if isinstance(exc, (
            BrokenPipeError,
            ConnectionAbortedError,
            ConnectionResetError,
            ConnectionClosed,
            EOFError,
        )):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


class WebSocketHandshakeNoiseFilter(logging.Filter):
    """Suppress benign handshake failures on the WebUI WebSocket surface.

    Drops two known-noisy cases logged at ERROR by ``websockets``:
    - restart-time handshakes where the browser already disconnected, and
    - non-GET probes (HEAD/OPTIONS) from platform health checks / uptime
      monitors, which the parser rejects before ``process_request`` runs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.getMessage() != OPENING_HANDSHAKE_FAILED_MESSAGE:
            return True
        exc_info = record.exc_info
        exc = exc_info[1] if isinstance(exc_info, tuple) and len(exc_info) >= 2 else None
        if _exception_chain_has_disconnect(exc):
            return False
        return not _exception_chain_has_unsupported_method(exc)


def websockets_server_logger() -> logging.Logger:
    ws_logger = logging.getLogger("websockets.server")
    if not any(isinstance(f, WebSocketHandshakeNoiseFilter) for f in ws_logger.filters):
        ws_logger.addFilter(WebSocketHandshakeNoiseFilter())
    return ws_logger
