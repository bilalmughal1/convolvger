"""Does Gemini still serve what this version knows how to read?

Every other Gemini test uses a fixture or a mock, which means all of
them would keep passing if Google changed the format tomorrow. These
call the live provider so that a reshaped payload is discovered here
rather than by a user whose archive silently stops working.

Excluded from the default suite by the ``contract`` marker: running the
tests should never depend on a network, on someone else's service being
up, or on a share link staying published. A scheduled workflow selects
them.

What is asserted is structure, not prose. Answer text and response size
are deliberately not pinned -- two identical requests were measured
returning bodies of different lengths, so a size assertion would raise
false alarms, and a scheduled job that cries wolf is one nobody reads.

The last two turns ran a web search, so the live shape of citations
and search queries is checked too. Counts are not pinned: how many
sources a search returns is Google's choice, not a format. What is
pinned is where the fields sit in each citation -- the URL and title of
its source, the span of the answer it supports, and the source id the
block tree references -- since a rule about which citations contributed
to an answer would rely on exactly those.
"""

import re
from itertools import pairwise

import pytest

from convolvger.core.models import MessageRole, TextBlock
from convolvger.core.results import ParseResult
from convolvger.providers.gemini import _fetch, _parse, _urls
from convolvger.providers.gemini._parse import _at

pytestmark = pytest.mark.contract

SHARE_URL = "https://share.gemini.google/UDbzOo2CK3tf"
TITLE = "The History of Time Measurement"
CONVERSATION_ID = "c_4d932369af28bdfc"
ANSWER_IDS = (
    "r_68166d122d5ab59d",
    "r_949eee48b63efd39",
    "r_eda7505ff37516d2",
    "r_2a7cccf729985832",
    "r_a0e1406869e716ed",
)
SEARCHED = (3, 4)
"""Answers, by position, whose turn ran a web search."""
UNSEARCHED = (0, 1, 2)


@pytest.fixture(scope="module")
def live() -> ParseResult:
    """Fetched once: five exchanges do not need fetching once per test."""
    return _parse.parse(_fetch.fetch(SHARE_URL))


def test_the_shortened_link_still_resolves_to_a_conversation(live: ParseResult) -> None:
    """The shortener's token is not the id, so this exercises the redirect."""
    assert _urls.share_id(SHARE_URL) is None
    assert live.conversation.title == TITLE
    assert live.conversation.id == CONVERSATION_ID


def test_every_turn_still_arrives_as_a_prompt_and_an_answer(live: ParseResult) -> None:
    messages = live.conversation.messages
    assert len(messages) == 10
    assert [message.role for message in messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ] * 5
    assert [message.id for message in messages[1::2]] == list(ANSWER_IDS)


def test_each_answer_still_links_back_to_the_one_before(live: ParseResult) -> None:
    """The chain lives only between turns, and is what a reshape would break."""
    answers = live.conversation.messages[1::2]
    assert "parent" not in answers[0].provider_metadata

    for earlier, later in pairwise(answers):
        parent = later.provider_metadata["parent"]
        assert parent[0] == CONVERSATION_ID
        assert parent[1] == earlier.id


def test_answers_still_arrive_as_markdown(live: ParseResult) -> None:
    """The flat string is authoritative; a table proves it still carries one."""
    last = live.conversation.messages[-1].content[0]
    assert isinstance(last, TextBlock)
    assert "|" in last.text


def test_the_conversation_still_parses_without_findings(live: ParseResult) -> None:
    """A finding here means Gemini served something this version cannot model."""
    assert live.findings == []


def test_a_searching_turn_still_yields_citations(live: ParseResult) -> None:
    """Each citation still names a source, its span and its source id."""
    answers = live.conversation.messages[1::2]
    for index in SEARCHED:
        citations = answers[index].provider_metadata.get("citations")
        assert isinstance(citations, list)
        assert citations
        for citation in citations:
            url = _at(citation, 2, 0, 0)
            title = _at(citation, 2, 0, 1)
            span = _at(citation, 0, 0)
            source_id = _at(citation, 3)
            assert isinstance(url, str)
            assert re.match(r"https?://", url)
            assert isinstance(title, str)
            assert title
            assert isinstance(span, str)
            assert span
            assert isinstance(source_id, str)
            assert source_id.startswith("sp")


def test_a_searching_turn_still_yields_its_queries(live: ParseResult) -> None:
    answers = live.conversation.messages[1::2]
    for index in SEARCHED:
        queries = answers[index].provider_metadata.get("search_queries")
        assert isinstance(queries, list)
        assert queries
        assert all(isinstance(query, str) and query for query in queries)


def test_a_turn_without_a_search_still_carries_neither(live: ParseResult) -> None:
    """Measured: such a turn serves None for both, so neither is kept."""
    answers = live.conversation.messages[1::2]
    for index in UNSEARCHED:
        assert "citations" not in answers[index].provider_metadata
        assert "search_queries" not in answers[index].provider_metadata
