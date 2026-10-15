"""The verdict on captures a provider actually served, not on fixtures.

These pin the whole chain -- parse, findings, aspects, report -- against
real snapshots, so a change to the aspect table that would flip a real
verdict cannot pass on synthetic data alone. They skip where the
captures are absent: they are real conversations and are not committed.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from convolvger.core.models import MessageRole, ReasoningBlock, TextBlock
from convolvger.core.source import RawSource
from convolvger.providers.chatgpt._parse import parse
from convolvger.providers.grok import _parse as grok
from convolvger.renderers import render_markdown
from convolvger.validation.aspects import Aspect
from convolvger.validation.report import Report

LOCAL = Path(__file__).parent.parent / "fixtures" / "local" / "chatgpt"
URL = "https://chatgpt.com/share/6aa3f5a2-00a4-83eb-8d18-3b2266aac2e6"


def report_for(name: str) -> Report:
    html = (LOCAL / name).read_text(encoding="utf-8")
    return Report(findings=parse(RawSource(url=URL, content=html)).findings)


@pytest.mark.skipif(
    not (LOCAL / "minimal-2026-09-11.html").exists(),
    reason="local capture not present (see tests/fixtures/local/)",
)
def test_the_first_capture_is_complete_but_not_faithful() -> None:
    """The provider served everything; we drop one deferred slot."""
    report = report_for("minimal-2026-09-11.html")

    assert report.complete is True
    assert report.faithful is False
    assert len(report.findings_for(Aspect.FIDELITY)) == 2
    assert len(report.findings_for(Aspect.INFORMATIONAL)) == 12
    assert report.unrecognised == []


@pytest.mark.skipif(
    not (LOCAL / "minimal-2026-09-12.html").exists(),
    reason="local capture not present (see tests/fixtures/local/)",
)
def test_the_second_capture_withholds_four_more_messages() -> None:
    """The same conversation, four messages emptied by the provider."""
    report = report_for("minimal-2026-09-12.html")

    assert report.complete is False
    assert report.faithful is False
    assert len(report.findings_for(Aspect.COMPLETENESS)) == 4
    assert len(report.findings_for(Aspect.FIDELITY)) == 2
    assert len(report.findings_for(Aspect.INFORMATIONAL)) == 12
    assert report.unrecognised == []


GROK_LOCAL = Path(__file__).parent.parent / "fixtures" / "local" / "grok" / "share.json"
GROK_FIXTURE = Path(__file__).parent.parent / "fixtures" / "grok" / "share-minimal.json"
GROK_URL = "https://grok.com/share/bGVnYWN5_00000000-0000-4000-8000-000000000001"
"""Synthetic on purpose. The capture is a real conversation, and nothing
here -- not its link, its title or its text -- is committed; only the
shape of what parsing it produces is asserted."""

CITATION = re.compile(r"<grok:render\b([^>]*)>.*?</grok:render>", re.DOTALL)
"""Written here rather than imported, so the parser is checked against an
independent reading of the markup rather than against itself."""


def without_carried_citations(message: str, cards: list[str]) -> str:
    """Number each inline citation whose card the response carries, by its link."""
    carried = {json.loads(card)["id"]: json.loads(card).get("url") for card in cards}
    numbers: dict[str, int] = {}

    def number(match: re.Match[str]) -> str:
        opening = match.group(1)
        card = re.search(r'card_id="([^"]*)"', opening)
        cited = 'type="render_inline_citation"' in opening
        if not (cited and card and card.group(1) in carried):
            return match.group(0)
        link = carried[card.group(1)] or card.group(1)
        return f"[{numbers.setdefault(link, len(numbers) + 1)}]"

    return CITATION.sub(number, message)


grok_capture = pytest.mark.skipif(
    not GROK_LOCAL.exists(),
    reason="local capture not present (see tests/fixtures/local/)",
)


def _keys(payload: dict[str, Any]) -> dict[str, set[str]]:
    responses = payload["responses"]
    return {
        "envelope": set(payload),
        "conversation": set(payload["conversation"]),
        "responses": set().union(*(set(item) for item in responses)),
        "steps": set().union(
            *(set(step) for item in responses for step in item.get("steps", []))
        ),
    }


@grok_capture
def test_the_committed_grok_fixture_has_the_real_capture_s_shape() -> None:
    """The fixture's text is invented; its keys must not be."""
    real = json.loads(GROK_LOCAL.read_text(encoding="utf-8"))
    synthetic = json.loads(GROK_FIXTURE.read_text(encoding="utf-8"))
    assert _keys(synthetic) == _keys(real)


