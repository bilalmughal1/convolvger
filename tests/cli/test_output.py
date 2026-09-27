"""File names in any script, numbering, and streams that write UTF-8.

Characters that cannot be seen, or told apart from another, on the page
-- controls, direction marks, zero-width joiners, combining marks and
variation selectors -- are written as ``\\uXXXX`` escapes, so the source
says exactly which code point is meant. Visible letters from other
scripts are written as themselves.
"""

import io
import json
import unicodedata
from pathlib import Path

import pytest

from convolvger.cli._output import (
    MAX_BYTES,
    MAX_CHARACTERS,
    OutputError,
    file_stem,
    use_utf8,
    write_new,
    write_to,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "multilingual" / "samples.json"
SAMPLES: list[dict[str, str]] = json.loads(FIXTURE.read_text(encoding="utf-8"))[
    "samples"
]
KEPT = {"L", "N"}

PERSIAN = "می" + "\u200c" + "خواهم"
"""A Persian word spelled with a zero-width non-joiner between its parts."""


@pytest.mark.parametrize(
    "sample", SAMPLES, ids=lambda s: f"{s['continent']}-{s['language']}"
)
def test_every_language_gets_a_name_of_its_own(sample: dict[str, str]) -> None:
    stem = file_stem(sample["text"], "grok")

    assert stem != "grok"
    assert stem == unicodedata.normalize("NFC", stem)
    assert len(stem.encode("utf-8")) <= MAX_BYTES
    assert len(stem) <= MAX_CHARACTERS
    assert not stem.startswith("-")
    assert not stem.endswith("-")
    for character in stem:
        category = unicodedata.category(character)
        assert (
            category[0] in KEPT
            or category in ("Mn", "Mc")
            or character in "-\u200c\u200d"
        ), f"U+{ord(character):04X} {category}"


@pytest.mark.parametrize(
    "sample", SAMPLES, ids=lambda s: f"{s['continent']}-{s['language']}"
)
def test_every_language_s_name_can_be_created_on_this_filesystem(
    sample: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Created for real, so a Windows runner tests Windows' own rules."""
    monkeypatch.chdir(tmp_path)
    written = write_new(file_stem(sample["text"], "grok"), "md", "x")
    assert (tmp_path / written).read_text(encoding="utf-8") == "x"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("A Test Chat", "a-test-chat"),
        ("Café résumé", "café-résumé"),
        ("cafe\u0301", "café"),
        ("İstanbul", "i\u0307stanbul"),
        ("Straße", "straße"),
        ("नमस\u094dत\u0947", "नमस\u094dत\u0947"),
        (PERSIAN, PERSIAN),
        ("\u200cword\u200d", "word"),
        ("abc\u202edef", "abc-def"),
        ("\u2066inner\u2069", "inner"),
        ("keycap 1\ufe0f\u20e3 wave \U0001f44b", "keycap-1-wave"),
        ('a<b>c:d"e/f\\g|h?i*j', "a-b-c-d-e-f-g-h-i-j"),
        ("  --tidy--  ", "tidy"),
    ],
)
def test_names_keep_letters_marks_and_joiners_and_nothing_else(
    title: str, expected: str
) -> None:
    assert file_stem(title, "grok") == expected


@pytest.mark.parametrize(
    "title", [None, "", "\U0001f44b\U0001f3fd", "!!! ???", "\u202e"]
)
def test_a_title_with_nothing_nameable_falls_back_to_the_provider(
    title: str | None,
) -> None:
    assert file_stem(title, "grok") == "grok"


@pytest.mark.parametrize("title", ["CON", "prn", "Aux", "nul", "COM1", "lpt9", "com¹"])
def test_a_windows_device_name_is_never_used_alone(title: str) -> None:
    assert file_stem(title, "grok") == f"{title.lower()}-grok"


def test_a_name_that_merely_begins_with_a_device_name_is_left_alone() -> None:
    assert file_stem("Console", "grok") == "console"


def test_a_long_title_is_cut_to_the_character_budget() -> None:
    assert file_stem("a" * 100, "grok") == "a" * MAX_CHARACTERS


def test_a_long_title_outside_the_basic_plane_is_cut_to_the_byte_budget() -> None:
    """Adlam letters take four bytes each, so the byte cap binds first."""
    stem = file_stem("\U0001e900" * 100, "grok")
    assert len(stem.encode("utf-8")) <= MAX_BYTES
    assert stem == "\U0001e922" * (MAX_BYTES // 4)


def test_a_cut_never_strands_a_letter_without_its_mark() -> None:
    """Cutting between e and its accent would leave a different letter."""
    title = "x" * (MAX_CHARACTERS - 1) + "e\u0301\u0323"
    assert file_stem(title, "grok") == "x" * (MAX_CHARACTERS - 1)


def test_a_new_file_is_numbered_rather_than_replacing_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    first = write_new("chat", "md", "one")
    second = write_new("chat", "md", "two")
    third = write_new("chat", "md", "three")

    assert [str(first), str(second), str(third)] == [
        "chat.md",
        "chat-2.md",
        "chat-3.md",
    ]
    assert (tmp_path / "chat.md").read_text(encoding="utf-8") == "one"


def test_text_that_cannot_be_written_creates_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    chosen = tmp_path / "chosen.md"

    with pytest.raises(OutputError, match="nothing was written"):
        write_new("chat", "md", "half \ud83d")
    with pytest.raises(OutputError):
        write_to(chosen, "half \ud83d")

    assert list(tmp_path.iterdir()) == []


def test_a_stream_in_a_legacy_encoding_is_switched_to_utf8() -> None:
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", errors="backslashreplace")

    use_utf8(stream)
    stream.write("مرحبا 你好")
    stream.flush()

    assert raw.getvalue().decode("utf-8") == "مرحبا 你好"
    assert stream.errors == "backslashreplace"


def test_a_stream_already_writing_utf8_or_not_a_file_is_left_alone() -> None:
    utf8 = io.TextIOWrapper(io.BytesIO(), encoding="UTF8", errors="strict")
    text = io.StringIO()

    use_utf8(utf8, text)

    assert utf8.encoding == "UTF8"
    assert text.getvalue() == ""
