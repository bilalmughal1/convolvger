from convolvger.core.errors import ProviderNotFoundError
from convolvger.providers.base import Provider


class ProviderRegistry:
    """Ordered collection of provider adapters.

    Providers are matched in registration order, so detection is
    deterministic for a given registration sequence.
    """

    def __init__(self) -> None:
        self._providers: list[Provider] = []

    def register(self, provider: Provider) -> None:
        if any(existing.name == provider.name for existing in self._providers):
            raise ValueError(f"Provider already registered: {provider.name}")
        self._providers.append(provider)

    def names(self) -> list[str]:
        return [provider.name for provider in self._providers]

    def get(self, name: str) -> Provider:
        for provider in self._providers:
            if provider.name == name:
                return provider
        raise ProviderNotFoundError(f"No provider named: {name}")

    def detect(self, url: str) -> Provider:
        for provider in self._providers:
            if provider.matches(url):
                return provider
        raise ProviderNotFoundError(f"No provider matches URL: {url}")
