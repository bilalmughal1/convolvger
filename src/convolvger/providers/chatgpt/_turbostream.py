"""Decoder for React Router turbo-stream payloads.

ChatGPT share pages embed their loader data as a flat, deduplicated
array. Objects use ``{"_<key index>": <value index>}`` form, where both
the key and the value are indices into that array. Primitives are stored
in the array too, so a value slot is always an index, never a literal.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from convolvger.core import jsonload
from convolvger.core.errors import ConvolvgerError
from convolvger.core.findings import Finding, finding

_ENQUEUE_RE = re.compile(r'streamController\.enqueue\("((?:[^"\\]|\\.)*)"\)')
_DEFERRED_RE = re.compile(r"^P(\d+):")
_KEY_RE = re.compile(r"_([0-9]+)")

NULL_SENTINEL = -5


class TurboStreamError(ConvolvgerError):
    """Raised when a turbo-stream payload cannot be decoded."""


@dataclass
class DecodeResult:
    value: Any
    findings: list[Finding] = field(default_factory=list)


def _is_ref(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def extract_payloads(html: str) -> list[str]:
    """Return the unescaped turbo-stream chunks embedded in an HTML page."""
    matches = _ENQUEUE_RE.findall(html)
    if not matches:
        raise TurboStreamError("No turbo-stream payload found in source")
    return [json.loads(f'"{match}"') for match in matches]


def parse_stream(payloads: list[str]) -> tuple[list[Any], list[Finding]]:
    """Split chunks into the leading flat array and any deferred lines."""
    findings: list[Finding] = []
    lines = [
        line for payload in payloads for line in payload.split("\n") if line.strip()
    ]
    if not lines:
        raise TurboStreamError("Turbo-stream payload is empty")

    seen_constants: set[str] = set()

    def note_constant(token: str) -> None:
        if token in seen_constants:
            return
        seen_constants.add(token)
        findings.append(
            finding("non_standard_json_constant", f"{token} stored as null")
        )

    try:
        flat = jsonload.loads(lines[0], parse_constant=note_constant)
    except json.JSONDecodeError as exc:
        raise TurboStreamError(
            f"Leading turbo-stream line is not JSON: {exc.msg}"
        ) from exc
    except jsonload.JSONNestingError as exc:
        raise TurboStreamError(
            "Leading turbo-stream line is nested too deeply"
        ) from exc

    if not isinstance(flat, list):
        raise TurboStreamError(f"Expected a flat array, got {type(flat).__name__}")

    for line in lines[1:]:
        match = _DEFERRED_RE.match(line)
        if match:
            findings.append(
                finding(
                    "deferred_slot_not_merged",
                    f"slot {match.group(1)} was not merged",
                )
            )
        else:
            findings.append(finding("unrecognised_stream_line", "line ignored"))

    return flat, findings


def decode(flat: list[Any]) -> DecodeResult:
    """Resolve a flat turbo-stream array into plain Python data."""
    if not flat:
        raise TurboStreamError("Flat array is empty")

    findings: list[Finding] = []
    resolved: dict[int, Any] = {}
    active: set[int] = set()

    def at(index: int) -> Any:
        if index < 0:
            if index == NULL_SENTINEL:
                return None
            raise TurboStreamError(f"Unknown turbo-stream sentinel: {index}")
        if index >= len(flat):
            raise TurboStreamError(f"Reference out of range: {index}")
        if index in resolved:
            return resolved[index]
        if index in active:
            raise TurboStreamError(f"Reference cycle at index {index}")

        active.add(index)
        value = convert(flat[index])
        active.discard(index)
        resolved[index] = value
        return value

    def key_name(key: str) -> str:
        if key.startswith("_"):
            index = _KEY_RE.fullmatch(key)
            if index is None:
                raise TurboStreamError(f"Malformed key reference: {key!r}")
            return str(at(int(index.group(1))))
        findings.append(finding("literal_object_key", f"kept as-is: {key}"))
        return key

    def marker(node: list[Any]) -> Any:
        if node[0] == "P":
            findings.append(finding("deferred_value_unresolved", f"value {node[1:]}"))
            return None
        raise TurboStreamError(f"Unsupported turbo-stream marker: {node[0]!r}")

    def convert(node: Any) -> Any:
        if isinstance(node, dict):
            return {
                key_name(key): at(ref) if _is_ref(ref) else ref
                for key, ref in node.items()
            }
        if isinstance(node, list):
            if node and node[0] == "P" and len(node) == 2 and _is_ref(node[1]):
                return marker(node)
            return [at(item) if _is_ref(item) else item for item in node]
        return node

    # Resolution recurses once per reference followed, so a long enough
    # chain exhausts the stack; that is a payload this decoder refuses,
    # not a crash.
    try:
        value = at(0)
    except RecursionError as exc:
        raise TurboStreamError("References are nested too deeply") from exc
    # The flat array is two levels deep whatever it encodes, so the limit
    # every other provider's JSON gets is applied to what it decodes to.
    try:
        jsonload.check_depth(value)
    except jsonload.JSONNestingError as exc:
        raise TurboStreamError(f"Decoded payload is refused: {exc}") from exc
    return DecodeResult(value=value, findings=findings)


def decode_html(html: str) -> DecodeResult:
    """Extract and decode the turbo-stream payload from an HTML page."""
    flat, findings = parse_stream(extract_payloads(html))
    result = decode(flat)
    return DecodeResult(value=result.value, findings=findings + result.findings)
