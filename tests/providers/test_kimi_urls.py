import pytest

from convolvger.providers.kimi import _urls

SHARE_ID = "00000000-0000-4000-8000-000000000002"


@pytest.mark.parametrize(
    ("url", "api"),
    [
        (f"https://www.kimi.ai/share/{SHARE_ID}", "https://www.kimi.ai"),
        (f"https://kimi.ai/share/{SHARE_ID}", "https://www.kimi.ai"),
        (f"https://www.kimi.com/share/{SHARE_ID}", "https://www.kimi.com"),
        (f"https://kimi.com/share/{SHARE_ID}", "https://www.kimi.com"),
        (f"https://kimi.moonshot.cn/share/{SHARE_ID}", "https://www.kimi.com"),
    ],
)
def test_every_observed_host_is_recognised_and_asked_on_its_own_service(
    url: str, api: str
) -> None:
    """The old Moonshot host redirects to kimi.com, so it is asked there."""
    assert _urls.share_id(url) == SHARE_ID
    assert _urls.api_url(url) == f"{api}{_urls.SERVICE_PATH}"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.kimi.ai/share/{SHARE_ID}/",
        f"https://www.kimi.ai/share/{SHARE_ID}?from=copy#top",
        f"https://WWW.KIMI.AI/share/{SHARE_ID}",
        f"https://www.kimi.ai./share/{SHARE_ID}",
    ],
)
def test_trailing_slash_query_fragment_and_case_do_not_affect_the_id(url: str) -> None:
    assert _urls.share_id(url) == SHARE_ID


@pytest.mark.parametrize(
    "url",
    [
        f"http://www.kimi.ai/share/{SHARE_ID}",
        f"https://www.kimi.ai/chat/{SHARE_ID}",
        f"https://www.kimi.ai/share/en-US/{SHARE_ID}",
        "https://www.kimi.ai/share",
        f"https://kimi.example.com/share/{SHARE_ID}",
        f"https://grok.com/share/{SHARE_ID}",
    ],
)
def test_rejects_urls_that_are_not_share_links(url: str) -> None:
    """A language-prefixed path was measured redirecting home, not to a share."""
    assert _urls.is_share_url(url) is False
    assert _urls.share_id(url) is None
    assert _urls.api_url(url) is None


def test_a_malformed_url_is_rejected_rather_than_raising() -> None:
    assert _urls.is_share_url("https://[") is False
