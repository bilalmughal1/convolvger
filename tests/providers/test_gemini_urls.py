import pytest

from convolvger.providers.gemini import _urls

CANONICAL = "https://gemini.google.com/share/09bcf760b07b"
ALIAS = "https://g.co/gemini/share/09bcf760b07b"
SHORT = "https://share.gemini.google/94ESiKYXbGiV"


@pytest.mark.parametrize("url", [CANONICAL, ALIAS, SHORT])
def test_recognises_every_observed_share_form(url: str) -> None:
    assert _urls.is_share_url(url) is True


def test_canonical_form_carries_the_id() -> None:
    assert _urls.share_id(CANONICAL) == "09bcf760b07b"


def test_alias_form_carries_the_same_id_as_the_canonical_form() -> None:
    """g.co is a path alias, not a shortener: it redirects carrying this id."""
    assert _urls.share_id(ALIAS) == _urls.share_id(CANONICAL)


def test_shortened_form_is_recognised_but_yields_no_id() -> None:
    """Its token is not the conversation id; only a redirect reveals that."""
    assert _urls.is_share_url(SHORT) is True
    assert _urls.share_id(SHORT) is None


def test_query_and_fragment_do_not_affect_the_id() -> None:
    """The skid the shortener appends is disposable: the id is the path."""
    url = f"{CANONICAL}?skid=07cf69f5-d907-47d0-9aa6-8089e32d09d9#top"
    assert _urls.share_id(url) == "09bcf760b07b"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.gemini.google.com/share/09bcf760b07b",
        "https://gemini.google.com./share/09bcf760b07b",
    ],
)
def test_host_is_normalised_before_matching(url: str) -> None:
    assert _urls.share_id(url) == "09bcf760b07b"


@pytest.mark.parametrize(
    "url",
    [
        "http://gemini.google.com/share/09bcf760b07b",
        "https://gemini.google.com/app/09bcf760b07b",
        "https://gemini.google.com/share",
        "https://gemini.google.com/share/09bcf760b07b/extra",
        "https://g.co/gemini/09bcf760b07b",
        "https://share.gemini.google/",
        "https://chatgpt.com/share/09bcf760b07b",
    ],
)
def test_rejects_urls_that_are_not_share_links(url: str) -> None:
    assert _urls.is_share_url(url) is False


def test_share_id_is_none_for_an_unrecognised_url() -> None:
    assert _urls.share_id("https://example.com/share/09bcf760b07b") is None


def test_a_malformed_url_is_rejected_rather_than_raising() -> None:
    assert _urls.is_share_url("https://[") is False
