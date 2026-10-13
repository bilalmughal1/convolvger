"""Reading a provider's response without trusting its size.

``httpx`` reads a whole body into memory on ``get``, so a response of
any size is accepted. Every fetcher reads through here instead, and a
body larger than ``MAX_BYTES`` (32 MiB) is refused before it is all
held. The number is the one the capture listener puts on a body posted
from the browser. What is counted differs: the listener counts the
posted JSON, escapes and all, and this counts the response body, so the
same conversation can fall under one limit and over the other.

The count is of decoded bytes -- after any ``Content-Encoding`` is
undone -- so a small compressed body that expands enormously is
refused too. A declared ``Content-Length`` over the limit is refused
before anything is read; the count is still kept while reading,
because a header can be absent or wrong.

Status codes are not looked at here. What a 400 or an empty 200 means
differs between providers, so each fetcher keeps its own mapping and
its own errors, and names the error a refusal here should raise.
"""

from typing import Any

import httpx

MAX_BYTES = 32 * 1024 * 1024


def read(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    too_large: type[Exception],
    **options: Any,
) -> tuple[httpx.Response, str]:
    """Send one request and return the response with its body as text.

    The body is decoded as ``Response.text`` would decode it. The
    returned response has been closed, so its own ``text`` and
    ``content`` are not available; use the string returned beside it.
    """
    with client.stream(method, url, **options) as response:
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_BYTES:
            raise too_large(f"Response declares {declared} bytes, over the limit")
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                raise too_large(f"Response is over the limit of {MAX_BYTES} bytes")
            chunks.append(chunk)
    body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
    return response, body
