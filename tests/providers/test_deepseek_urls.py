import pytest

from convolvger.providers.deepseek import _urls

SHARE_ID = "0example0share0id"
LINK = f"https://chat.deepseek.com/share/{SHARE_ID}"


def test_the_share_form_carries_the_id() -> None:
    assert _urls.share_id(LINK) == SHARE_ID


@pytest.mark.parametrize(
    "url",
    [
        f"{LINK}/",
        f"{LINK}?from=copy#top",
        LINK.replace("chat.", "CHAT."),
        f"{LINK}".replace(".com", ".com."),
    ],
)
def test_trailing_slash_query_fragment_and_case_do_not_affect_the_id(url: str) -> None:
    assert _urls.share_id(url) == SHARE_ID


def test_the_data_endpoint_is_asked_rather_than_the_page() -> None:
    """The page refused every client tried; the endpoint answered."""
    assert _urls.api_url(LINK) == (
        f"https://chat.deepseek.com/api/v0/share/content?share_id={SHARE_ID}"
    )


def test_an_id_is_escaped_into_the_query() -> None:
    assert _urls.api_url("https://chat.deepseek.com/share/a&b=c") == (
        "https://chat.deepseek.com/api/v0/share/content?share_id=a%26b%3Dc"
    )


@pytest.mark.parametrize(
    "url",
    [
        f"http://chat.deepseek.com/share/{SHARE_ID}",
        f"https://deepseek.com/share/{SHARE_ID}",
        f"https://www.deepseek.com/share/{SHARE_ID}",
        f"https://chat.deepseek.com/a/chat/s/{SHARE_ID}",
        "https://chat.deepseek.com/share",
        f"https://chat.deepseek.com/share/{SHARE_ID}/extra",
    ],
)
def test_rejects_urls_that_are_not_share_links(url: str) -> None:
    """deepseek.com and www.deepseek.com were measured answering 404."""
    assert _urls.is_share_url(url) is False
    assert _urls.api_url(url) is None


def test_a_malformed_url_is_rejected_rather_than_raising() -> None:
    assert _urls.is_share_url("https://[") is False
