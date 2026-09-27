"""Text that arrives in a form Python cannot write back out.

Two problems, both about text in general rather than any one provider or
language, so both are solved here once.

A saved snapshot is bytes, and how those bytes encode text depends on
what saved them. A browser saves UTF-8. Notepad has been known to put a
UTF-8 byte-order mark in front, and Windows PowerShell 5.1's ``>``
writes UTF-16. Each announces itself with a byte-order mark, so each is
read. A file with no mark is read as UTF-8 or refused: guessing a legacy
code page would turn Arabic or Chinese into plausible-looking nonsense,
which is worse than an error.

A provider's JSON can carry half a character. Anything outside the basic
plane -- every emoji, many CJK characters, Adlam and Osage -- is escaped
in JSON as two halves, a surrogate pair, and a reply cut off between
them leaves one half alone. Python holds it, but it cannot be encoded as
UTF-8, so writing the archive fails. The half is replaced with U+FFFD,
the character Unicode reserves for exactly this, and the replacement is
recorded as a finding rather than made quietly. A whole pair is
recombined by the JSON decoder before this sees it, so only a genuine
half is ever touched.
"""

import codecs
import re
from typing import Any

from convolvger.core.errors import ConvolvgerError
from convolvger.core.findings import Finding, collapse, finding
from convolvger.core.models import Message
from convolvger.core.results import ParseResult

BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)
"""Byte-order marks, longest first.

The UTF-32 little-endian mark begins with the UTF-16 little-endian one,
so checking UTF-16 first would misread every UTF-32 file.
"""

SURROGATE = re.compile("[\ud800-\udfff]")
REPLACEMENT = "�"


class TextEncodingError(ConvolvgerError):
    """Raised when bytes are not text in an encoding this tool reads."""


def decode_text(data: bytes) -> str:
    """Return the text in ``data``, honouring a byte-order mark if present.

    The mark is removed: it describes the file, not the conversation.
    """
    for mark, encoding in BOMS:
        if data.startswith(mark):
            try:
                return data[len(mark) :].decode(encoding)
            except UnicodeDecodeError as error:
                raise TextEncodingError(
                    f"The file begins with a {encoding.upper()} byte-order mark "
                    f"but is not valid {encoding.upper()}: {error}"
                ) from error
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise TextEncodingError(
            "The file is not UTF-8, and has no byte-order mark saying it is "
            "UTF-16 or UTF-32. Save it again as UTF-8; a legacy code page is "
            "not guessed, because a wrong guess produces the wrong text."
        ) from error


def _scrub(value: Any) -> tuple[Any, int]:
    """Replace every lone surrogate in ``value``, counting them."""
    if isinstance(value, str):
        return SURROGATE.subn(REPLACEMENT, value)
    if isinstance(value, dict):
        total = 0
        cleaned: dict[Any, Any] = {}
        for key, item in value.items():
            new_key, in_key = _scrub(key)
            new_item, in_item = _scrub(item)
            cleaned[new_key] = new_item
            total += in_key + in_item
        return cleaned, total
    if isinstance(value, list):
        total = 0
        items = []
        for item in value:
            new_item, count = _scrub(item)
            items.append(new_item)
            total += count
        return items, total
    return value, 0


def _replaced(count: int, where: str) -> str:
    return f"{count} unpaired surrogate(s) in {where} replaced with U+FFFD"


def replace_unpaired_surrogates(result: ParseResult) -> ParseResult:
    """Return ``result`` with every lone surrogate replaced and reported.

    Every string is covered, not only message text: a title can carry
    one, and so can a URL typed on a command line whose bytes were not
    valid in the terminal's encoding. A result with none comes back as
    the same object, so the common case costs one pass and no copies.
    """
    conversation = result.conversation
    added: list[Finding] = []

    messages: list[Message] = []
    for message in conversation.messages:
        data, count = _scrub(message.model_dump())
        if count:
            messages.append(Message.model_validate(data))
            added.append(
                finding(
                    "unpaired_surrogate_replaced",
                    _replaced(count, "the message"),
                    message.id,
                )
            )
        else:
            messages.append(message)

    envelope, count = _scrub(conversation.model_dump(exclude={"messages"}))
    if count:
        added.append(
            finding(
                "unpaired_surrogate_replaced",
                _replaced(count, "the conversation's own fields"),
            )
        )

    # A finding's text is this tool's own prose around provider values,
    # not content, so it is cleaned without a finding of its own.
    existing = [
        item.model_copy(update={"message": _scrub(item.message)[0]})
        for item in result.findings
    ]
    if not added and existing == result.findings:
        return result

    return ParseResult(
        conversation=conversation.model_copy(update={**envelope, "messages": messages}),
        findings=collapse([*existing, *added]),
    )
