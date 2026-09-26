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

from convolvger.core.models import MessageRole, TextBlock
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
    """Remove each inline citation whose card the response carries."""
    carried = {json.loads(card)["id"] for card in cards}

    def drop(match: re.Match[str]) -> str:
        opening = match.group(1)
        card = re.search(r'card_id="([^"]*)"', opening)
        cited = 'type="render_inline_citation"' in opening
        return "" if cited and card and card.group(1) in carried else match.group(0)

    return CITATION.sub(drop, message)


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
