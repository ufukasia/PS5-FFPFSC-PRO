"""Logging helpers for MkPFS CLI and UI.

This module provides a compact `log` function and convenience wrappers
(`info`, `warning`, `error`) used by the CLI. It intentionally avoids
configuring the global `logging` subsystem so callers can opt-in if needed.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, TextIO


def _reconfigure_stream_utf8(stream: Any) -> None:
    """Switch a text stream to UTF-8 with lossy fallback when it is not already.

    On Windows a real console already reports UTF-8, so this only kicks in when
    stdout/stderr are redirected to a pipe or a file, where Python falls back to
    the ANSI locale codepage (cp1254, cp1252, ...) and chokes on icons.
    """
    try:
        enc: str = (getattr(stream, "encoding", "") or "").upper()
        if "UTF" in enc:
            return
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            return
        reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def ensure_utf8_output() -> None:
    """Best-effort: make stdout/stderr able to carry non-ASCII output."""
    _reconfigure_stream_utf8(sys.stdout)
    _reconfigure_stream_utf8(sys.stderr)


# Applied at import time so every entrypoint (CLI, `python -m mkpfs`, frozen EXE)
# is protected before the first log line is emitted.
ensure_utf8_output()


def _encodable(text: str, stream: Any) -> bool:
    """Return True when `text` can be written to `stream` without raising."""
    enc: str = (getattr(stream, "encoding", "") or "") or "utf-8"
    try:
        text.encode(enc)
    except (UnicodeEncodeError, LookupError):
        return False
    except Exception:
        return False
    return True


def _safe_print(text: str, stream: TextIO) -> None:
    """Print `text`, degrading unsupported characters instead of crashing.

    A build that finished successfully must never fail on its own success
    message, so encoding problems are downgraded to replacement characters.
    """
    try:
        print(text, file=stream)
        return
    except UnicodeEncodeError:
        pass
    except Exception:
        return
    enc: str = (getattr(stream, "encoding", "") or "") or "ascii"
    try:
        fallback: str = text.encode(enc, errors="replace").decode(enc, errors="replace")
        print(fallback, file=stream)
    except Exception:
        try:
            print(text.encode("ascii", errors="replace").decode("ascii"), file=stream)
        except Exception:
            pass


def supports_utf8() -> bool:
    """Return True when terminal appears to support UTF-8 icons.

    Honor the `MKPFS_NO_UTF8` environment variable to force ASCII-only
    output (useful in CI and tests).
    """
    env_val: str | None = os.environ.get("MKPFS_NO_UTF8")
    if env_val:
        return False
    enc: str = getattr(sys.stdout, "encoding", "") or ""
    if not enc:
        return False
    return "UTF-8" in enc.upper()


def icon(name: str | None) -> str:
    """Map a semantic icon name to a UTF-8 glyph or an ASCII fallback."""
    utf8: dict[str, str] = {"info": "ℹ️", "ok": "✅", "warning": "⚠️", "error": "❌", "file": "📄", "success": "🎉"}
    ascii_map: dict[str, str] = {
        "info": "INFO",
        "ok": "OK",
        "warning": "WARN",
        "error": "ERROR",
        "file": "FILE",
        "success": "SUCCESS",
    }
    name_key: str = name or ""
    return utf8.get(name_key, "") if supports_utf8() else ascii_map.get(name_key, "")


def log(message: str, level: int = logging.INFO, icon_name: str | None = None) -> None:
    """Print a message to stdout/stderr using the provided logging level.

    Args:
        message: The textual message to emit.
        level: One of logging.INFO, logging.WARNING, logging.ERROR, logging.DEBUG.
        icon_name: Optional semantic icon name to prefix the message.
    """
    prefix: str = (icon(icon_name) + " ") if icon_name else ""
    text: str = prefix + str(message)
    # Colorize output when terminal appears to support colors and the user has not
    # disabled colors via MKPFS_NO_COLOR. Keep logic simple and fall back to plain
    # output when unsure.
    no_color_env: str | None = os.environ.get("MKPFS_NO_COLOR")
    use_color: bool = False
    try:
        use_color = bool(
            (getattr(sys.stderr, "isatty", lambda: False)() or getattr(sys.stdout, "isatty", lambda: False)())
            and not no_color_env
        )
    except Exception:
        use_color = False

    color_code: str = ""
    reset_code: str = ""
    if use_color:
        reset_code = "\x1b[0m"
        if level >= logging.ERROR:
            color_code = "\x1b[31m"  # red
        elif level >= logging.WARNING:
            color_code = "\x1b[38;5;208m"  # orange (256-color)
        else:
            color_code = ""

    colored_text: str = f"{color_code}{text}{reset_code}" if color_code else text
    stream: TextIO = sys.stderr if level >= logging.ERROR else sys.stdout
    # Messages may embed literal emoji regardless of `icon()`; strip them when the
    # target stream cannot represent them (redirected output on a non-UTF-8 locale).
    if not _encodable(colored_text, stream):
        colored_text = "".join(ch if _encodable(ch, stream) else "" for ch in colored_text).strip() or text
    _safe_print(colored_text, stream)


def info(message: str, icon_name: str | None = None) -> None:
    """Convenience wrapper for informational messages."""
    log(message, level=logging.INFO, icon_name=icon_name)


def warning(message: str, icon_name: str | None = None) -> None:
    """Convenience wrapper for warnings."""
    log(message, level=logging.WARNING, icon_name=icon_name)


def error(message: str, icon_name: str | None = None) -> None:
    """Convenience wrapper for errors."""
    log(message, level=logging.ERROR, icon_name=icon_name)