@grok_capture
def test_the_grok_capture_is_complete_but_its_trace_unmodelled() -> None:
    result = grok.parse(
        RawSource(url=GROK_URL, content=GROK_LOCAL.read_text(encoding="utf-8"))
    )
    messages = result.conversation.messages

    assert [message.role for message in messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ] * 3
    assert all(message.content for message in messages)
    assert [item.code for item in result.findings] == ["unmodelled_content_type"]

    report = Report(findings=result.findings)
    assert report.complete is True
    assert report.faithful is False
    assert report.unrecognised == []


@grok_capture
def test_the_grok_capture_keeps_its_served_text_beside_the_visible_text() -> None:
    result = grok.parse(
        RawSource(url=GROK_URL, content=GROK_LOCAL.read_text(encoding="utf-8"))
    )
    document = render_markdown(result.conversation, findings=result.findings)
    assert "<grok:" not in document

    cited = [
        m for m in result.conversation.messages if "message" in m.provider_metadata
    ]
    assert cited
    for message in cited:
        block = message.content[0]
        assert isinstance(block, TextBlock)
        served = message.provider_metadata["message"]
        cards = message.provider_metadata["cardAttachmentsJson"]
        assert without_carried_citations(served, cards) == block.text


NEWER = Path(__file__).parent.parent / "fixtures"
"""Real throwaway shares from three more providers, saved under local/ and
checked for shape against the synthetic fixtures committed beside them."""


def _capture(provider: str) -> Path:
    return NEWER / "local" / provider / "share.json"


