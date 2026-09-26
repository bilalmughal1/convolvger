"""Mapping of a Grok share payload onto a Conversation.

The payload is keyed JSON, measured as::

    {"conversation": {"conversationId", "title", "createTime", ...},
     "responses": [{"responseId", "sender", "message", ...}, ...],
     "isPublic", "allowIndexing", "sharedSubagents", ...}

Each response is one message. Being keyed, it can be lossless by
construction the way the Claude snapshot is: a key is mapped only where
the canonical field holds its value exactly, and every other key lands
in ``provider_metadata``. ``sender`` is deliberately left there too. It
was seen as ``human``, ``ASSISTANT`` and ``assistant`` within one
conversation, and normalising it into a role discards which casing the
provider sent -- a fact worth keeping about a provider that is not
consistent with itself.

What the model does not render is kept rather than dropped. Search
results, cited X posts, card attachments and the model name live only
in the payload and go to ``provider_metadata``, as Gemini's citations
do; no renderer reads them. The reasoning trace in ``steps`` and any
tool responses are kept there as well, but flagged, because they are
content this version does not model rather than annotations of content
it does.

An answer's text carries its citations inline, as
``<grok:render type="render_inline_citation" card_id=...>`` markup
pointing into ``cardAttachmentsJson``. Left in, that markup reaches the
Markdown a reader sees. A citation whose card the payload carries is
therefore lifted out of the visible text, and the served ``message`` is
kept verbatim in ``provider_metadata`` beside it, so nothing the
provider sent is lost. Markup of any other shape is left in the text
and flagged: text this version cannot account for is shown rather than
hidden.

The first response's ``parentResponseId`` was observed naming a response
outside the share -- the share had been copied from another
conversation. It is preserved and not reported, since it describes where
the conversation came from rather than anything missing from it.
"""

import json
import re
from datetime import datetime
from typing import Any

from convolvger.core.findings import Finding, collapse, finding
from convolvger.core.models import (
    ContentBlock,
    Conversation,
    Message,
    MessageRole,
    TextBlock,
)
from convolvger.core.results import ParseError, ParseResult
from convolvger.core.source import RawSource

PROVIDER = "grok"

ROLES = {"human": MessageRole.USER, "assistant": MessageRole.ASSISTANT}
"""Senders observed, after casing is folded. Anything else is recorded, not guessed."""

ENVELOPE_MAPPED_KEYS = frozenset({"conversation", "responses"})
CONVERSATION_MAPPED_KEYS = frozenset(
    {"conversationId", "title", "createTime", "modifyTime"}
)
RESPONSE_MAPPED_KEYS = frozenset({"responseId", "message", "createTime"})

ATTACHMENT_KEYS = (
    "fileAttachments",
    "imageAttachments",
    "generatedImageUrls",
    "imageEditUris",
)
"""Lists that name files or images the payload refers to but never carries.

Each holds identifiers or URLs, not content, and a URL is never
dereferenced to fill the gap. A non-empty one is reported as withheld.
"""

UNMODELLED_KEYS = ("steps", "toolResponses", "inputChunks", "outputChunks")
"""Content, rather than annotation, that this version has no block for.

``steps`` is the trace the web UI shows beside a thinking answer:
headers, prose, and the searches issued with their results. It is kept
whole in ``provider_metadata`` and flagged, not mapped, because its
shape was seen in a single conversation.
"""

MESSAGE_KEY = "message"

INLINE_CITATION = "render_inline_citation"
RENDER = re.compile(r"<grok:render\b([^>]*)>.*?</grok:render>", re.DOTALL)
ATTRIBUTE = re.compile(r'([\w-]+)="([^"]*)"')
MARKUP = "<grok:"


def carries_nothing(payload: Any) -> bool:
    """True for a well-formed share that holds no responses.

    A real public share was seen answering 200 with its title and an
    empty ``responses`` list. The envelope is intact and the
    conversation is absent, so it is treated as a missing share: an
    archive of a title alone would pass an empty conversation off as a
    real one.
    """
    if not isinstance(payload, dict):
        return False
    responses = payload.get("responses")
    return isinstance(responses, list) and not responses


def _extras(source: dict[str, Any], mapped: frozenset[str]) -> dict[str, Any]:
    return {key: value for key, value in source.items() if key not in mapped}


def _unconsumed(source: dict[str, Any], mapped: frozenset[str]) -> set[str]:
    """Return the mapped keys whose value the canonical field could not hold.

    A key counts as mapped only when its value was actually taken: a
    title that is not a string, or a time that does not parse, stays in
    ``provider_metadata`` rather than vanishing between the two.
    """
    refused: set[str] = set()
    for key in mapped & source.keys():
        value = source[key]
        if key.endswith("Time"):
            if _timestamp(value) is None:
                refused.add(key)
        elif not isinstance(value, str):
            refused.add(key)
    return refused


