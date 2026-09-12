from convolvger.core.findings import Finding, Level, finding
from convolvger.validation.aspects import Aspect
from convolvger.validation.report import Report


def test_no_findings_is_complete_and_faithful() -> None:
    report = Report()

    assert report.complete is True
    assert report.faithful is True


def test_a_completeness_finding_clears_only_completeness() -> None:
    report = Report(findings=[finding("message_content_withheld", "emptied", "m1")])

    assert report.complete is False
    assert report.faithful is True


def test_a_fidelity_finding_clears_only_fidelity() -> None:
    report = Report(findings=[finding("unmodelled_content_type", "unknown block")])

    assert report.complete is True
    assert report.faithful is False


def test_informational_findings_change_no_verdict() -> None:
    """The whole point: a snapshot of empty messages is not damage."""
    report = Report(
        findings=[
            finding("message_has_no_content", "no content blocks", f"m{n}")
            for n in range(12)
        ]
    )

    assert report.complete is True
    assert report.faithful is True
    assert len(report.findings) == 12


def test_a_real_capture_shape_is_complete_but_not_faithful() -> None:
    """12 empty messages the provider meant to send, 2 slots we dropped."""
    findings = [
        finding("message_has_no_content", "no content blocks", f"m{n}")
        for n in range(12)
    ]
    findings.append(finding("deferred_slot_not_merged", "slot 3"))
    findings.append(finding("deferred_value_unresolved", "value [4]"))
    report = Report(findings=findings)

    assert report.complete is True
    assert report.faithful is False
    assert len(report.findings_for(Aspect.FIDELITY)) == 2


def test_findings_are_grouped_by_aspect_in_the_order_recorded() -> None:
    first = finding("unrecognised_role", "'bot' preserved as unknown")
    second = finding("unrecognised_stream_line", "line ignored")
    report = Report(findings=[first, finding("message_has_no_content", "x"), second])

    assert report.findings_for(Aspect.FIDELITY) == [first, second]
    assert len(report.findings_for(Aspect.INFORMATIONAL)) == 1


def test_a_code_from_a_later_version_does_not_raise() -> None:
    """An archive may be newer than the tool reading it."""
    future = Finding(code="minted_by_a_later_version", level=Level.WARNING, message="?")
    report = Report(findings=[future])

    assert report.complete is True
    assert report.faithful is True


def test_a_code_from_a_later_version_is_reported() -> None:
    future = Finding(code="minted_by_a_later_version", level=Level.NOTE, message="?")
    report = Report(findings=[future])

    assert report.unrecognised == [future]


def test_a_known_code_is_never_unrecognised() -> None:
    report = Report(findings=[finding("literal_object_key", "kept as-is: x")])

    assert report.unrecognised == []
