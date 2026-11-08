"""Tests for the Travelpayouts integration (no network)."""

from content_factory.integrations.travelpayouts import (
    TravelpayoutsClient,
    partner_url,
    redirect_page,
)


def test_client_configured():
    assert not TravelpayoutsClient(token="", marker="", trs="").configured()
    assert not TravelpayoutsClient(token="t", marker="", trs="1").configured()
    assert TravelpayoutsClient(token="t", marker="1", trs="2").configured()


def test_partner_url():
    assert partner_url({"code": "success", "partner_url": "https://x.tp.st/abc"}, "https://a") == "https://x.tp.st/abc"
    assert partner_url({"code": "failed", "partner_url": ""}, "https://a") == ""


def test_redirect_page_noindex_and_target():
    html = redirect_page("https://x.tp.st/abc", title="Redirecting")
    assert "noindex,nofollow" in html
    assert 'location.replace("https://x.tp.st/abc")' in html
    assert "Ad · affiliate link" in html
