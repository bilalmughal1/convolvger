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

Not covered: no turn in this conversation drew citations or ran a web
search, so the live shape of those fields goes unchecked. Fixture tests
cover parsing them; they would not notice Google reshaping them. Adding
a turn that makes Gemini search would close that gap.
"""

from itertools import pairwise

import pytest

from convolvger.core.models import MessageRole, TextBlock
from convolvger.core.results import ParseResult
from convolvger.providers.gemini import _fetch, _parse, _urls

pytestmark = pytest.mark.contract

SHARE_URL = "https://share.gemini.google/x1sCSRHxplUf"
TITLE = "The History of Time Measurement"
CONVERSATION_ID = "c_4d932369af28bdfc"
ANSWER_IDS = ("r_68166d122d5ab59d", "r_949eee48b63efd39", "r_eda7505ff37516d2")


@pytest.fixture(scope="module")
def live() -> ParseResult:
    """Fetched once: three exchanges do not need fetching four times."""
    return _parse.parse(_fetch.fetch(SHARE_URL))


def test_the_shortened_link_still_resolves_to_a_conversation(live: ParseResult) -> None:
    """The shortener's token is not the id, so this exercises the redirect."""
    assert _urls.share_id(SHARE_URL) is None
    assert live.conversation.title == TITLE
    assert live.conversation.id == CONVERSATION_ID


def test_every_turn_still_arrives_as_a_prompt_and_an_answer(live: ParseResult) -> None:
    messages = live.conversation.messages
    assert len(messages) == 6
    assert [message.role for message in messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ] * 3
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
