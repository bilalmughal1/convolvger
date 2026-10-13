"""Every provider refuses JSON nested past the limit, and keeps what is within it.

Within the limit is checked where it matters: a value placed at every
spot in each synthetic fixture where a parser could keep it, nested so
the source reaches exactly the limit, must survive the parse, both
renderers and being read back as an archive. One level more must be
refused at every one of those spots.
"""

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from convolvger.core import jsonload
from convolvger.core.archive import load_archive
from convolvger.core.errors import ConvolvgerError
from convolvger.core.source import RawSource
from convolvger.providers.chatgpt._turbostream import NULL_SENTINEL, decode_html
from convolvger.providers.deepseek import _fetch as deepseek_fetch
from convolvger.providers.default import build_registry
from convolvger.providers.grok import _fetch as grok_fetch
from convolvger.providers.kimi import _fetch as kimi_fetch
from convolvger.providers.qwen import _fetch as qwen_fetch
from convolvger.renderers import render_json, render_markdown

FIXTURES = Path(__file__).parent.parent / "fixtures"
MARK = "deep-value-end"
REGISTRY = build_registry()

URLS = {
    "claude": "https://claude.ai/share/00000000-0000-0000-0000-000000000000",
    "grok": "https://grok.com/share/bGVnYWN5_00000000-0000-4000-8000-000000000001",
    "deepseek": "https://chat.deepseek.com/share/0example0share0id",
    "kimi": "https://www.kimi.ai/share/00000000-0000-4000-8000-000000000002",
    "qwen": "https://chat.qwen.ai/s/00000000-0000-4000-8000-000000000001",
    "gemini": "https://gemini.google.com/share/0000000000ab",
}
JSON_PROVIDERS = ["claude", "grok", "deepseek", "kimi", "qwen"]
CHATGPT_URL = "https://chatgpt.com/share/abc123"


def nest(levels: int) -> Any:
    value: Any = MARK
    for _ in range(levels):
        value = [value]
    return value


def gemini_body(payload: object) -> str:
    inner = json.dumps(payload, ensure_ascii=False)
    frame = json.dumps(
        [["wrb.fr", "ujx1Bf", inner, None, None, None, "generic"]], ensure_ascii=False
    )
    return f")]}}'\n{len(frame.encode('utf-16-le')) // 2 + 2}\n{frame}"


def source(provider: str, document: object) -> RawSource:
    content = gemini_body(document) if provider == "gemini" else json.dumps(document)
    return RawSource(url=URLS[provider], content=content)


def fixture(provider: str) -> Any:
    path = FIXTURES / provider / "share-minimal.json"
    return json.loads(path.read_text(encoding="utf-8"))


def containers(
    value: Any, depth: int = 1, path: tuple[Any, ...] = ()
) -> Iterator[tuple[tuple[Any, ...], int]]:
    if isinstance(value, dict):
        yield path, depth
        for key, child in value.items():
            yield from containers(child, depth + 1, (*path, key))
    elif isinstance(value, list):
        yield path, depth
        for index, child in enumerate(value):
            yield from containers(child, depth + 1, (*path, index))


def with_value_at(document: Any, path: tuple[Any, ...], value: Any) -> Any:
    placed = copy.deepcopy(document)
    node = placed
    for step in path:
        node = node[step]
    if isinstance(node, dict):
        node["unmodelled_for_test"] = value
    else:
        node.append(value)
    return placed


def depth_of(value: Any) -> int:
    deepest, pending = 0, [(value, 1)]
    while pending:
        node, depth = pending.pop()
        if isinstance(node, (dict, list)):
            deepest = max(deepest, depth)
            children = node.values() if isinstance(node, dict) else node
            pending.extend((child, depth + 1) for child in children)
    return deepest


@pytest.mark.parametrize("provider", list(URLS))
def test_a_source_at_the_limit_survives_export_and_reads_back(provider: str) -> None:
    base = fixture(provider)
    parser = REGISTRY.get(provider)
    kept = 0
    for path, depth in containers(base):
        document = with_value_at(base, path, nest(jsonload.MAX_DEPTH - depth))
        assert depth_of(document) == jsonload.MAX_DEPTH
        result = parser.parse(source(provider, document))
        archive = render_json(result.conversation, findings=result.findings)
        render_markdown(result.conversation, findings=result.findings)
        load_archive(archive)
        kept += MARK in archive
    assert kept, "no spot in the fixture keeps an unmodelled value"


@pytest.mark.parametrize("provider", list(URLS))
def test_a_source_one_level_over_the_limit_is_refused_wherever_it_nests(
    provider: str,
) -> None:
    base = fixture(provider)
    parser = REGISTRY.get(provider)
    for path, depth in containers(base):
        document = with_value_at(base, path, nest(jsonload.MAX_DEPTH + 1 - depth))
        with pytest.raises(ConvolvgerError, match="refused"):
            parser.parse(source(provider, document))


