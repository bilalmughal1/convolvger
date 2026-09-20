"""Mapping of a Gemini share payload onto a Conversation.

The payload is JSPB: nested arrays with no keys, where meaning comes
from position alone. Every index below was measured against a live
share response and confirmed against a reduced fixture built from it.

A Gemini turn holds both sides of an exchange, so each one becomes two
messages: the prompt at ``[2][0][0]`` and the answer at
``[3][0][0][1][0]``. The answer is flat Markdown and was measured to be
complete -- every heading, bullet and table cell of the rendered reply
appears in it -- so the parallel block tree at ``[3][12]``, which
re-decomposes the same text for the web UI, is passed over without
comment. Nothing is lost by ignoring a second copy.

What is *not* in that Markdown is kept. Citations and the search
queries the model issued exist only in the payload, so they are
preserved in ``provider_metadata`` rather than dropped, pending a
canonical shape for citations across providers.

Unlike a keyed snapshot, this cannot be lossless by construction: with
no keys there is no "every field not mapped" to sweep up, so what is
preserved is enumerated by hand and this docstring is the record of
what was looked at. A position not named here is not modelled.
"""

from datetime import UTC, datetime
from typing import Any

from convolvger.core.findings import Finding, collapse, finding
from convolvger.core.models import Conversation, Message, MessageRole, TextBlock
from convolvger.core.results import ParseError, ParseResult
from convolvger.core.source import RawSource
from convolvger.providers.gemini._batchexecute import BatchExecuteError, decode

PROVIDER = "gemini"

CONVERSATION_RPC = "ujx1Bf"
"""The RPC a share page calls to load its conversation."""


def _at(node: Any, *indices: int) -> Any:
    """Return the value at a positional path, or None if it is absent."""
    for index in indices:
        if not isinstance(node, list) or len(node) <= index:
            return None
        node = node[index]
    return node


def _timestamp(value: Any) -> datetime | None:
    """Turn a ``[seconds, nanoseconds]`` pair into a datetime."""
    seconds = _at(value, 0)
    if not isinstance(seconds, int | float):
        return None
    nanos = _at(value, 1)
    fraction = nanos / 1_000_000_000 if isinstance(nanos, int | float) else 0.0
    return datetime.fromtimestamp(seconds + fraction, tz=UTC)


def _messages(turn: Any, index: int, findings: list[Finding]) -> list[Message]:
    response_id = _at(turn, 0, 1)
    identifier = response_id if isinstance(response_id, str) else None
    when = _timestamp(_at(turn, 4))

    prompt = _at(turn, 2, 0, 0)
    answer = _at(turn, 3, 0, 0, 1, 0)

    built: list[Message] = []
    if isinstance(prompt, str) and prompt:
        built.append(
            Message(role=MessageRole.USER, timestamp=when, content=[TextBlock(text=prompt)])
        )
    else:
        findings.append(
            finding("message_has_no_content", f"turn {index} carried no prompt text")
        )

    metadata: dict[str, Any] = {}
    content_id = _at(turn, 3, 0, 0, 0)
    if isinstance(content_id, str):
        metadata["response_content_id"] = content_id
    parent = _at(turn, 1)
    if parent is not None:
        metadata["parent"] = parent
    citations = _at(turn, 3, 0, 0, 2, 1)
    if citations:
        metadata["citations"] = citations
    queries = _at(turn, 3, 1)
    if queries:
        metadata["search_queries"] = [query[0] for query in queries if _at(query, 0)]

    if isinstance(answer, str) and answer:
        built.append(
            Message(
                id=identifier,
                role=MessageRole.ASSISTANT,
                timestamp=when,
                content=[TextBlock(text=answer)],
                provider_metadata=metadata,
            )
        )
    else:
        findings.append(
            finding(
                "message_has_no_content",
                f"turn {index} carried no answer text",
                message_id=identifier,
            )
        )
    return built


def parse(source: RawSource) -> ParseResult:
    """Map a batchexecute share response onto a Conversation."""
    findings: list[Finding] = []
    try:
        result = decode(source.content)
    except BatchExecuteError as error:
        raise ParseError(str(error), findings=findings) from error

    payloads = [item.payload for item in result.envelopes if item.rpc_id == CONVERSATION_RPC]
    if not payloads:
        raise ParseError(
            f"Response carried no {CONVERSATION_RPC} conversation payload",
            findings=result.findings,
        )
    findings.extend(result.findings)

    if payloads[0] is None:
        raise ParseError(
            "Share carried no conversation (deleted, never existed, or made private)",
            findings=findings,
        )

    root = _at(payloads[0], 0)
    turns = _at(root, 1)
    if not isinstance(turns, list) or not turns:
        raise ParseError("Conversation payload carried no turns", findings=findings)

    messages: list[Message] = []
    for index, turn in enumerate(turns):
        messages.extend(_messages(turn, index, findings))

    stamps = [message.timestamp for message in messages if message.timestamp is not None]
    title = _at(root, 2, 1)
    share_id = _at(root, 3)
    model = _at(root, 2, 7, 2)

    metadata: dict[str, Any] = {}
    if isinstance(model, str):
        metadata["model"] = model
    if isinstance(share_id, str):
        metadata["share_id"] = share_id
    retrieved = _timestamp(_at(root, 4))
    if retrieved is not None:
        metadata["payload_timestamp"] = retrieved.isoformat()

    conversation = Conversation(
        id=_at(turns[0], 0, 0),
        provider=PROVIDER,
        source_url=source.url,
        title=title if isinstance(title, str) else None,
        created_at=min(stamps) if stamps else None,
        updated_at=max(stamps) if stamps else None,
        messages=messages,
        provider_metadata=metadata,
    )
    return ParseResult(conversation=conversation, findings=collapse(findings))
