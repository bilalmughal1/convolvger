"""Every language, through every provider, reaches Markdown and JSON unchanged.

One conversation per provider carries every sample and edge case in the
fixture. Each is asserted byte for byte in the parsed model, in the
Markdown, and in the JSON read back -- so a parser or renderer that
normalised, trimmed or re-encoded any script fails here and names it.

Providers that send JSON are tried both ways they might: with non-ASCII
escaped, where everything outside the basic plane arrives as a pair of
escaped halves, and raw. The escaped form is also the check that a whole
emoji is never mistaken for half of one.
"""

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from convolvger.core.archive import load_archive
from convolvger.core.models import TextBlock
from convolvger.core.results import ParseResult
from convolvger.core.source import RawSource
from convolvger.providers.chatgpt import ChatGPTProvider
from convolvger.providers.chatgpt import _fetch as chatgpt_fetch
from convolvger.providers.claude import ClaudeProvider
from convolvger.providers.deepseek import DeepSeekProvider
from convolvger.providers.deepseek import _fetch as deepseek_fetch
from convolvger.providers.gemini import GeminiProvider
from convolvger.providers.gemini import _fetch as gemini_fetch
from convolvger.providers.grok import GrokProvider
from convolvger.providers.grok import _fetch as grok_fetch
from convolvger.providers.kimi import KimiProvider
from convolvger.providers.kimi import _fetch as kimi_fetch
from convolvger.providers.qwen import QwenProvider
from convolvger.providers.qwen import _fetch as qwen_fetch
from convolvger.renderers import render_json, render_markdown

FIXTURE = Path(__file__).parent.parent / "fixtures" / "multilingual" / "samples.json"
LOADED = json.loads(FIXTURE.read_text(encoding="utf-8"))
NAMES = [f"{s['continent']}: {s['language']}" for s in LOADED["samples"]] + [
    f"edge: {e['case']}" for e in LOADED["edge_cases"]
]
TEXTS: list[str] = [s["text"] for s in LOADED["samples"]] + [
    e["text"] for e in LOADED["edge_cases"]
]
TITLE = TEXTS[0]


def claude(escape: bool, texts: list[str]) -> RawSource:
    messages = [
        {
            "uuid": f"m{index}",
            "sender": "human" if index % 2 == 0 else "assistant",
            "created_at": "2026-01-01T00:00:00Z",
            "content": [{"type": "text", "text": text}],
        }
        for index, text in enumerate(texts)
    ]
    body = {"uuid": "u", "snapshot_name": TITLE, "chat_messages": messages}
    return RawSource(
        url="https://claude.ai/share/x", content=json.dumps(body, ensure_ascii=escape)
    )


def grok(escape: bool, texts: list[str]) -> RawSource:
    responses = [
        {
            "responseId": f"r{index}",
            "sender": "human" if index % 2 == 0 else "assistant",
            "message": text,
            "createTime": "2026-01-01T00:00:00Z",
        }
        for index, text in enumerate(texts)
    ]
    body = {
        "conversation": {"conversationId": "c", "title": TITLE},
        "responses": responses,
    }
    return RawSource(
        url="https://grok.com/share/x", content=json.dumps(body, ensure_ascii=escape)
    )


def gemini(escape: bool, texts: list[str]) -> RawSource:
    padded = [*texts, "."] if len(texts) % 2 else texts
    turns = [
        [
            ["c_1", f"r_{index}"],
            None,
            [[padded[index]]],
            [[[f"rc_{index}", [padded[index + 1]]]]],
            [1789000000, 0],
        ]
        for index in range(0, len(padded), 2)
    ]
    inner = json.dumps([[None, turns, [None, TITLE]]], ensure_ascii=escape)
    frame = json.dumps(
        [["wrb.fr", "ujx1Bf", inner, None, None, None, "generic"]], ensure_ascii=escape
    )
    return RawSource(
        url="https://gemini.google.com/share/x", content=f")]}}'\n\n{frame}"
    )


def chatgpt(escape: bool, texts: list[str]) -> RawSource:
    nodes: list[dict[str, object]] = [{"id": "root", "children": ["n0"]}]
    for index, text in enumerate(texts):
        nodes.append(
            {
                "id": f"n{index}",
                "message": {
                    "id": f"n{index}",
                    "author": {"role": "user" if index % 2 == 0 else "assistant"},
                    "content": {"content_type": "text", "parts": [text]},
                    "weight": 1.0,
                },
            }
        )
    flat = [
        {"_1": 2},
        "loaderData",
        {"_3": 4},
        "routes/share.$shareId.($action)",
        {"_5": 6},
        "serverResponse",
        {"_7": 8},
        "data",
        {"title": TITLE, "linear_conversation": nodes},
    ]
    escaped = json.dumps(
        json.dumps(flat, ensure_ascii=escape) + "\n", ensure_ascii=escape
    )
    return RawSource(
        url="https://chatgpt.com/share/x",
        content=f"<html><script>streamController.enqueue({escaped})</script></html>",
    )


def deepseek(escape: bool, texts: list[str]) -> RawSource:
    messages = [
        {
            "message_id": index + 1,
            "parent_id": index or None,
            "role": "USER" if index % 2 == 0 else "ASSISTANT",
            "status": "FINISHED",
            "inserted_at": 1789000000.0 + index,
            "fragments": [
                {
                    "id": 1,
                    "type": "REQUEST" if index % 2 == 0 else "RESPONSE",
                    "content": text,
                }
            ],
        }
        for index, text in enumerate(texts)
    ]
    body = {
        "code": 0,
        "msg": "",
        "data": {
            "biz_code": 0,
            "biz_msg": "",
            "biz_data": {"title": TITLE, "messages": messages},
        },
    }
    return RawSource(
        url="https://chat.deepseek.com/share/x",
        content=json.dumps(body, ensure_ascii=escape),
    )


