import pytest

from convolvger.providers.qwen import _urls

SHARE_ID = "00000000-0000-4000-8000-000000000001"
LINK = f"https://chat.qwen.ai/s/{SHARE_ID}?fev=0.3.11"


@pytest.mark.parametrize(
    ("url", "host"),
    [
        (LINK, "chat.qwen.ai"),
        (f"https://chat.qwen.ai/s/{SHARE_ID}", "chat.qwen.ai"),
        (f"https://chat.qwenlm.ai/s/{SHARE_ID}", "chat.qwenlm.ai"),
        (f"https://chat.qwen.ai/s/{SHARE_ID}/#top", "chat.qwen.ai"),
        (f"https://CHAT.QWEN.AI/s/{SHARE_ID}", "chat.qwen.ai"),
    ],
)
def test_every_observed_form_carries_the_id_and_is_asked_on_its_own_host(
    url: str, host: str
) -> None:
    """The share dialog's fev query is disposable: the id is the path."""
    assert _urls.share_id(url) == SHARE_ID
    assert _urls.api_url(url) == f"https://{host}/api/v2/chats/share/{SHARE_ID}"


@pytest.mark.parametrize(
    "url",
    [
        f"http://chat.qwen.ai/s/{SHARE_ID}",
        f"https://chat.qwen.ai/share/{SHARE_ID}",
        f"https://chat.qwen.ai/c/{SHARE_ID}",
        f"https://qwen.ai/s/{SHARE_ID}",
        "https://chat.qwen.ai/s",
        f"https://chat.qwen.ai/s/{SHARE_ID}/extra",
    ],
)
def test_rejects_urls_that_are_not_share_links(url: str) -> None:
    """The app answers every path with a 200 shell, so only /s/ is trusted."""
    assert _urls.is_share_url(url) is False
    assert _urls.api_url(url) is None


def test_a_malformed_url_is_rejected_rather_than_raising() -> None:
    assert _urls.is_share_url("https://[") is False
