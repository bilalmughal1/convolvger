import json

import pytest

from convolvger.providers.gemini import _batchexecute


def declared_length(frame: str) -> int:
    """The length the real endpoint declares: UTF-16 code units plus two.

    Measured against a live response across all three of its frames.
    """
    return len(frame.encode("utf-16-le")) // 2 + 2


def build(*frames: str, length: int | None = None) -> str:
    """Assemble a response body the way the endpoint does."""
    body = ")]}'"
    for frame in frames:
        size = declared_length(frame) if length is None else length
        body += f"\n{size}\n{frame}"
    return body


def envelope(rpc_id: str, payload: object) -> str:
    inner = json.dumps(payload, ensure_ascii=False)
    return json.dumps(
        [[_batchexecute.ENVELOPE_TAG, rpc_id, inner, None, None, None, "generic"]],
        ensure_ascii=False,
    )


TRAILERS = (
    json.dumps([["di", 466], ["af.httprm", 466, "5314567270682293609", 128]]),
    json.dumps([["e", 4, None, None, 2691]]),
)


def test_returns_the_payload_of_a_single_envelope() -> None:
    result = _batchexecute.decode(build(envelope("ujx1Bf", [["c_1", "r_1"], "hello"])))
    assert [item.rpc_id for item in result.envelopes] == ["ujx1Bf"]
    assert result.envelopes[0].payload == [["c_1", "r_1"], "hello"]


def test_payload_is_decoded_a_second_time_rather_than_left_a_string() -> None:
    result = _batchexecute.decode(build(envelope("ujx1Bf", {"nested": [1, 2]})))
    assert result.envelopes[0].payload == {"nested": [1, 2]}


def test_frame_length_is_counted_in_bytes_not_characters() -> None:
    """A conversation with non-ASCII text makes the two differ."""
    text = "Rs. 1,930,000 naïve résumé 日本語"
    frame = envelope("ujx1Bf", [text])
    assert len(frame) != len(frame.encode("utf-8"))

    result = _batchexecute.decode(build(frame, *TRAILERS))
    assert result.envelopes[0].payload == [text]


def test_trailers_are_skipped_without_comment() -> None:
    result = _batchexecute.decode(build(envelope("ujx1Bf", ["x"]), *TRAILERS))
    assert len(result.envelopes) == 1
    assert result.findings == []


def test_every_envelope_in_a_batch_is_returned() -> None:
    body = build(envelope("ujx1Bf", ["first"]), envelope("Te6DCf", ["second"]), *TRAILERS)
    result = _batchexecute.decode(body)
    assert [item.rpc_id for item in result.envelopes] == ["ujx1Bf", "Te6DCf"]


def test_an_unknown_row_tag_is_recorded_rather_than_dropped() -> None:
    unknown = json.dumps([["zz.qq", 1, "something"]])
    result = _batchexecute.decode(build(envelope("ujx1Bf", ["x"]), unknown))
    assert [item.code for item in result.findings] == ["unrecognised_stream_line"]
    assert "zz.qq" in result.findings[0].message


def test_a_body_without_the_prefix_is_refused() -> None:
    with pytest.raises(_batchexecute.BatchExecuteError, match="prefix"):
        _batchexecute.decode('[["wrb.fr","ujx1Bf","[]"]]')


def test_a_truncated_frame_is_refused_rather_than_silently_short() -> None:
    body = build(envelope("ujx1Bf", ["x"]))[:-5]
    with pytest.raises(_batchexecute.BatchExecuteError, match="not valid JSON"):
        _batchexecute.decode(body)


def test_a_wrong_declared_length_does_not_affect_decoding() -> None:
    """The length is read past: the JSON itself says where the frame ends."""
    body = build(envelope("ujx1Bf", ["kept"]), length=3)
    assert _batchexecute.decode(body).envelopes[0].payload == ["kept"]


def test_a_frame_holding_multibyte_text_survives_the_declared_length() -> None:
    """UTF-16 units, UTF-8 bytes and characters all differ here."""
    text = "Rs. 1,930,000 na\u00efve r\u00e9sum\u00e9 \U0001f600 \u65e5\u672c\u8a9e"
    frame = envelope("ujx1Bf", [text])
    assert len({len(frame), len(frame.encode("utf-8")), declared_length(frame)}) == 3

    assert _batchexecute.decode(build(frame)).envelopes[0].payload == [text]


def test_a_frame_that_is_not_json_is_refused() -> None:
    with pytest.raises(_batchexecute.BatchExecuteError, match="not valid JSON"):
        _batchexecute.decode(build("not json at all"))


def test_a_payload_that_is_not_json_is_refused() -> None:
    frame = json.dumps([["wrb.fr", "ujx1Bf", "{definitely not json", None]])
    with pytest.raises(_batchexecute.BatchExecuteError, match="not valid JSON"):
        _batchexecute.decode(build(frame))


def test_a_response_carrying_only_trailers_is_refused() -> None:
    with pytest.raises(_batchexecute.BatchExecuteError, match="carried no"):
        _batchexecute.decode(build(*TRAILERS))


def test_an_empty_body_is_refused() -> None:
    with pytest.raises(_batchexecute.BatchExecuteError, match="no frames"):
        _batchexecute.decode(")]}'\n\n")
