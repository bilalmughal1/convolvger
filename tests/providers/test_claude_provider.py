"""The Claude provider adapter: what it claims, and what it cannot do."""

import json
from pathlib import Path

import pytest

from convolvger.core.errors import ConvolvgerError
from convolvger.core.results import ParseError
from convolvger.core.source import RawSource
from convolvger.providers.base import FetchUnsupportedError
from convolvger.providers.claude import ClaudeProvider

FIXTURE = Path(__file__).parent.parent / "fixtures" / "claude" / "share-minimal.json"
SHARE_URL = "https://claude.ai/share/00000000-0000-0000-0000-000000000000"


def test_the_provider_is_named_after_its_provider() -> None:
    assert ClaudeProvider().name == "claude"


def test_it_claims_claude_share_links_and_nothing_else() -> None:
    provider = ClaudeProvider()

    assert provider.matches(SHARE_URL)
    assert not provider.matches("https://chatgpt.com/share/abc")
    assert not provider.matches("https://claude.ai/chat/abc")


def test_fetching_is_refused_rather_than_attempted() -> None:
    with pytest.raises(FetchUnsupportedError):
        ClaudeProvider().fetch(SHARE_URL)


def test_the_refusal_says_how_to_supply_the_snapshot_instead() -> None:
    """A dead end would be useless; --from-file already exists."""
    with pytest.raises(FetchUnsupportedError, match="--from-file"):
        ClaudeProvider().fetch(SHARE_URL)


def test_the_refusal_is_reported_as_an_ordinary_failure() -> None:
    """The CLI catches ConvolvgerError, so no capability check is needed."""
    with pytest.raises(ConvolvgerError):
        ClaudeProvider().fetch(SHARE_URL)


def test_parsing_is_delegated_to_the_snapshot_parser() -> None:
    result = ClaudeProvider().parse(
        RawSource(url=SHARE_URL, content=FIXTURE.read_text(encoding="utf-8"))
    )

    assert result.conversation.provider == "claude"
    assert len(result.conversation.messages) == 2
    assert {item.code for item in result.findings} == {
        "attachment_withheld",
        "tool_result_has_no_content",
    }


def test_a_snapshot_that_is_not_a_claude_snapshot_is_refused() -> None:
    with pytest.raises(ParseError):
        ClaudeProvider().parse(
            RawSource(url=SHARE_URL, content=json.dumps({"mapping": {}}))
        )
