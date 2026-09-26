import pytest

from convolvger.providers.grok import _urls

SHARE_ID = "bGVnYWN5_00000000-0000-4000-8000-000000000001"
CANONICAL = f"https://grok.com/share/{SHARE_ID}"


@pytest.mark.parametrize(
    "identifier",
    [
        SHARE_ID,
        "bGVnYWN5LWNvcHk_00000000-0000-4000-8000-000000000002",
        "c2hhcmQtMg_00000000-0000-4000-8000-000000000003",
    ],
)
def test_every_observed_prefix_is_kept_as_part_of_an_opaque_id(identifier: str) -> None:
    """legacy, legacy-copy and shard-2 were all seen; none is decoded."""
    assert _urls.share_id(f"https://grok.com/share/{identifier}") == identifier


def test_an_unfamiliar_prefix_is_not_refused() -> None:
    """The provider judges an id; a new prefix must not look foreign here."""
    identifier = "bmV3LXByZWZpeA_00000000-0000-4000-8000-000000000004"
    assert _urls.share_id(f"https://grok.com/share/{identifier}") == identifier


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.grok.com/share/{SHARE_ID}",
        f"https://grok.com./share/{SHARE_ID}",
        f"https://grok.com/share/{SHARE_ID}/",
        f"https://grok.com/share/{SHARE_ID}?utm_source=x#top",
        f"HTTPS://GROK.COM/share/{SHARE_ID}",
    ],
)
def test_host_trailing_slash_query_and_fragment_do_not_affect_the_id(url: str) -> None:
    assert _urls.share_id(url) == SHARE_ID


def test_the_endpoint_is_keyed_on_the_whole_id() -> None:
    assert _urls.api_url(CANONICAL) == (
        f"https://grok.com/rest/app-chat/share_links/{SHARE_ID}"
    )


@pytest.mark.parametrize(
    "url",
    [
        f"http://grok.com/share/{SHARE_ID}",
        f"https://grok.com/chat/{SHARE_ID}",
        "https://grok.com/share",
        f"https://grok.com/share/{SHARE_ID}/extra",
        f"https://x.com/i/grok/share/{SHARE_ID}",
        f"https://grok.example.com/share/{SHARE_ID}",
        f"https://chatgpt.com/share/{SHARE_ID}",
    ],
)
def test_rejects_urls_that_are_not_share_links(url: str) -> None:
    assert _urls.is_share_url(url) is False
    assert _urls.share_id(url) is None
    assert _urls.api_url(url) is None


def test_a_malformed_url_is_rejected_rather_than_raising() -> None:
    assert _urls.is_share_url("https://[") is False
