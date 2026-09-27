"""Reading saved text in any encoding it announces, and mending half characters."""

import codecs

import pytest

from convolvger.core.findings import Level
from convolvger.core.models import (
    Conversation,
    Message,
    MessageRole,
    TextBlock,
    ToolResultBlock,
    UnknownBlock,
)
from convolvger.core.results import ParseResult
from convolvger.core.text import (
    TextEncodingError,
    decode_text,
    replace_unpaired_surrogates,
)
from convolvger.validation.aspects import ASPECTS, Aspect

TEXT = '{"t": "مرحبا 你好 \U0001f44b\U0001f3fd \U0001e900"}'


@pytest.mark.parametrize(
    ("mark", "codec"),
    [
        (codecs.BOM_UTF8, "utf-8"),
        (codecs.BOM_UTF16_LE, "utf-16-le"),
        (codecs.BOM_UTF16_BE, "utf-16-be"),
        (codecs.BOM_UTF32_LE, "utf-32-le"),
        (codecs.BOM_UTF32_BE, "utf-32-be"),
    ],
)
def test_text_behind_any_byte_order_mark_is_read_and_the_mark_dropped(
    mark: bytes, codec: str
) -> None:
    assert decode_text(mark + TEXT.encode(codec)) == TEXT


def test_utf32_little_endian_is_not_mistaken_for_utf16() -> None:
    """Its mark begins with UTF-16's, so the order of the checks matters."""
    assert decode_text(codecs.BOM_UTF32_LE + "ab".encode("utf-32-le")) == "ab"


def test_plain_utf8_is_read_as_it_is() -> None:
    assert decode_text(TEXT.encode("utf-8")) == TEXT


def test_a_mark_inside_the_text_is_content_and_kept() -> None:
    assert decode_text("a﻿b".encode()) == "a﻿b"


def test_a_legacy_code_page_is_refused_rather_than_guessed() -> None:
    with pytest.raises(TextEncodingError, match="Save it again as UTF-8"):
        decode_text("Café".encode("cp1252"))


def test_a_mark_followed_by_something_else_is_refused() -> None:
    with pytest.raises(TextEncodingError, match="byte-order mark"):
        decode_text(codecs.BOM_UTF8 + b"\xff\xfe\xfd")


def result(*messages: Message, title: str = "t", url: str = "https://x") -> ParseResult:
    return ParseResult(
        conversation=Conversation(
            provider="p", source_url=url, title=title, messages=list(messages)
        )
    )


def text_message(text: str, identifier: str = "m1") -> Message:
    return Message(
        id=identifier, role=MessageRole.ASSISTANT, content=[TextBlock(text=text)]
    )


def test_a_result_with_nothing_to_mend_comes_back_unchanged() -> None:
    clean = result(text_message("wave \U0001f44b\U0001f3fd 你好"))
    assert replace_unpaired_surrogates(clean) is clean


@pytest.mark.parametrize("half", ["\ud83d", "\udc4b"])
def test_either_half_alone_is_replaced_and_attributed_to_its_message(half: str) -> None:
    mended = replace_unpaired_surrogates(result(text_message(f"cut {half}off")))

    block = mended.conversation.messages[0].content[0]
    assert isinstance(block, TextBlock)
    assert block.text == "cut �off"
    assert [(f.code, f.message_id) for f in mended.findings] == [
        ("unpaired_surrogate_replaced", "m1")
    ]
    assert mended.findings[0].message.startswith("1 unpaired surrogate(s)")


def test_the_new_code_is_a_fidelity_warning() -> None:
    mended = replace_unpaired_surrogates(result(text_message("\ud83d")))
    assert mended.findings[0].level is Level.WARNING
    assert ASPECTS["unpaired_surrogate_replaced"] is Aspect.FIDELITY


def test_every_string_in_a_message_is_mended_and_counted() -> None:
    message = Message(
        id="m1",
        role=MessageRole.TOOL,
        content=[
            ToolResultBlock(content=[TextBlock(text="\ud83d")]),
            UnknownBlock(type="x", raw={"key\udc00": ["\ud800"]}),
        ],
        provider_metadata={"sender": "\udfff"},
    )
    mended = replace_unpaired_surrogates(result(message))

    fixed = mended.conversation.messages[0]
    assert fixed.provider_metadata == {"sender": "�"}
    unknown = fixed.content[1]
    assert isinstance(unknown, UnknownBlock)
    assert unknown.raw == {"key�": ["�"]}
    assert mended.findings[0].message.startswith("4 unpaired surrogate(s)")


def test_a_half_in_the_title_or_url_is_reported_against_the_conversation() -> None:
    """A URL from a command line can carry one where argv was not valid text."""
    mended = replace_unpaired_surrogates(
        result(
            text_message("fine"), title="t\ud83d", url="https://grok.com/share/a\udcff"
        )
    )

    assert mended.conversation.title == "t�"
    assert mended.conversation.source_url == "https://grok.com/share/a�"
    assert [(f.code, f.message_id) for f in mended.findings] == [
        ("unpaired_surrogate_replaced", None)
    ]
    assert "conversation's own fields" in mended.findings[0].message


def test_untouched_messages_are_kept_as_they_were() -> None:
    kept = text_message("fine", "m1")
    mended = replace_unpaired_surrogates(result(kept, text_message("\ud83d", "m2")))
    assert mended.conversation.messages[0] is kept
