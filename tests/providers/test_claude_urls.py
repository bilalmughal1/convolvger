import pytest

from convolvger.providers.claude._urls import is_share_url, share_id, snapshot_url

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


def test_the_share_id_is_the_second_path_segment() -> None:
    assert share_id("https://claude.ai/share/abc-123") == "abc-123"


def test_a_link_that_is_not_a_share_link_has_no_share_id() -> None:
    assert share_id("https://claude.ai/chat/abc-123") is None
    assert share_id("https://chatgpt.com/share/abc-123") is None


def test_a_share_link_names_where_a_browser_reads_the_snapshot() -> None:
    """Keyed on the share id alone: no organization, no session."""
    assert snapshot_url("https://claude.ai/share/abc-123") == (
        "https://claude.ai/api/chat_snapshots/abc-123"
        "?rendering_mode=messages&render_all_tools=true"
    )


def test_nothing_is_offered_for_a_link_this_provider_does_not_own() -> None:
    assert snapshot_url("https://chatgpt.com/share/abc-123") is None
