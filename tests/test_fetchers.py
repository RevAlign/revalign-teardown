"""Offline tests for the fcc.report parser + fetcher selection. No network."""

from revalign_teardown import fetchers

# shaped like a real fcc.report company page (date | FCC ID | company | ...)
REPORT_HTML = """
<table>
<tr><td>2026-05-15</td><td>FCC ID 2AJ2X-WM50</td><td>Whoop Inc.</td><td>NEW DEVICE</td></tr>
<tr><td>2025-05-08</td><td>FCC ID 2AJ2X-WS50</td><td>Whoop Inc.</td><td>NEW DEVICE</td></tr>
<tr><td>2016-11-14</td><td>FCC ID 2AJ2X-WS102</td><td>Whoop Inc.</td><td>NEW DEVICE</td></tr>
<tr><td>header row, no device</td></tr>
</table>
"""


def test_parse_report_company_pairs_date_and_fccid():
    rows = fetchers.parse_report_company(REPORT_HTML, "2AJ2X")
    by = {r["fcc_id"]: r for r in rows}
    assert by["2AJ2X-WM50"]["grant_date"] == "2026-05-15"
    assert by["2AJ2X-WS50"]["grant_date"] == "2025-05-08"
    assert by["2AJ2X-WS102"]["grant_date"] == "2016-11-14"
    assert all(r["grantee_code"] == "2AJ2X" for r in rows)
    assert len(rows) == 3


def test_report_fetcher_exhibit_url_points_at_mirror():
    f = fetchers.ReportFetcher()
    assert f.exhibit_url("2AJ2X-WM50") == "https://fcc.report/FCC-ID/2AJ2X-WM50"


def test_get_fetcher_default_is_report():
    f = fetchers.get_fetcher(False)
    assert isinstance(f, fetchers.ReportFetcher)
    assert f.name == "fcc.report"
