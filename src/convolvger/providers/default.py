"""The registry of providers shipped with Convolvger.

Registration is explicit and ordered: no import scanning, no entry-point
discovery. Detection order follows registration order.
"""

from convolvger.providers.chatgpt import ChatGPTProvider
from convolvger.providers.claude import ClaudeProvider
from convolvger.providers.registry import ProviderRegistry


def build_registry() -> ProviderRegistry:
    """Return a registry containing every bundled provider."""
    registry = ProviderRegistry()
    registry.register(ChatGPTProvider())
    registry.register(ClaudeProvider())
    return registry
