"""URL recognition for Perplexity shared threads.

Only ``/search/<id>`` links are recognised: the form of the one share
measured. Its id was a UUID, but it is not validated -- the ChatGPT
adapter learned that a stricter pattern risks refusing links that work,
and the provider's own answer is the authority on whether an id exists.

The page loads its thread from ``/rest/thread/<id>``. Measured from a
signed-out browser, with no cookie or token, that request answered with
the whole thread as JSON. Asked by this tool directly, the page and the
endpoint alike answered with a Cloudflare challenge, whatever headers
were sent, so the thread is captured in the browser rather than fetched,
as Claude's is. ``CAPTURE`` tells the bookmarklet where to look.

The query is the one the page sent, copied whole: among other things it
names the kinds of block the page can show, and the answer was measured
in one of them. ``limit=20`` means a thread longer than twenty entries
arrives in more than one page; only the first is read, and the payload
says whether more exist.
"""

from urllib.parse import urlsplit

from convolvger.capture.rules import CaptureRule

SHARE_HOSTS = frozenset({"perplexity.ai"})
PAGE_HOSTS = frozenset({"www.perplexity.ai"})
"""Where a share page was seen, as the browser names the host."""

THREAD_API = (
    "https://www.perplexity.ai/rest/thread/{share_id}?"
    "with_parent_info=true&with_schematized_response=true&version=2.18"
    "&source=default&limit=20&offset=0&from_first=false"
    "&with_first_entry=true&with_latest_entry=false"
    "&supported_block_use_cases=answer_modes"
    "&supported_block_use_cases=media_items"
    "&supported_block_use_cases=inline_entity_cards"
    "&supported_block_use_cases=place_widgets"
    "&supported_block_use_cases=finance_widgets"
    "&supported_block_use_cases=news_widgets"
    "&supported_block_use_cases=shopping_widgets"
    "&supported_block_use_cases=search_result_widgets"
    "&supported_block_use_cases=inline_images"
    "&supported_block_use_cases=inline_assets"
    "&supported_block_use_cases=placeholder_cards"
    "&supported_block_use_cases=diff_blocks"
    "&supported_block_use_cases=entity_group_v2"
    "&supported_block_use_cases=refinement_filters"
    "&supported_block_use_cases=canvas_mode"
    "&supported_block_use_cases=maps_preview"
    "&supported_block_use_cases=answer_tabs"
    "&supported_block_use_cases=preserve_latex"
    "&supported_block_use_cases=in_context_suggestions"
    "&supported_block_use_cases=pending_followups"
    "&supported_block_use_cases=inline_claims"
    "&supported_block_use_cases=unified_assets"
    "&supported_block_use_cases=workflow_steps"
    "&supported_block_use_cases=workflow_widgets"
    "&supported_block_use_cases=navigation_results"
    "&supported_block_use_cases=background_agents"
)

CAPTURE = CaptureRule(hosts=PAGE_HOSTS, path=r"^/search/([^/?#]+)", api=THREAD_API)


def is_share_url(url: str) -> bool:
    """Return True if ``url`` is a Perplexity shared thread link."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
    except ValueError:
        return False
    if parts.scheme.lower() != "https":
        return False
    host = host.rstrip(".").removeprefix("www.")
    if host not in SHARE_HOSTS:
        return False
    segments = [segment for segment in parts.path.split("/") if segment]
    return len(segments) == 2 and segments[0] == "search"


def share_id(url: str) -> str | None:
    """Return the thread id in ``url``, or None if it is not a share link."""
    if not is_share_url(url):
        return None
    return [segment for segment in urlsplit(url).path.split("/") if segment][1]
