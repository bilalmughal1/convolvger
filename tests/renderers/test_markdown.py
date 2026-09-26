from datetime import UTC, datetime
from pathlib import Path

import pytest

from convolvger.core.findings import finding
from convolvger.core.models import (
    CodeBlock,
    Conversation,
    Message,
    MessageRole,
    ReasoningBlock,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UnknownBlock,
)
from convolvger.core.source import RawSource
from convolvger.providers.chatgpt._parse import parse
from convolvger.renderers import render_markdown

LOCAL = Path(__file__).parent.parent / "fixtures" / "local" / "chatgpt"


def conversation(*messages: Message, title: str | None = None) -> Conversation:
    return Conversation(
        provider="chatgpt",
        source_url="https://chatgpt.com/share/abc",
        title=title,
        messages=list(messages),
    )


def text(
    role: MessageRole,
    body: str,
    *,
    visible: bool = True,
    active: bool = True,
    author: str | None = None,
    timestamp: datetime | None = None,
) -> Message:
    return Message(
        role=role,
        content=[TextBlock(text=body)],
        visible=visible,
        active=active,
        author=author,
        timestamp=timestamp,
    )


def test_header_reports_source_and_counts() -> None:
    output = render_markdown(conversation(text(MessageRole.USER, "hi"), title="Chat"))

    assert output.startswith("# Chat")
    assert "https://chatgpt.com/share/abc" in output
    assert "1 in snapshot, 1 rendered" in output


def test_untitled_conversation_gets_a_placeholder_title() -> None:
    assert "# Untitled conversation" in render_markdown(
        conversation(text(MessageRole.USER, "hi"))
    )


def test_roles_become_headings() -> None:
    output = render_markdown(
        conversation(
            text(MessageRole.USER, "question"),
            text(MessageRole.ASSISTANT, "answer"),
        )
    )

    assert "## User" in output
    assert "## Assistant" in output


def test_hidden_messages_are_omitted_and_reported() -> None:
    output = render_markdown(
        conversation(
            text(MessageRole.USER, "shown"),
            text(MessageRole.SYSTEM, "secret", visible=False),
        )
    )

    assert "secret" not in output
    assert "Omitted as hidden by the provider: 1" in output
    assert "preserved in full in the JSON export" in output


def test_hidden_messages_can_be_included() -> None:
    output = render_markdown(
        conversation(text(MessageRole.SYSTEM, "secret", visible=False)),
        include_hidden=True,
    )

    assert "secret" in output
    assert "— hidden" in output


def test_deactivated_messages_are_omitted_and_reported() -> None:
    output = render_markdown(
        conversation(text(MessageRole.ASSISTANT, "abandoned draft", active=False))
    )

    assert "abandoned draft" not in output
    assert "Omitted as deactivated branches: 1" in output


def test_deactivated_messages_can_be_included() -> None:
    output = render_markdown(
        conversation(text(MessageRole.ASSISTANT, "abandoned draft", active=False)),
        include_inactive=True,
    )

    assert "— deactivated" in output


def test_messages_without_content_are_omitted_and_reported() -> None:
    output = render_markdown(
        conversation(
            text(MessageRole.USER, "shown"),
            Message(role=MessageRole.ASSISTANT),
        )
    )

    assert "Omitted as carrying no renderable content: 1" in output
    assert "no renderable content*" not in output


def test_every_message_is_either_rendered_or_accounted_for() -> None:
    """The header must reconcile: total == rendered + every omission."""
    output = render_markdown(
        conversation(
            text(MessageRole.USER, "a"),
            text(MessageRole.SYSTEM, "b", visible=False),
            text(MessageRole.ASSISTANT, "c", active=False),
            Message(role=MessageRole.ASSISTANT),
        )
    )

    assert "4 in snapshot, 1 rendered" in output
    assert "hidden by the provider: 1" in output
    assert "deactivated branches: 1" in output
    assert "no renderable content: 1" in output


def test_code_block_is_fenced_with_language() -> None:
    output = render_markdown(
        conversation(
            Message(
                role=MessageRole.ASSISTANT,
                content=[CodeBlock(text="print(1)", language="python")],
            )
        )
    )

    assert "```python\nprint(1)\n```" in output


def test_code_block_without_language_is_still_fenced() -> None:
    output = render_markdown(
        conversation(
            Message(
                role=MessageRole.ASSISTANT,
                content=[CodeBlock(text='search("x")')],
            )
        )
    )

    assert '```\nsearch("x")\n```' in output


