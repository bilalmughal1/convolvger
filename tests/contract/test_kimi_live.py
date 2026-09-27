"""Does Kimi still serve what this version knows how to read?

Calls the live provider with a throwaway share made for the purpose, so
a reshaped payload is found here rather than by a user. Excluded from the
default suite by the ``contract`` marker; a scheduled workflow selects
them.

What is asserted is structure, not prose. The sharer's name is served in
the payload; it is never asserted or printed here, only checked to stay
out of the Markdown.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from convolvger.core.results import ParseResult
from convolvger.core.source import RawSource
from convolvger.providers.kimi import _fetch, _parse
from convolvger.renderers import render_markdown

pytestmark = pytest.mark.contract

SHARE_URL = "https://www.kimi.ai/share/1a0e2ed0-0dd2-85a9-8000-0000b8c868a2"
TITLE = "Web vs App Tech"
FIXTURE = Path(__file__).parent.parent / "fixtures" / "kimi" / "share-minimal.json"
KNOWN_FINDINGS = {
    "think block preserved in provider_metadata",
    "tool block preserved in provider_metadata",
}


@pytest.fixture(scope="module")
def source() -> RawSource:
    return _fetch.fetch(SHARE_URL)


@pytest.fixture(scope="module")
def live(source: RawSource) -> ParseResult:
    return _parse.parse(source)


def _keys(payload: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    share = payload["share"]
    blocks = [b for m in share["messages"] for b in m["blocks"]]
    return (
        set(share),
        set().union(*(set(m) for m in share["messages"])),
        set().union(*(set(b) for b in blocks)),
    )


def test_the_share_still_alternates_three_questions_and_answers(
    live: ParseResult,
) -> None:
    assert live.conversation.title == TITLE
    roles = [message.role.value for message in live.conversation.messages]
    assert roles == ["user", "assistant"] * 3
    assert all(message.content for message in live.conversation.messages)


def test_the_searching_answer_still_cites_spans_of_its_own_text(
    live: ParseResult,
) -> None:
    last = live.conversation.messages[-1]
    references = last.provider_metadata["references"]
    assert references
    text = "".join(getattr(block, "text", "") for block in last.content)
    unmatched = sum(1 for ref in references if ref.get("matchedText") not in text)
    assert unmatched == 0


def test_the_sharer_is_kept_but_never_rendered(live: ParseResult) -> None:
    creator = live.conversation.provider_metadata.get("creator")
    assert isinstance(creator, dict)
    document = render_markdown(live.conversation, findings=live.findings)
    leaked = isinstance(creator.get("name"), str) and creator["name"] in document
    assert not leaked, "the sharer's name reached the Markdown"


def test_no_field_has_appeared_that_the_fixture_does_not_know(
    source: RawSource,
) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for live_set, known in zip(
        _keys(json.loads(source.content)), _keys(fixture), strict=True
    ):
        new = sorted(live_set - known)
        assert not new, new


def test_the_share_still_parses_without_unexpected_findings(live: ParseResult) -> None:
    unexpected = sorted({f.message for f in live.findings} - KNOWN_FINDINGS)
    assert not unexpected, unexpected
