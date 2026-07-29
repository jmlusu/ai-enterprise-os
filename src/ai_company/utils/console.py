"""Cross-platform console utilities for safe terminal output.

All CLI modules should use :func:`console_print` instead of ``rich.print``
directly.  On Windows / legacy terminals any Unicode characters that cannot be
encoded are automatically replaced with ASCII-safe alternatives so commands
never crash with ``UnicodeEncodeError``.
"""

import os
import sys

from rich.console import Console

_UNICODE_TO_ASCII: dict[str, str] = {
    "\u2713": "[OK]",  # ✓
    "\u2717": "[X]",  # ✗
    "\u2714": "[OK]",  # ✔
    "\u2716": "[X]",  # ✖
    "\u2705": "[OK]",  # ✅
    "\u274c": "[X]",  # ❌
    "\u26a0": "[!]",  # ⚠
    "\u2139": "[i]",  # ℹ
    "\u2192": "->",  # →
    "\u2190": "<-",  # ←
    "\u25cf": "*",  # ●
}

_USE_ASCII = False


def _detect_legacy_terminal() -> bool:
    """Return True when the terminal is known to have limited Unicode support."""
    if os.environ.get("NO_COLOR"):
        return True
    if sys.platform == "win32":
        if not sys.stdout.isatty():
            return True
        try:
            import ctypes

            cp = ctypes.windll.kernel32.GetConsoleOutputCP()
            if cp != 65001:
                return True
        except (OSError, AttributeError):
            return True
    return False


def configure_console(*, force_ascii: bool | None = None) -> None:
    """Call once at startup to set console mode.

    Parameters
    ----------
    force_ascii:
        If ``True`` always use ASCII replacements.  If ``None`` (default)
        auto-detect based on the terminal capabilities.
    """
    global _USE_ASCII
    _USE_ASCII = force_ascii if force_ascii is not None else _detect_legacy_terminal()


def _sanitize(text: str) -> str:
    if not _USE_ASCII:
        return text
    for unicode_char, ascii_replacement in _UNICODE_TO_ASCII.items():
        text = text.replace(unicode_char, ascii_replacement)
    return text


_console = Console(highlight=False)


def console_print(*args: object, **kwargs: object) -> None:
    """Print with automatic Unicode-to-ASCII fallback on legacy terminals.

    Accepts the same arguments as ``rich.print``.
    """
    text = " ".join(str(a) for a in args)
    if _USE_ASCII:
        text = _sanitize(text)
    try:
        _console.print(text, **kwargs)  # type: ignore[arg-type]
    except (UnicodeEncodeError, UnicodeDecodeError):
        plain = _sanitize(text)
        for ch, rep in _UNICODE_TO_ASCII.items():
            plain = plain.replace(ch, rep)
        sys.stdout.write(plain + "\n")


def console_print_plain(text: str) -> None:
    """Print plain text without any Rich markup processing.

    Safe for all terminals. Never raises Unicode-related errors.
    """
    try:
        sys.stdout.write(text + "\n")
    except (UnicodeEncodeError, UnicodeDecodeError):
        safe = text.encode("ascii", errors="replace").decode("ascii")
        sys.stdout.write(safe + "\n")
