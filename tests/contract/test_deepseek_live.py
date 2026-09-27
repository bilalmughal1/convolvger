"""Does DeepSeek still serve what this version knows how to read?

Every other DeepSeek test uses a fixture or a mock, so all of them would
keep passing if the payload were reshaped tomorrow. These call the live
provider with a throwaway share made for the purpose, so a change is
found here rather than by a user.

Excluded from the default suite by the ``contract`` marker; a scheduled
workflow selects them. What is asserted is structure, not prose: the
roles, the search a turn ran and the citations that point into it, and
that no key has appeared that the committed fixture does not know.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from convolvger.core.results import ParseResult
from convolvger.core.source import RawSource
from convolvger.providers.deepseek import _fetch, _parse
from convolvger.renderers import render_markdown

pytestmark = pytest.mark.contract

SHARE_URL = "https://chat.deepseek.com/share/7czjusfjfoqwjqowr0"
FIXTURE = Path(__file__).parent.parent / "fixtures" / "deepseek" / "share-minimal.json"
SEARCHED = (1, 9)
"""Messages, by position, whose turn ran a web search."""


@pytest.fixture(scope="module")
def source() -> RawSource:
    return _fetch.fetch(SHARE_URL)


@pytest.fixture(scope="module")
def live(source: RawSource) -> ParseResult:
    return _parse.parse(source)


def _keys(payload: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    messages = payload["data"]["biz_data"]["messages"]
    fragments = [f for m in messages for f in m["fragments"]]
    return (
        set().union(*(set(m) for m in messages)),
        set().union(*(set(f) for f in fragments)),
        {f["type"] for f in fragments},
    )


def test_the_share_still_alternates_ten_questions_and_answers(
    live: ParseResult,
) -> None:
    roles = [message.role.value for message in live.conversation.messages]
    assert roles == ["user", "assistant"] * 5


def test_the_title_is_still_the_generic_one(live: ParseResult) -> None:
    assert live.conversation.title == "Shared Conversation"


def test_a_searching_turn_still_yields_results_its_citations_resolve_to(
    live: ParseResult,
) -> None:
    for position in SEARCHED:
        extras = live.conversation.messages[position].provider_metadata[
            "fragment_extras"
        ]
        searches = [f for f in extras.values() if f.get("type") == "SEARCH"]
        assert searches
        results = searches[0]["results"]
        assert results
        assert all(isinstance(r.get("cite_index"), int) for r in results)
        assert all(str(r.get("url", "")).startswith("http") for r in results)
        answers = [f for f in extras.values() if f.get("type") == "RESPONSE"]
        assert "[citation:" in answers[0].get("content", "")


def test_no_citation_marker_reaches_the_document(live: ParseResult) -> None:
    document = render_markdown(live.conversation, findings=live.findings)
    assert "[citation:" not in document


def test_no_field_has_appeared_that_the_fixture_does_not_know(
    source: RawSource,
) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    live_keys = _keys(json.loads(source.content))
    for live_set, known in zip(live_keys, _keys(fixture), strict=True):
        new = sorted(live_set - known)
        assert not new, new


def test_the_share_still_parses_without_findings(live: ParseResult) -> None:
    assert live.findings == []
