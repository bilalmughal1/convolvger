"""The registry of providers shipped with Convolvger.

Registration is explicit and ordered: no import scanning, no entry-point
discovery. Detection order follows registration order.
"""

from convolvger.providers.chatgpt import ChatGPTProvider
from convolvger.providers.claude import ClaudeProvider
from convolvger.providers.deepseek import DeepSeekProvider
from convolvger.providers.gemini import GeminiProvider
from convolvger.providers.grok import GrokProvider
from convolvger.providers.kimi import KimiProvider
from convolvger.providers.qwen import QwenProvider
from convolvger.providers.registry import ProviderRegistry


def build_registry() -> ProviderRegistry:
    """Return a registry containing every bundled provider."""
    registry = ProviderRegistry()
    registry.register(ChatGPTProvider())
    registry.register(ClaudeProvider())
    registry.register(GeminiProvider())
    registry.register(GrokProvider())
    registry.register(DeepSeekProvider())
    registry.register(KimiProvider())
    registry.register(QwenProvider())
    return registry