def kimi(escape: bool, texts: list[str]) -> RawSource:
    messages = [
        {
            "id": f"m{index}",
            "role": "user" if index % 2 == 0 else "assistant",
            "status": "MESSAGE_STATUS_COMPLETED",
            "blocks": [{"messageId": f"m{index}", "text": {"content": text}}],
        }
        for index, text in enumerate(texts)
    ]
    body = {
        "share": {"id": "s", "chat": {"id": "c", "name": TITLE}, "messages": messages}
    }
    return RawSource(
        url="https://www.kimi.ai/share/x", content=json.dumps(body, ensure_ascii=escape)
    )


def qwen(escape: bool, texts: list[str]) -> RawSource:
    nodes: dict[str, dict[str, object]] = {}
    for index, text in enumerate(texts):
        key = f"n{index}"
        node: dict[str, object] = {
            "id": key,
            "parentId": f"n{index - 1}" if index else None,
            "childrenIds": [f"n{index + 1}"] if index + 1 < len(texts) else [],
            "role": "user" if index % 2 == 0 else "assistant",
            "timestamp": 1789000000 + index,
        }
        if index % 2 == 0:
            node["content"] = text
        else:
            node["content"] = ""
            node["content_list"] = [{"phase": "answer", "content": text}]
        nodes[key] = node
    last = f"n{len(texts) - 1}"
    body = {
        "success": True,
        "data": {
            "id": "q",
            "title": TITLE,
            "chat": {
                "history": {"messages": nodes, "currentId": last},
                "messages": list(nodes.values()),
            },
        },
    }
    return RawSource(
        url="https://chat.qwen.ai/s/x", content=json.dumps(body, ensure_ascii=escape)
    )


SOURCES: dict[
    str,
    tuple[Callable[[RawSource], ParseResult], Callable[[bool, list[str]], RawSource]],
] = {
    "chatgpt": (ChatGPTProvider().parse, chatgpt),
    "claude": (ClaudeProvider().parse, claude),
    "gemini": (GeminiProvider().parse, gemini),
    "grok": (GrokProvider().parse, grok),
    "deepseek": (DeepSeekProvider().parse, deepseek),
    "kimi": (KimiProvider().parse, kimi),
    "qwen": (QwenProvider().parse, qwen),
}
CASES = [(name, escape) for name in SOURCES for escape in (True, False)]


@pytest.mark.parametrize(
    ("provider", "escape"),
    CASES,
    ids=[f"{n}-{'escaped' if e else 'raw'}" for n, e in CASES],
)
def test_every_language_survives_parsing_markdown_and_json(
    provider: str, escape: bool
) -> None:
    parse, build = SOURCES[provider]
    result = parse(build(escape, TEXTS))
    conversation = result.conversation
    findings = result.findings

    carried = [
        block.text
        for message in conversation.messages
        for block in message.content
        if isinstance(block, TextBlock)
    ]
    document = render_markdown(conversation, findings=findings)
    reloaded = load_archive(render_json(conversation, findings=findings)).conversation

    assert conversation.title == TITLE
    assert [n for n, t in zip(NAMES, TEXTS, strict=True) if t not in carried] == []
    assert [n for n, t in zip(NAMES, TEXTS, strict=True) if t not in document] == []
    assert reloaded == conversation
    assert "unpaired_surrogate_replaced" not in [item.code for item in findings]


HALF_EMOJI = "cut off mid-emoji \ud83d"
"""The first half of a surrogate pair with no second half, as a reply cut off
between the two halves of an emoji leaves it."""


@pytest.mark.parametrize("provider", list(SOURCES))
def test_every_provider_replaces_half_an_emoji_and_reports_it(provider: str) -> None:
    """Each adapter must mend a half character, not only the one a CLI test uses.

    This fails for any provider whose ``parse`` stops passing its result
    through ``replace_unpaired_surrogates``.
    """
    parse, build = SOURCES[provider]
    source = build(True, [TITLE, HALF_EMOJI])
    assert "\\ud83d" in source.content, (
        "the half must arrive escaped, as providers send it"
    )

    result = parse(source)

    carried = [
        block.text
        for message in result.conversation.messages
        for block in message.content
        if isinstance(block, TextBlock)
    ]
    assert "cut off mid-emoji �" in carried
    assert "unpaired_surrogate_replaced" in [item.code for item in result.findings]


FETCHERS = {
    "chatgpt": (chatgpt_fetch.fetch, "https://chatgpt.com/share/x"),
    "gemini": (gemini_fetch.fetch, "https://gemini.google.com/share/0000000000ab"),
    "grok": (
        grok_fetch.fetch,
        "https://grok.com/share/bGVnYWN5_00000000-0000-4000-8000-000000000001",
    ),
    "deepseek": (
        deepseek_fetch.fetch,
        "https://chat.deepseek.com/share/0example0share0id",
    ),
    "kimi": (
        kimi_fetch.fetch,
        "https://www.kimi.ai/share/00000000-0000-4000-8000-000000000002",
    ),
    "qwen": (
        qwen_fetch.fetch,
        "https://chat.qwen.ai/s/00000000-0000-4000-8000-000000000001",
    ),
}


@pytest.mark.parametrize("provider", list(FETCHERS))
def test_a_response_without_a_charset_is_read_as_utf8(provider: str) -> None:
    """Grok answers ``application/json`` with no charset; the body is UTF-8."""
    fetch, url = FETCHERS[provider]
    body = json.dumps({"responses": [{"message": " ".join(TEXTS)}]}, ensure_ascii=False)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=body.encode("utf-8"),
            headers={"content-type": "application/json"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch(url, client=client).content == body
