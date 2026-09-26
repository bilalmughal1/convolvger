"""Does Grok still serve what this version knows how to read?

Every other Grok test uses a fixture or a mock, so all of them would
keep passing if the payload were reshaped tomorrow. These call the live
provider so that a change is discovered here rather than by a user.

Excluded from the default suite by the ``contract`` marker: running the
tests should never depend on a network, on someone else's service being
up, or on a share link staying published. A scheduled workflow selects
them.

What is asserted is structure, not prose: the keys this version reads,
the roles senders fold into, the parent chain, and that no finding
appears beyond the one a thinking answer raises by design. A new key in
the payload fails here too, because it is the first sign of a reshape.
"""

import json
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from convolvger.core.models import MessageRole
from convolvger.core.results import ParseResult
from convolvger.core.source import RawSource
from convolvger.providers.grok import _fetch, _parse, _urls
from convolvger.renderers import render_markdown

SHARE_URL = (
    "https://grok.com/share/bGVnYWN5LWNvcHk_500a8acf-1f98-4c9f-a20e-81a80dc352af"
)
FIXTURE = Path(__file__).parent.parent / "fixtures" / "grok" / "share-minimal.json"

pytestmark = pytest.mark.contract

READ_ENVELOPE = {"conversation", "responses"}
READ_CONVERSATION = {"conversationId", "title", "createTime", "modifyTime"}
READ_RESPONSE = {"responseId", "sender", "message", "createTime", "parentResponseId"}
KNOWN_FINDINGS = {("unmodelled_content_type", "steps preserved in provider_metadata")}
"""The one finding a healthy share is expected to raise: a thinking
answer's trace is kept and flagged by design."""


@pytest.fixture(scope="module")
def source() -> RawSource:
    """Fetched once: the checks below do not need the provider asked twice."""
    return _fetch.fetch(SHARE_URL)


@pytest.fixture(scope="module")
def payload(source: RawSource) -> dict[str, Any]:
    loaded = json.loads(source.content)
    is_object = isinstance(loaded, dict)
    assert is_object, "payload is no longer a JSON object"
    result: dict[str, Any] = loaded
    return result


@pytest.fixture(scope="module")
def parsed(source: RawSource) -> ParseResult:
    return _parse.parse(source)


def _response_keys(payload: dict[str, Any]) -> set[str]:
    return set().union(*(set(item) for item in payload["responses"]))


def test_the_link_is_still_one_this_version_recognises() -> None:
    recognised = _urls.is_share_url(SHARE_URL)
    assert recognised, "the contract link is not a grok.com/share link"


def test_the_fields_this_version_reads_are_still_served(
    payload: dict[str, Any],
) -> None:
    missing = sorted(READ_ENVELOPE - set(payload))
    assert not missing, missing
    missing = sorted(READ_CONVERSATION - set(payload["conversation"]))
    assert not missing, missing
    count = len(payload["responses"])
    assert count > 0, "the share now answers with no responses"
    missing = sorted(
        set().union(*(READ_RESPONSE - set(item) for item in payload["responses"]))
    )
    assert not missing, missing


def test_no_field_has_appeared_that_the_fixture_does_not_know(
    payload: dict[str, Any],
) -> None:
    """A new key is the first sign of a reshape, and names only a key."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    new = sorted(set(payload) - set(fixture))
    assert not new, new
    new = sorted(set(payload["conversation"]) - set(fixture["conversation"]))
    assert not new, new
    new = sorted(_response_keys(payload) - _response_keys(fixture))
    assert not new, new


def test_every_sender_still_folds_into_a_known_role(parsed: ParseResult) -> None:
    known = {MessageRole.USER, MessageRole.ASSISTANT}
    unknown = sum(1 for m in parsed.conversation.messages if m.role not in known)
    assert unknown == 0


def test_every_response_still_carries_text(parsed: ParseResult) -> None:
    empty = sum(1 for message in parsed.conversation.messages if not message.content)
    assert empty == 0


def test_each_response_still_links_back_to_the_one_before(parsed: ParseResult) -> None:
    messages = parsed.conversation.messages
    broken = sum(
        1
        for earlier, later in pairwise(messages)
        if later.provider_metadata.get("parentResponseId") != earlier.id
    )
    assert broken == 0


def test_inline_markup_still_leaves_the_document(parsed: ParseResult) -> None:
    document = render_markdown(parsed.conversation, findings=parsed.findings)
    leaked = "<grok:" in document
    assert not leaked, "inline grok markup reached the Markdown export"


def test_the_share_still_parses_without_unexpected_findings(
    parsed: ParseResult,
) -> None:
    """Codes and messages name shapes, not content, so they are safe to print."""
    unexpected = sorted({(f.code, f.message) for f in parsed.findings} - KNOWN_FINDINGS)
    assert not unexpected, unexpected
