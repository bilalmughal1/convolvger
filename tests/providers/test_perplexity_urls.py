import re

import pytest

from convolvger.providers.perplexity import _urls

SHARE_ID = "00000000-0000-4000-8000-000000000001"
LINK = f"https://www.perplexity.ai/search/{SHARE_ID}"


@pytest.mark.parametrize(
    "url",
    [
        LINK,
        f"https://perplexity.ai/search/{SHARE_ID}",
        f"{LINK}/",
        f"{LINK}?s=c",
        f"{LINK}#top",
        f"HTTPS://WWW.PERPLEXITY.AI/search/{SHARE_ID}",
    ],
)
def test_the_measured_form_carries_the_id(url: str) -> None:
    assert _urls.is_share_url(url)
    assert _urls.share_id(url) == SHARE_ID


@pytest.mark.parametrize(
    "url",
    [
        f"http://www.perplexity.ai/search/{SHARE_ID}",
        "https://www.perplexity.ai/search",
        "https://www.perplexity.ai/discover",
        f"https://www.perplexity.ai/page/{SHARE_ID}",
        f"https://www.perplexity.ai/search/{SHARE_ID}/more",
        f"https://example.com/search/{SHARE_ID}",
        "not a url",
    ],
)
def test_other_urls_are_not_share_links(url: str) -> None:
    assert not _urls.is_share_url(url)
    assert _urls.share_id(url) is None


def test_the_capture_rule_finds_the_id_on_the_page_it_was_measured_on() -> None:
    rule = _urls.CAPTURE
    assert rule.hosts == frozenset({"www.perplexity.ai"})
    match = re.match(rule.path, f"/search/{SHARE_ID}")
    assert match is not None
    assert match.group(1) == SHARE_ID
    assert re.match(rule.path, "/discover") is None


def test_the_thread_is_read_where_the_page_read_it() -> None:
    """The query is copied whole from the page's own request."""
    api = _urls.CAPTURE.api.format(share_id=SHARE_ID)
    assert api.startswith(f"https://www.perplexity.ai/rest/thread/{SHARE_ID}?")
    assert "limit=20" in api
    assert "with_schematized_response=true" in api
    assert "%" not in api