def _timestamp(value: Any) -> datetime | None:
    """Read an ISO 8601 instant, or record nothing rather than guess."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _role(sender: Any, findings: list[Finding], message_id: str | None) -> MessageRole:
    known = ROLES.get(sender.lower()) if isinstance(sender, str) else None
    if known is not None:
        return known
    findings.append(
        finding("unrecognised_role", f"{sender!r} preserved as unknown", message_id)
    )
    return MessageRole.UNKNOWN


def _card_ids(
    raw: dict[str, Any], findings: list[Finding], message_id: str | None
) -> set[str]:
    """Return the ids of the cards a response carries.

    Each card arrives as a JSON *string* inside a list. The strings stay
    in ``provider_metadata`` exactly as served; this only reads them.
    """
    cards = raw.get("cardAttachmentsJson")
    if not isinstance(cards, list):
        return set()

    found: set[str] = set()
    for card in cards:
        try:
            decoded = json.loads(card) if isinstance(card, str) else None
        except json.JSONDecodeError:
            decoded = None
        identifier = decoded.get("id") if isinstance(decoded, dict) else None
        if isinstance(identifier, str):
            found.add(identifier)
        else:
            findings.append(
                finding(
                    "unmodelled_content_type",
                    "card attachment without a readable id preserved verbatim",
                    message_id,
                )
            )
    return found


def _lift_citations(
    text: str, cards: set[str], findings: list[Finding], message_id: str | None
) -> str:
    """Return ``text`` without the inline citations whose card the payload carries.

    The served string is not kept here; the caller keeps it whole
    whenever the result differs from it.
    """
    kept: list[str] = []
    position = 0
    left = 0

    for match in RENDER.finditer(text):
        attributes = dict(ATTRIBUTE.findall(match.group(1)))
        kind = attributes.get("type")
        if kind == INLINE_CITATION and attributes.get("card_id") in cards:
            kept.append(text[position : match.start()])
            position = match.end()
            continue
        left += 1
        reason = (
            "whose card was not carried" if kind == INLINE_CITATION else f"{kind!r}"
        )
        findings.append(
            finding(
                "unmodelled_content_type",
                f"grok:render {reason} preserved in text",
                message_id,
            )
        )

    kept.append(text[position:])
    visible = "".join(kept)
    if visible.count(MARKUP) > left:
        findings.append(
            finding(
                "unmodelled_content_type",
                "unrecognised grok markup preserved in text",
                message_id,
            )
        )
    return visible


def _report_unserved(
    raw: dict[str, Any], findings: list[Finding], message_id: str | None
) -> None:
    for key in ATTACHMENT_KEYS:
        declared = raw.get(key)
        if isinstance(declared, list) and declared:
            findings.append(
                finding(
                    "attachment_withheld",
                    f"{len(declared)} {key} declared, none carried",
                    message_id,
                )
            )

    for key in UNMODELLED_KEYS:
        if raw.get(key):
            findings.append(
                finding(
                    "unmodelled_content_type",
                    f"{key} preserved in provider_metadata",
                    message_id,
                )
            )

    if raw.get("partial") is True:
        findings.append(
            finding("message_content_withheld", "response marked partial", message_id)
        )
    errors = raw.get("streamErrors")
    if isinstance(errors, list) and errors:
        findings.append(
            finding(
                "message_content_withheld",
                f"{len(errors)} stream error(s) recorded",
                message_id,
            )
        )


def _message(raw: dict[str, Any], findings: list[Finding]) -> Message:
    identifier = raw.get("responseId")
    message_id = identifier if isinstance(identifier, str) else None
    mapped = set(RESPONSE_MAPPED_KEYS) - _unconsumed(raw, RESPONSE_MAPPED_KEYS)

    served = raw.get(MESSAGE_KEY)
    content: list[ContentBlock] = []
    text: str | None = None
    if isinstance(served, str):
        text = _lift_citations(
            served, _card_ids(raw, findings, message_id), findings, message_id
        )
        if text:
            content.append(TextBlock(text=text))

    if not content or text != served:
        # Mapped only when a text block holds the served string exactly.
        # An empty string makes no block, and lifted citations change the
        # text, so in both cases the string itself is kept.
        mapped.discard(MESSAGE_KEY)

    if not content:
        findings.append(
            finding("message_has_no_content", "no message text", message_id)
        )

    _report_unserved(raw, findings, message_id)

    metadata = _extras(raw, frozenset(mapped))

    return Message(
        id=message_id,
        role=_role(raw.get("sender"), findings, message_id),
        timestamp=_timestamp(raw.get("createTime")),
        content=content,
        provider_metadata=metadata,
    )


def parse(source: RawSource) -> ParseResult:
    """Convert a Grok share payload into a Conversation."""
    try:
        envelope = json.loads(source.content)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Share payload is not valid JSON: {exc}") from exc

    if not isinstance(envelope, dict):
        raise ParseError("Share payload is not a JSON object")

    header = envelope.get("conversation")
    raw_responses = envelope.get("responses")
    if not isinstance(header, dict) or not isinstance(raw_responses, list):
        raise ParseError("Share payload has no conversation and responses")

    if carries_nothing(envelope):
        raise ParseError(
            "Share carried no conversation (deleted, never existed, or made private)"
        )

    findings: list[Finding] = []
    messages: list[Message] = []
    unreadable: list[Any] = []
    for raw in raw_responses:
        if isinstance(raw, dict):
            messages.append(_message(raw, findings))
        else:
            unreadable.append(raw)
            findings.append(
                finding(
                    "unmodelled_content_type",
                    f"{type(raw).__name__} response preserved in provider_metadata",
                )
            )

    metadata = _extras(envelope, ENVELOPE_MAPPED_KEYS)
    metadata["conversation"] = _extras(
        header, CONVERSATION_MAPPED_KEYS - _unconsumed(header, CONVERSATION_MAPPED_KEYS)
    )
    if unreadable:
        metadata["unreadable_responses"] = unreadable

    if envelope.get("sharedSubagents"):
        findings.append(
            finding(
                "unmodelled_content_type",
                "sharedSubagents preserved in provider_metadata",
            )
        )

    identifier = header.get("conversationId")
    title = header.get("title")
    conversation = Conversation(
        id=identifier if isinstance(identifier, str) else None,
        provider=PROVIDER,
        source_url=source.url,
        title=title if isinstance(title, str) else None,
        created_at=_timestamp(header.get("createTime")),
        updated_at=_timestamp(header.get("modifyTime")),
        messages=messages,
        provider_metadata=metadata,
    )
    return ParseResult(conversation=conversation, findings=collapse(findings))
