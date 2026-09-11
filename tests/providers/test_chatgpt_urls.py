import pytest

from convolvger.providers.chatgpt._urls import is_share_url

SHARE_ID = "6aa3f5a2-00a4-83eb-8d18-3b2266aac2e6"


@pytest.mark.parametrize(
    "url",
    [
        f"https://chatgpt.com/share/{SHARE_ID}",
        f"https://chatgpt.com/share/{SHARE_ID}/",
        f"https://www.chatgpt.com/share/{SHARE_ID}",
        f"https://chat.openai.com/share/{SHARE_ID}",
        f"https://www.chat.openai.com/share/{SHARE_ID}",
        f"https://CHATGPT.COM/share/{SHARE_ID}",
        f"HTTPS://chatgpt.com/share/{SHARE_ID}",
        f"https://chatgpt.com./share/{SHARE_ID}",
        f"https://chatgpt.com/share/{SHARE_ID}?utm_source=x",
        f"https://chatgpt.com/share/{SHARE_ID}#top",
        "https://chatgpt.com/share/not-a-uuid-at-all",
        "https://chatgpt.com/share/69b1c492-1540-8006-aa29-ee2e0a831385",
    ],
)
def test_accepts_share_urls(url: str) -> None:
    assert is_share_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        f"https://chatgpt.com.evil.test/share/{SHARE_ID}",
        f"https://evil.test/chatgpt.com/share/{SHARE_ID}",
        f"https://notchatgpt.com/share/{SHARE_ID}",
        f"http://chatgpt.com/share/{SHARE_ID}",
        f"https://chatgpt.com/share/{SHARE_ID}/continue",
        f"https://chatgpt.com/c/{SHARE_ID}",
        f"https://claude.ai/share/{SHARE_ID}",
        "https://chatgpt.com/share/",
        "https://chatgpt.com/share",
        "https://chatgpt.com/",
        "not a url",
        "",
    ],
)
def test_rejects_other_urls(url: str) -> None:
    assert is_share_url(url) is False