def test_reasoning_is_visually_distinct_from_assistant_prose() -> None:
    """Reasoning must never be presentable as ordinary assistant output."""
    output = render_markdown(
        conversation(
            Message(
                role=MessageRole.ASSISTANT,
                content=[ReasoningBlock(text="Searching 3 websites")],
            )
        )
    )

    assert "**Reasoning**" in output
    assert "> Searching 3 websites" in output


def test_reasoning_label_is_shown() -> None:
    output = render_markdown(
        conversation(
            Message(
                role=MessageRole.ASSISTANT,
                content=[ReasoningBlock(text="Worked briefly", label="recap")],
            )
        )
    )

    assert "**Reasoning — recap**" in output


def test_unknown_block_is_flagged_not_silently_skipped() -> None:
    output = render_markdown(
        conversation(
            Message(
                role=MessageRole.ASSISTANT,
                content=[UnknownBlock(type="future_type", raw={"a": 1})],
            )
        )
    )

    assert "**Unrendered content — `future_type`**" in output


def test_an_unmodelled_block_that_carries_a_title_and_link_shows_them() -> None:
    """A placeholder where the snapshot served a source loses the one

    thing the reader could have used.
    """
    output = render_markdown(
        conversation(
            Message(
                role=MessageRole.ASSISTANT,
                content=[
                    UnknownBlock(
                        type="knowledge",
                        raw={
                            "title": "Amira AI | Dubai",
                            "url": "https://example.com/a",
                        },
                    )
                ],
            )
        )
    )

    assert "[Amira AI | Dubai](<https://example.com/a>)" in output
    assert "> (preserved in the JSON export)" not in output


def test_a_title_without_a_link_is_still_shown() -> None:
    output = render_markdown(
        conversation(
            Message(
                role=MessageRole.ASSISTANT,
                content=[UnknownBlock(type="knowledge", raw={"title": "A source"})],
            )
        )
    )

    assert "> A source" in output


def test_a_link_without_a_title_is_still_shown() -> None:
    output = render_markdown(
        conversation(
            Message(
                role=MessageRole.ASSISTANT,
                content=[
                    UnknownBlock(type="knowledge", raw={"url": "https://example.com/b"})
                ],
            )
        )
    )

    assert "> https://example.com/b" in output


def test_an_unmodelled_block_carrying_neither_keeps_its_placeholder() -> None:
    """Nothing to show means show nothing, not a fabricated label."""
    output = render_markdown(
        conversation(
            Message(
                role=MessageRole.ASSISTANT,
                content=[UnknownBlock(type="future_type", raw={"a": 1})],
            )
        )
    )

    assert "> (preserved in the JSON export)" in output


def test_a_bracket_in_a_title_cannot_break_the_link() -> None:
    output = render_markdown(
        conversation(
            Message(
                role=MessageRole.ASSISTANT,
                content=[
                    UnknownBlock(
                        type="knowledge",
                        raw={"title": "A [draft] post", "url": "https://example.com/c"},
                    )
                ],
            )
        )
    )

    assert r"[A \[draft\] post](<https://example.com/c>)" in output


def test_tool_recipient_is_shown_in_the_heading() -> None:
    output = render_markdown(
        conversation(
            Message(
                role=MessageRole.ASSISTANT,
                recipient="web.run",
                content=[CodeBlock(text='search("x")')],
            )
        )
    )

    assert "— to web.run" in output


def test_author_is_shown_for_tool_messages() -> None:
    output = render_markdown(
        conversation(text(MessageRole.TOOL, "result", author="web.run"))
    )

    assert "## Tool (web.run)" in output


def test_timestamp_is_rendered_when_present() -> None:
    output = render_markdown(
        conversation(
            text(
                MessageRole.USER,
                "hi",
                timestamp=datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
            )
        )
    )

    assert "2026-01-02T03:04:00+00:00" in output


def test_findings_are_counted_by_level() -> None:
    """Notes and warnings are counted apart: a reader needs to see at a
    glance whether anything actually went wrong.
    """
    output = render_markdown(
        conversation(text(MessageRole.USER, "hi")),
        findings=[
            finding("unrecognised_role", "a"),
            finding("message_has_no_content", "b", "m1"),
            finding("message_has_no_content", "c", "m2"),
        ],
    )

    assert "Extraction warnings: 1" in output
    assert "Extraction notes: 2" in output


