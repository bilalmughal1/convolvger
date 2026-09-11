from convolvger.providers.base import Provider
from convolvger.providers.chatgpt import ChatGPTProvider
from convolvger.providers.default import build_registry


def test_chatgpt_provider_satisfies_the_protocol() -> None:
    provider: Provider = ChatGPTProvider()

    assert provider.name == "chatgpt"


def test_registry_contains_chatgpt() -> None:
    assert build_registry().names() == ["chatgpt"]


def test_registry_detects_a_chatgpt_share_url() -> None:
    registry = build_registry()
    url = "https://chatgpt.com/share/6aa3f5a2-00a4-83eb-8d18-3b2266aac2e6"

    assert registry.detect(url).name == "chatgpt"


def test_build_registry_returns_independent_instances() -> None:
    """A shared mutable registry across callers would leak registrations."""
    assert build_registry() is not build_registry()
