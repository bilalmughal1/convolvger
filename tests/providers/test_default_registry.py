from convolvger.providers.base import Provider
from convolvger.providers.chatgpt import ChatGPTProvider
from convolvger.providers.claude import ClaudeProvider
from convolvger.providers.default import build_registry
from convolvger.providers.gemini import GeminiProvider


def test_chatgpt_provider_satisfies_the_protocol() -> None:
    provider: Provider = ChatGPTProvider()

    assert provider.name == "chatgpt"


def test_registry_contains_chatgpt() -> None:
    assert build_registry().names() == ["chatgpt", "claude", "gemini"]


def test_registry_detects_a_chatgpt_share_url() -> None:
    registry = build_registry()
    url = "https://chatgpt.com/share/6aa3f5a2-00a4-83eb-8d18-3b2266aac2e6"

    assert registry.detect(url).name == "chatgpt"


def test_build_registry_returns_independent_instances() -> None:
    """A shared mutable registry across callers would leak registrations."""
    assert build_registry() is not build_registry()


def test_claude_provider_satisfies_the_protocol() -> None:
    provider: Provider = ClaudeProvider()

    assert provider.name == "claude"


def test_registry_detects_a_claude_share_url() -> None:
    registry = build_registry()
    url = "https://claude.ai/share/f2f59cb2-8857-4808-a650-2712e80290fd"

    assert registry.detect(url).name == "claude"


def test_gemini_provider_satisfies_the_protocol() -> None:
    provider: Provider = GeminiProvider()

    assert provider.name == "gemini"


def test_registry_detects_a_gemini_share_url() -> None:
    registry = build_registry()
    url = "https://gemini.google.com/share/09bcf760b07b"

    assert registry.detect(url).name == "gemini"


def test_registry_detects_a_shortened_gemini_share_url() -> None:
    """The shortener is a distinct host and must be claimed too."""
    registry = build_registry()

    assert registry.detect("https://share.gemini.google/94ESiKYXbGiV").name == "gemini"
