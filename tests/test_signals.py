"""Offline tests for the account-signal engine (the account-in core)."""

from revalign_teardown import signals
from revalign_teardown.resolve import _score, _tokens

TODAY = "2026-07-21"


def _f(fcc_id, date, app="x=="):
    return {"fcc_id": fcc_id, "grant_date": date, "application_id": app,
            "grantee_code": "2AJ2X"}


def test_product_code_strips_grantee_prefix():
    assert signals.product_code("2AJ2X-WM50", "2AJ2X") == "WM50"
    assert signals.product_code("SS3-DEN225", "SS3") == "DEN225"
    assert signals.product_code("SS3DEN225", "SS3") == "DEN225"


def test_in_pipeline_headline_fires_on_locked_recent_filing():
    # granted 67 days ago -> under the 180-day confidentiality clock
    sig = signals.compute_signals([_f("2AJ2X-WM50", "2026-05-15")], TODAY, "2AJ2X")
    assert sig["in_pipeline"]
    assert "pipeline" in sig["headline"].lower()
    assert sig["filings"][0]["_released"] is False


def test_unlocking_headline_when_photos_about_to_release():
    # granted ~150 days ago -> unlocks in ~30 days (< 45-day imminent window)
    sig = signals.compute_signals([_f("2AJ2X-WM60", "2026-02-25")], TODAY, "2AJ2X")
    assert sig["unlocking"]
    assert "imminent" in sig["headline"].lower()


def test_ramping_headline():
    fs = [_f("2AJ2X-A%d" % i, "2026-0%d-01" % ((i % 6) + 1)) for i in range(5)]
    fs.append(_f("2AJ2X-OLD", "2019-01-01"))
    sig = signals.compute_signals(fs, TODAY, "2AJ2X")
    # released older ones + several within the year -> ramping or pipeline signal
    assert sig["recent_count_365"] >= 2


def test_quiet_headline_when_all_old():
    sig = signals.compute_signals(
        [_f("2AJ2X-WS30", "2019-05-08"), _f("2AJ2X-WS102", "2016-11-14")],
        TODAY, "2AJ2X")
    assert sig["recent_count_365"] == 0
    assert "quiet" in sig["headline"].lower()


def test_new_family_detection():
    sig = signals.compute_signals(
        [_f("2AJ2X-WM50", "2026-05-15"), _f("2AJ2X-WS30", "2019-05-08")],
        TODAY, "2AJ2X")
    assert "WM50" in sig["new_families"]
    assert "WS30" not in sig["new_families"]  # old, not a new family this year


def test_empty_filings():
    sig = signals.compute_signals([], TODAY, "2AJ2X")
    assert sig["total"] == 0
    assert "no fcc filings" in sig["headline"].lower()


def test_brief_renders_verifiable_links():
    sig = signals.compute_signals([_f("2AJ2X-WM50", "2026-05-15")], TODAY, "2AJ2X")
    brief = signals.render_brief("Whoop", "Whoop Inc.", "2AJ2X", sig,
                                 exhibit_url=lambda fid, app: "https://apps.fcc.gov/x?%s" % fid)
    assert "Whoop" in brief and "2AJ2X-WM50" in brief
    assert "apps.fcc.gov" in brief


def test_resolve_scoring_prefers_exact_brand():
    # "Eight Sleep" should score its own entity above "Casper Sleep"
    assert _score("Eight Sleep", "Eight Sleep Inc") > _score("Eight Sleep", "Casper Sleep Inc.")


def test_resolve_tokens_drop_corporate_filler():
    assert _tokens("SZ DJI Technology Co., Ltd.") == {"sz", "dji"}
