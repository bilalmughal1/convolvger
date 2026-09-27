"""Where an export goes: its file name, the file itself, and the terminal.

A file is named after the conversation's title, in whatever script the
title is written. Naming it from ``a-z`` and ``0-9`` alone left a title
in Arabic, Chinese, Hindi or Russian with nothing, so every such
conversation from one provider was written to the same file and each
export silently replaced the last.

What a name keeps is decided by Unicode category, not by a list of
languages: letters, digits, and the combining marks that belong to a
letter -- without which Hindi, Thai or Yoruba words lose their vowels
and tones. The zero-width joiners Persian and several Indic scripts
write inside words are kept there too. Everything else becomes a
hyphen, which removes what Windows forbids in a name, direction
controls that can make a name display differently from what it is, and
emoji. Variation selectors are marks by category but only choose how a
character is drawn, so they are dropped.

The title is lowercased and then normalised to NFC, in that order:
lowercasing can decompose a letter, as it does Turkish dotted I, and
macOS and Linux should agree on the bytes of the same name.

A name this tool chose never replaces an existing file: the next free
``-2``, ``-3`` is used instead, claimed atomically so two exports at
once cannot both take it. A name the user chose with ``--output`` is
written as asked.
"""

import codecs
import io
import itertools
import re
import unicodedata
from pathlib import Path
from typing import TextIO

from convolvger.core.errors import ConvolvgerError

JOINERS = "\u200c\u200d"
"""Zero-width non-joiner and joiner: part of how some words are spelled."""

MAX_CHARACTERS = 60
MAX_BYTES = 200
"""A name's budget, before the ``-N`` and the extension.

Most filesystems allow 255 bytes and a character outside Latin takes two
to four, so the byte cap is what binds for most of the world's scripts;
it leaves room for any numbering suffix and extension.
"""

RESERVED = re.compile(r"(con|prn|aux|nul|(com|lpt)[0-9¹²³])")
"""Device names Windows will not create a file under, whatever follows."""


class OutputError(ConvolvgerError):
    """Raised when a rendered document cannot be written."""


def _attaches(character: str) -> bool:
    """True for a character that belongs to the one before it."""
    return character in JOINERS or unicodedata.category(character) in ("Mn", "Mc")


def _fit(stem: str) -> str:
    """Shorten ``stem`` to the budget without splitting a letter from its marks."""
    end = min(len(stem), MAX_CHARACTERS)
    while end and len(stem[:end].encode("utf-8")) > MAX_BYTES:
        end -= 1
    while 0 < end < len(stem) and _attaches(stem[end]):
        end -= 1
    return re.sub(f"[{JOINERS}-]+$", "", stem[:end])


def file_stem(title: str | None, fallback: str) -> str:
    """Return a file name, without extension, for a conversation titled ``title``."""
    text = unicodedata.normalize("NFC", (title or "").lower())
    kept: list[str] = []
    for character in text:
        category = unicodedata.category(character)
        previous = kept[-1] if kept else "-"
        if (
            category[0] in "LN"
            or (
                category in ("Mn", "Mc")
                and previous != "-"
                and "VARIATION SELECTOR" not in unicodedata.name(character, "")
            )
            or (character in JOINERS and previous not in f"-{JOINERS}")
        ):
            kept.append(character)
        else:
            kept.append("-")

    stem = re.sub("-+", "-", "".join(kept))
    stem = re.sub(f"[{JOINERS}]+(?=-|$)", "", stem).strip("-")
    stem = _fit(stem)
    if not stem:
        return fallback
    if RESERVED.fullmatch(stem):
        return f"{stem}-{fallback}"
    return stem


def _writable(text: str) -> None:
    """Refuse text that cannot be encoded, before any file is opened.

    Opening first and failing on write would leave an empty file where
    an archive was claimed.
    """
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise OutputError(
            f"The document holds text that cannot be written as UTF-8 "
            f"({error.reason}); nothing was written"
        ) from error


def write_new(stem: str, extension: str, text: str) -> Path:
    """Write ``text`` to a file that did not exist, numbering it if needed."""
    _writable(text)
    for number in itertools.count(1):
        suffix = "" if number == 1 else f"-{number}"
        path = Path(f"{stem}{suffix}.{extension}")
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(text)
        except FileExistsError:
            continue
        return path
    raise AssertionError("unreachable")


def write_to(path: Path, text: str) -> Path:
    """Write ``text`` to the path the user chose, replacing it if present."""
    _writable(text)
    path.write_text(text, encoding="utf-8")
    return path


def write_stdout(stream: TextIO, text: str) -> None:
    _writable(text)
    stream.write(text)


def use_utf8(*streams: TextIO) -> None:
    """Make each stream write UTF-8, whatever the platform chose.

    A redirected or piped stream on Windows uses the legacy code page,
    which cannot encode most scripts, so printing a title or a whole
    document failed there. A stream already writing UTF-8 -- a terminal
    almost anywhere, or a test's capture -- is left untouched, and each
    keeps its own error handling.
    """
    for stream in streams:
        if (
            isinstance(stream, io.TextIOWrapper)
            and codecs.lookup(stream.encoding).name != "utf-8"
        ):
            stream.reconfigure(encoding="utf-8", errors=stream.errors)
