"""The verdict on captures a provider actually served, not on fixtures.

These pin the whole chain -- parse, findings, aspects, report -- against
real snapshots, so a change to the aspect table that would flip a real
verdict cannot pass on synthetic data alone. They skip where the
captures are absent: they are real conversations and are not committed.
"""

from pathlib import Path

import pytest

from convolvger.core.source import RawSource
from convolvger.providers.chatgpt._parse import parse
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