def test_content_the_provider_did_not_serve_is_named_not_just_counted() -> None:
    """The file most people read must say what the provider withheld."""
    output = render_markdown(
        conversation(text(MessageRole.USER, "hi")),
        findings=[finding("attachment_withheld", "7 declared, none carried", "m1")],
    )

    assert "Referenced by the snapshot but not served:" in output
    assert "attachment_withheld: 7 declared, none carried" in output


def test_repeated_withholding_keeps_its_count() -> None:
    """The number of observations is evidence and must survive rendering."""
    withheld = finding(
        "tool_result_has_no_content", "search result carried no payload", "m1"
    ).model_copy(update={"occurrences": 19})

    output = render_markdown(
        conversation(text(MessageRole.USER, "hi")), findings=[withheld]
    )

    assert (
        "tool_result_has_no_content: search result carried no payload (x19)" in output
    )


def test_fidelity_findings_are_counted_but_not_named() -> None:
    """What this tool could not model is the archive's business, not the

    reader's: naming it here would put extraction detail in a
    dissemination copy.
    """
    output = render_markdown(
        conversation(text(MessageRole.USER, "hi")),
        findings=[finding("unmodelled_content_type", "knowledge preserved verbatim")],
    )

    assert "Extraction warnings: 1" in output
    assert "knowledge preserved verbatim" not in output
    assert "Referenced by the snapshot but not served" not in output


def test_a_snapshot_served_in_full_says_nothing_about_withholding() -> None:
    """Silence is the correct output when the provider served everything."""
    output = render_markdown(
        conversation(text(MessageRole.USER, "hi")),
        findings=[finding("literal_object_key", "kept as-is: title")],
    )

    assert "Referenced by the snapshot but not served" not in output
    assert "Extraction notes: 1" in output


def test_the_same_withholding_on_two_messages_is_merged_and_summed() -> None:
    """Message ids separate them in the record, but this file shows no

    ids, so two identical lines would read as a duplication bug. They
    merge, and the counts add, so no observation is lost.
    """
    output = render_markdown(
        conversation(text(MessageRole.USER, "hi")),
        findings=[
            finding(
                "tool_result_has_no_content", "memory_read carried no payload", "m1"
            ),
            finding(
                "tool_result_has_no_content", "memory_read carried no payload", "m2"
            ),
        ],
    )

    assert output.count("memory_read carried no payload") == 1
    assert "memory_read carried no payload (x2)" in output


def test_render_is_deterministic() -> None:
    conv = conversation(text(MessageRole.USER, "a"), text(MessageRole.ASSISTANT, "b"))

    assert render_markdown(conv) == render_markdown(conv)


def test_output_ends_with_a_single_newline() -> None:
    output = render_markdown(conversation(text(MessageRole.USER, "hi")))

    assert output.endswith("\n")
    assert not output.endswith("\n\n")


@pytest.mark.skipif(
    not (LOCAL / "minimal-2026-09-11.html").exists(),
    reason="local capture not present (see tests/fixtures/local/)",
)
def test_real_capture_renders_and_reconciles() -> None:
    html = (LOCAL / "minimal-2026-09-11.html").read_text(encoding="utf-8")
    result = parse(RawSource(url="https://chatgpt.com/share/x", content=html))
    output = render_markdown(result.conversation, findings=result.findings)

    assert "31 in snapshot, 18 rendered" in output
    assert "Omitted as hidden by the provider: 11" in output
    assert "Omitted as carrying no renderable content: 2" in output


def test_a_tool_call_renders_its_arguments() -> None:
    rendered = render_markdown(
        conversation(
            Message(
                role=MessageRole.ASSISTANT,
                content=[ToolUseBlock(name="web_search", input={"query": "drift"})],
            )
        )
    )

    assert "**Tool call — `web_search`**" in rendered
    assert '"query": "drift"' in rendered


def test_a_tool_result_the_snapshot_did_not_carry_says_so() -> None:
    rendered = render_markdown(
        conversation(
            Message(
                role=MessageRole.ASSISTANT,
                content=[ToolResultBlock(name="memory_read")],
            )
        )
    )

    assert "**Tool result — `memory_read`**" in rendered
    assert "carried no result" in rendered


def test_a_tool_result_renders_the_content_it_did_carry() -> None:
    rendered = render_markdown(
        conversation(
            Message(
                role=MessageRole.ASSISTANT,
                content=[
                    ToolResultBlock(
                        name="web_search", content=[TextBlock(text="nine results")]
                    )
                ],
            )
        )
    )

    assert "nine results" in rendered
