from datetime import UTC, datetime

import pytest

from convolvger.core.errors import ProviderNotFoundError
from convolvger.core.models import (
    Conversation,
    Message,
    MessageRole,
    TextBlock,
)
from convolvger.core.results import ParseResult
from convolvger.core.source import RawSource
from convolvger.providers.base import Provider
from convolvger.providers.registry import ProviderRegistry


class FakeProvider:
    def __init__(
        self,
        name: str = "fake",
        prefix: str = "https://fake.example/share/",
    ) -> None:
        self.name = name
        self.prefix = prefix

    def matches(self, url: str) -> bool:
        return url.startswith(self.prefix)

    def fetch(self, url: str) -> RawSource:
        return RawSource(
            url=url,
            content="raw snapshot",
            content_type="text/html",
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

    def parse(self, source: RawSource) -> ParseResult:
        conversation = Conversation(
            provider=self.name,
            source_url=source.url,
            messages=[
                Message(
                    role=MessageRole.USER,
                    content=[TextBlock(text=source.content)],
                )
            ],
        )
        return ParseResult(conversation=conversation)


def test_fake_provider_satisfies_provider_protocol() -> None:
    provider: Provider = FakeProvider()

    assert provider.name == "fake"


def test_registered_provider_is_listed_and_retrievable() -> None:
    registry = ProviderRegistry()
    provider = FakeProvider()

    registry.register(provider)

    assert registry.names() == ["fake"]
    assert registry.get("fake") is provider


def test_get_unknown_provider_raises() -> None:
    registry = ProviderRegistry()

    with pytest.raises(ProviderNotFoundError):
        registry.get("missing")


def test_detect_returns_matching_provider() -> None:
    registry = ProviderRegistry()
    provider = FakeProvider()
    registry.register(provider)

    assert registry.detect("https://fake.example/share/abc") is provider


def test_detect_unmatched_url_raises() -> None:
    registry = ProviderRegistry()
    registry.register(FakeProvider())

    with pytest.raises(ProviderNotFoundError):
        registry.detect("https://other.example/share/abc")


def test_detection_uses_registration_order() -> None:
    registry = ProviderRegistry()
    first = FakeProvider(name="first")
    second = FakeProvider(name="second")
    registry.register(first)
    registry.register(second)

    assert registry.detect("https://fake.example/share/abc") is first


def test_duplicate_provider_name_is_rejected() -> None:
    registry = ProviderRegistry()
    registry.register(FakeProvider())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeProvider())


def test_provider_round_trip_produces_canonical_conversation() -> None:
    registry = ProviderRegistry()
    registry.register(FakeProvider())

    provider = registry.detect("https://fake.example/share/abc")
    result = provider.parse(provider.fetch("https://fake.example/share/abc"))
    conversation = result.conversation

    assert conversation.provider == "fake"
    assert conversation.messages[0].content[0].text == "raw snapshot"
