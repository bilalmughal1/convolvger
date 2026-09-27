"""Does Qwen still serve what this version knows how to read?

Calls the live provider with a throwaway share made for the purpose, so
a reshaped payload is found here rather than by a user. Excluded from the
default suite by the ``contract`` marker; a scheduled workflow selects
them.

What is asserted is structure, not prose: the tree and its flat copy
agreeing, the answer arriving in ``content_list`` rather than
``content``, every citation resolving against the searches, and that no
key has appeared that the committed fixture does not know.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from convolvger.core.results import ParseResult
from convolvger.core.source import RawSource
from convolvger.providers.qwen import _fetch, _parse
from convolvger.renderers import render_markdown

pytestmark = pytest.mark.contract

SHARE_URL = "https://chat.qwen.ai/s/b5f54f06-e87c-4eed-9128-6cc23e7b0697?fev=0.3.11"
TITLE = "Copper vs Aluminum Cookware"
FIXTURE = Path(__file__).parent.parent / "fixtures" / "qwen" / "share-minimal.json"


@pytest.fixture(scope="module")
def source() -> RawSource:
    return _fetch.fetch(SHARE_URL)


@pytest.fixture(scope="module")
def live(source: RawSource) -> ParseResult:
    return _parse.parse(source)


def _keys(payload: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    nodes = list(payload["data"]["chat"]["history"]["messages"].values())
    parts = [p for n in nodes for p in n.get("content_list", [])]
    return (
        set(payload["data"]),
        set().union(*(set(n) for n in nodes)),
        set().union(*(set(p) for p in parts)),
    )


def test_the_share_still_alternates_two_questions_and_answers(
    live: ParseResult,
) -> None:
    assert live.conversation.title == TITLE
    roles = [message.role.value for message in live.conversation.messages]
    assert roles == ["user", "assistant"] * 2
    assert all(
        message.active and message.content for message in live.conversation.messages
    )


def test_the_flat_copy_still_agrees_with_the_tree(live: ParseResult) -> None:
    assert "messages" not in live.conversation.provider_metadata["chat"]


def test_every_answer_still_searches_and_every_citation_resolves(
    live: ParseResult,
) -> None:
    for message in live.conversation.messages[1::2]:
        parts = message.provider_metadata["part_extras"].values()
        phases = [part.get("phase") for part in parts]
        assert "web_search" in phases
        assert "answer" in phases
    unresolved = [f for f in live.findings if "names no search result" in f.message]
    assert not unresolved
    document = render_markdown(live.conversation, findings=live.findings)
    assert "[[" not in document


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
    unexpected = sorted(
        {f.message for f in live.findings}
        - {"thinking_summary part preserved in provider_metadata"}
    )
    assert not unexpected, unexpected
