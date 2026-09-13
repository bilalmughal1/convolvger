import pytest

from convolvger.providers.claude._urls import is_share_url

SHARE_ID = "f2f59cb2-8857-4808-a650-2712e80290fd"


@pytest.mark.parametrize(
    "url",
    [
        f"https://claude.ai/share/{SHARE_ID}",
        f"https://claude.ai/share/{SHARE_ID}/",
        f"https://www.claude.ai/share/{SHARE_ID}",
        f"https://CLAUDE.AI/share/{SHARE_ID}",
        f"HTTPS://claude.ai/share/{SHARE_ID}",
        f"https://claude.ai./share/{SHARE_ID}",
        f"https://claude.ai/share/{SHARE_ID}?utm_source=x",
        f"https://claude.ai/share/{SHARE_ID}#top",
        "https://claude.ai/share/not-a-uuid-at-all",
    ],
)
def test_accepts_share_urls(url: str) -> None:
    assert is_share_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        f"https://claude.ai.evil.test/share/{SHARE_ID}",
        f"https://evil.test/claude.ai/share/{SHARE_ID}",
        f"https://notclaude.ai/share/{SHARE_ID}",
        f"http://claude.ai/share/{SHARE_ID}",
        f"https://claude.ai/share/{SHARE_ID}/continue",
        f"https://claude.ai/chat/{SHARE_ID}",
        f"https://claude.ai/api/chat_snapshots/{SHARE_ID}",
        f"https://chatgpt.com/share/{SHARE_ID}",
        "https://claude.ai/share/",
        "https://claude.ai/share",
        "https://claude.ai/",
        "not a url",
        "",
    ],
)
def test_rejects_other_urls(url: str) -> None:
    assert is_share_url(url) is False