def _fixture(provider: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(
        (NEWER / provider / "share-minimal.json").read_text(encoding="utf-8")
    )
    return loaded


def _union(items: list[Any]) -> set[str]:
    return set().union(*(set(item) for item in items if isinstance(item, dict)))


def _deepseek_keys(payload: dict[str, Any]) -> dict[str, set[str]]:
    body = payload["data"]["biz_data"]
    fragments = [f for m in body["messages"] for f in m["fragments"]]
    return {
        "outer": set(payload),
        "data": set(payload["data"]),
        "body": set(body),
        "message": _union(body["messages"]),
        "fragment": _union(fragments),
        "result": _union([r for f in fragments for r in f.get("results", [])]),
    }


def _kimi_keys(payload: dict[str, Any]) -> dict[str, set[str]]:
    share = payload["share"]
    blocks = [b for m in share["messages"] for b in m["blocks"]]
    return {
        "share": set(share),
        "chat": set(share["chat"]),
        "message": _union(share["messages"]),
        "block": _union(blocks),
    }


def _qwen_keys(payload: dict[str, Any]) -> dict[str, set[str]]:
    data = payload["data"]
    nodes = list(data["chat"]["history"]["messages"].values())
    parts = [p for n in nodes for p in n.get("content_list", [])]
    return {
        "data": set(data),
        "chat": set(data["chat"]),
        "history": set(data["chat"]["history"]),
        "node": _union(nodes),
        "part": _union(parts),
    }


def _perplexity_keys(payload: dict[str, Any]) -> dict[str, set[str]]:
    entries = payload["entries"]
    blocks = [block for entry in entries for block in entry["blocks"]]
    workflow = [b["workflow_block"] for b in blocks if "workflow_block" in b]
    steps = [step for flow in workflow for step in flow["steps"]]
    items = [item for step in steps for item in step["items"]]
    text = [
        i["payload"]["text_payload"] for i in items if "text_payload" in i["payload"]
    ]
    return {
        "envelope": set(payload),
        "thread": set(payload["thread_metadata"]),
        "entry": _union(entries),
        "blocks": {block["intended_usage"] for block in blocks},
        "workflow": _union(workflow),
        "step": _union(steps),
        "item types": {item["type"] for item in items},
        # The image one answer carried is left out of the fixture, which would
        # otherwise answer every test with its finding; its own test adds one.
        "text": _union(text) - {"images"},
    }


SHAPES = {
    "deepseek": _deepseek_keys,
    "kimi": _kimi_keys,
    "qwen": _qwen_keys,
    "perplexity": _perplexity_keys,
}


@pytest.mark.parametrize("provider", list(SHAPES))
def test_each_committed_fixture_has_its_real_capture_s_shape(provider: str) -> None:
    if not _capture(provider).exists():
        pytest.skip("local capture not present (see tests/fixtures/local/)")
    real = json.loads(_capture(provider).read_text(encoding="utf-8"))
    assert SHAPES[provider](_fixture(provider)) == SHAPES[provider](real)


def _parse_capture(provider: str, url: str) -> Any:
    from convolvger.providers.default import build_registry

    path = _capture(provider)
    if not path.exists():
        pytest.skip("local capture not present (see tests/fixtures/local/)")
    return (
        build_registry()
        .get(provider)
        .parse(RawSource(url=url, content=path.read_text(encoding="utf-8")))
    )


def _renumbered(served: str, marker: str) -> str:
    """``served`` with each marker shown as the number of its first citation.

    Written apart from the parser, as the expectation it is checked
    against; neither capture cites inside code, as the earlier version of
    this check, which removed every marker, showed.
    """
    numbers: dict[str, int] = {}
    return re.sub(
        marker,
        lambda m: f"[{numbers.setdefault(m.group(1), len(numbers) + 1)}]",
        served,
    )


def _served(extras: dict[str, Any]) -> list[str]:
    return [item["content"] for item in extras.values() if "content" in item]


def test_the_deepseek_capture_parses_clean_with_every_citation_resolved() -> None:
    result = _parse_capture("deepseek", "https://chat.deepseek.com/share/x")
    messages = result.conversation.messages
    assert [m.role for m in messages] == [MessageRole.USER, MessageRole.ASSISTANT] * 5
    assert result.findings == []
    document = render_markdown(result.conversation, findings=result.findings)
    assert "[citation:" not in document
    lifted = 0
    for message in messages:
        extras = message.provider_metadata.get("fragment_extras", {})
        for served in _served(extras):
            if "[citation:" in served:
                lifted += 1
                block = message.content[0]
                assert isinstance(block, TextBlock)
                assert _renumbered(served, r"\[citation:(\d+)\]") == block.text
                assert len(message.citations) == len(
                    set(re.findall(r"\[\d+\]", block.text))
                )
    assert lifted > 0


def test_the_kimi_capture_parses_with_its_reasoning_flagged_and_sharer_unrendered() -> (
    None
):
    result = _parse_capture("kimi", "https://www.kimi.ai/share/x")
    conversation = result.conversation
    assert [m.role for m in conversation.messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ] * 3
    assert {f.code for f in result.findings} == {"unmodelled_content_type"}
    assert all(message.content for message in conversation.messages)
    document = render_markdown(conversation, findings=result.findings)
    assert conversation.provider_metadata["creator"]["name"] not in document


def test_the_qwen_capture_parses_with_its_copies_in_step_and_citations_resolved() -> (
    None
):
    result = _parse_capture("qwen", "https://chat.qwen.ai/s/x")
    conversation = result.conversation
    assert [m.role for m in conversation.messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ] * 2
    assert all(message.active for message in conversation.messages)
    # Its reasoning is read whole, so nothing is left flagged.
    assert result.findings == []
    assert "messages" not in conversation.provider_metadata["chat"]
    document = render_markdown(conversation, findings=result.findings)
    assert "[[" not in document
    assert conversation.provider_metadata["user_id"] not in document
    for message in conversation.messages[1::2]:
        served = [
            part["content"]
            for part in message.provider_metadata["part_extras"].values()
            if part.get("phase") == "answer" and "content" in part
        ]
        reasoning = [b for b in message.content if isinstance(b, ReasoningBlock)]
        texts = [b for b in message.content if isinstance(b, TextBlock)]
        assert reasoning
        assert message.content == [*reasoning, *texts]
        assert [_renumbered(text, r"\[\[(\d+)\]\]") for text in served] == [
            block.text for block in texts
        ]


def test_the_perplexity_capture_parses_as_measured() -> None:
    url = "https://www.perplexity.ai/search/c0644da2-41d2-4b1e-850f-053b89708567"
    result = _parse_capture("perplexity", url)
    conversation = result.conversation
    assert conversation.id == url.rsplit("/", 1)[1]
    assert [m.role for m in conversation.messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ] * 2
    # Exactly the results each answer's sources mark as cited.
    assert [len(m.citations) for m in conversation.messages[1::2]] == [5, 4]
    assert all(c.url and c.title for m in conversation.messages for c in m.citations)
    assert [(f.code, f.message) for f in result.findings] == [
        (
            "unmodelled_content_type",
            "image in the answer preserved in provider_metadata",
        )
    ]
    document = render_markdown(conversation, findings=result.findings)
    thread = conversation.provider_metadata["thread_metadata"]
    for sharer in ("author_name", "author_username", "author_id"):
        assert thread[sharer] not in document
