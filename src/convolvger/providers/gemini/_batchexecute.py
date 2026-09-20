"""Decoder for Google's batchexecute response envelope.

Gemini share conversations arrive from a batchexecute endpoint, whose
body was measured as::

    )]}'
    <length>
    <frame>
    <length>
    <frame>

Each frame is a JSON array of rows. A row tagged ``wrb.fr`` carries the
RPC id at index 1 and the response at index 2 -- as a JSON *string*, so
the payload needs a second decode. Rows tagged ``di``, ``af.httprm`` or
``e`` are Google's own diagnostics and end markers; they carry nothing
this tool needs and are skipped without comment.

The declared length is read past rather than used. Measured against a
live response it was neither the frame's character count nor its length
in UTF-8 bytes: for all three frames it came to the UTF-16 code unit
count plus two, which is what JavaScript's ``String.length`` reports
for the frame plus its surrounding newlines. Slicing on it means
encoding the whole body a second way to honour a number that only
restates where the JSON already ends, and getting it wrong cuts the
frame mid-string. Decoding each document where it starts and letting
the parser find its end needs no such agreement, and a frame cut short
still fails -- as an incomplete document rather than a short slice.

The response is not byte-stable: two identical requests returned bodies
differing in length, so nothing here may assume a fixed size.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from convolvger.core.errors import ConvolvgerError
from convolvger.core.findings import Finding, finding

PREFIX = ")]}'"
ENVELOPE_TAG = "wrb.fr"
TRAILER_TAGS = frozenset({"di", "af.httprm", "e"})


class BatchExecuteError(ConvolvgerError):
    """Raised when a batchexecute response cannot be decoded."""


@dataclass
class Envelope:
    """One ``wrb.fr`` row: an RPC id and its decoded payload."""

    rpc_id: str
    payload: Any


@dataclass
class DecodeResult:
    envelopes: list[Envelope]
    findings: list[Finding] = field(default_factory=list)


def documents(raw: str) -> list[Any]:
    """Return every JSON document in a batchexecute body, in order."""
    if not raw.startswith(PREFIX):
        raise BatchExecuteError("Response does not begin with the batchexecute prefix")

    decoder = json.JSONDecoder()
    found: list[Any] = []
    position = len(PREFIX)
    while position < len(raw):
        while position < len(raw) and raw[position].isspace():
            position += 1
        # The declared length restates where the JSON ends; read past it.
        while position < len(raw) and raw[position].isdigit():
            position += 1
        while position < len(raw) and raw[position].isspace():
            position += 1
        if position >= len(raw):
            break

        try:
            document, position = decoder.raw_decode(raw, position)
        except json.JSONDecodeError as error:
            raise BatchExecuteError(f"Frame is not valid JSON: {error}") from error
        found.append(document)

    if not found:
        raise BatchExecuteError("Response carried no frames")
    return found


def decode(raw: str) -> DecodeResult:
    """Return every ``wrb.fr`` envelope in a batchexecute response."""
    envelopes: list[Envelope] = []
    findings: list[Finding] = []

    for rows in documents(raw):
        if not isinstance(rows, list):
            raise BatchExecuteError("Frame is not a JSON array")

        for row in rows:
            if not isinstance(row, list) or not row:
                findings.append(finding("unrecognised_stream_line", "empty frame row"))
                continue
            tag = row[0]
            if tag in TRAILER_TAGS:
                continue
            if tag != ENVELOPE_TAG:
                findings.append(
                    finding("unrecognised_stream_line", f"frame row tagged {tag!r}")
                )
                continue
            if len(row) < 3 or not isinstance(row[1], str):
                raise BatchExecuteError(f"Malformed {ENVELOPE_TAG} row: {row[:2]}")

            if row[2] is None:
                # Measured: an unknown or malformed share id returns 200 with
                # exactly this shape. The envelope is well formed and carries
                # nothing, which is a fact about the conversation rather than
                # about the encoding, so it is passed on rather than raised.
                envelopes.append(Envelope(rpc_id=row[1], payload=None))
                continue
            if not isinstance(row[2], str):
                raise BatchExecuteError(f"Malformed {ENVELOPE_TAG} row: {row[:2]}")

            try:
                payload = json.loads(row[2])
            except json.JSONDecodeError as error:
                raise BatchExecuteError(
                    f"Payload of {row[1]!r} is not valid JSON: {error}"
                ) from error
            envelopes.append(Envelope(rpc_id=row[1], payload=payload))

    if not envelopes:
        raise BatchExecuteError(f"Response carried no {ENVELOPE_TAG} envelope")
    return DecodeResult(envelopes=envelopes, findings=findings)