@pytest.mark.parametrize("provider", JSON_PROVIDERS)
def test_a_source_too_deep_for_the_stack_is_refused_not_a_crash(provider: str) -> None:
    content = '{"a": ' + "[" * 100_000 + "]" * 100_000 + "}"
    with pytest.raises(ConvolvgerError):
        REGISTRY.get(provider).parse(RawSource(url=URLS[provider], content=content))


def test_a_gemini_frame_too_deep_for_the_stack_is_refused_not_a_crash() -> None:
    content = ")]}'\n123\n" + "[" * 100_000 + "]" * 100_000 + "\n"
    with pytest.raises(ConvolvgerError, match="refused"):
        REGISTRY.get("gemini").parse(RawSource(url=URLS["gemini"], content=content))


def test_a_gemini_payload_too_deep_for_the_stack_is_refused_not_a_crash() -> None:
    content = gemini_body("PLACEHOLDER").replace(
        '"\\"PLACEHOLDER\\""', json.dumps("[" * 100_000 + "]" * 100_000)
    )
    with pytest.raises(ConvolvgerError, match="refused"):
        REGISTRY.get("gemini").parse(RawSource(url=URLS["gemini"], content=content))


def test_a_grok_card_too_deep_to_read_is_reported_not_a_crash() -> None:
    document = fixture("grok")
    response = next(
        item
        for item in containers(document)
        if isinstance(_at(document, item[0]), dict)
        and "cardAttachmentsJson" in _at(document, item[0])
    )
    _at(document, response[0])["cardAttachmentsJson"] = ["[" * 100_000 + "]" * 100_000]
    result = REGISTRY.get("grok").parse(source("grok", document))
    assert "unmodelled_content_type" in {item.code for item in result.findings}


def _at(document: Any, path: tuple[Any, ...]) -> Any:
    for step in path:
        document = document[step]
    return document


def _chatgpt_page(value: Any) -> str:
    """Encode ``value`` as a ChatGPT page, every container its own indexed node."""
    flat: list[Any] = []
    seen: dict[int, int] = {}
    primitives: dict[tuple[str, Any], int] = {}

    def encode(item: Any) -> int:
        if item is None:
            return NULL_SENTINEL
        if isinstance(item, (dict, list)):
            if id(item) in seen:
                return seen[id(item)]
            index = len(flat)
            flat.append(None)
            seen[id(item)] = index
            if isinstance(item, dict):
                flat[index] = {f"_{encode(k)}": encode(v) for k, v in item.items()}
            else:
                flat[index] = [encode(v) for v in item]
            return index
        key = (type(item).__name__, item)
        if key not in primitives:
            primitives[key] = len(flat)
            flat.append(item)
        return primitives[key]

    encode(value)
    payload = json.dumps(json.dumps(flat) + "\n")[1:-1]
    return f'<html><script>streamController.enqueue("{payload}");</script></html>'


def _chatgpt_with_deep_content(extra_levels: int) -> tuple[str, int]:
    """A page whose first message content is an unmodelled type holding a deep value."""
    html = (FIXTURES / "chatgpt" / "share-minimal.html").read_text(encoding="utf-8")
    value = decode_html(html).value
    path = next(
        path
        for path, _ in containers(value)
        if isinstance(_at(value, path), dict) and "content_type" in _at(value, path)
    )
    content = _at(value, path)
    content["content_type"] = "unmodelled_for_test"
    content["deep"] = []
    # ``[]`` stands where the outermost level of the deep value will go.
    room = jsonload.MAX_DEPTH - depth_of(value) + 1
    content["deep"] = nest(room + extra_levels)
    return _chatgpt_page(value), depth_of(value)


def test_a_chatgpt_payload_decoding_to_the_limit_survives_export() -> None:
    page, depth = _chatgpt_with_deep_content(0)
    assert depth == jsonload.MAX_DEPTH
    result = REGISTRY.get("chatgpt").parse(RawSource(url=CHATGPT_URL, content=page))
    archive = render_json(result.conversation, findings=result.findings)
    assert MARK in archive
    load_archive(archive)


def test_a_chatgpt_payload_decoding_past_the_limit_is_refused() -> None:
    """Its flat array is two levels deep; only what it decodes to can be judged."""
    page, depth = _chatgpt_with_deep_content(1)
    assert depth == jsonload.MAX_DEPTH + 1
    with pytest.raises(ConvolvgerError, match="refused"):
        REGISTRY.get("chatgpt").parse(RawSource(url=CHATGPT_URL, content=page))


FETCHERS = {
    "grok": (grok_fetch, URLS["grok"]),
    "deepseek": (deepseek_fetch, URLS["deepseek"]),
    "kimi": (kimi_fetch, URLS["kimi"]),
    "qwen": (qwen_fetch, URLS["qwen"]),
}


@pytest.mark.parametrize("provider", list(FETCHERS))
def test_a_fetched_body_too_deep_to_judge_is_left_to_the_parser(provider: str) -> None:
    """Whether it is empty cannot be told, so the parser gets to refuse it."""
    module, url = FETCHERS[provider]
    body = '{"a": ' + "[" * 100_000 + "]" * 100_000 + "}"
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body))
    )
    assert module.fetch(url, client=client).content == body
