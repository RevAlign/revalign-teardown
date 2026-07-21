"""Offline tests for the FCC HTML/text parsers and HTML inlining.

The live apps.fcc.gov endpoint is behind an Akamai WAF and unreachable from CI,
so we test the pure parsing functions against synthetic fixtures shaped like the
real pages (per the data-access spike: SS3-DEN225, application_id
Zc17qATP8T8uYsNEBDS+kA==, internal-photos attachment 8481875).
"""

import json

from revalign_teardown import fcc, build

SEARCH_HTML = """
<table>
 <tr>
   <td>SS3</td><td>DEN225</td><td>SZ DJI TECHNOLOGY</td>
   <td><a href="ViewExhibitReport.cfm?mode=Exhibits&application_id=Zc17qATP8T8uYsNEBDS%2BkA%3D%3D&fcc_id=SS3-DEN225">SS3-DEN225</a></td>
   <td>07/16/2025</td>
 </tr>
 <tr>
   <td>SS3</td><td>DN1A</td><td>SZ DJI TECHNOLOGY</td>
   <td><a href="ViewExhibitReport.cfm?mode=Exhibits&application_id=abc123%3D%3D&fcc_id=SS3-DN1A062624">SS3-DN1A062624</a></td>
   <td>07/24/2024</td>
 </tr>
</table>
"""

EXHIBIT_HTML = """
<table>
 <tr><td>Cover Letter</td><td><a href="GetApplicationAttachment.html?id=8481870">download</a></td></tr>
 <tr><td>Internal Photos</td><td><a href="GetApplicationAttachment.html?id=8481875">download</a></td></tr>
 <tr><td>External Photos</td><td><a href="GetApplicationAttachment.html?id=8481876">download</a></td></tr>
 <tr><td>Schematics (long-term confidential)</td><td>&nbsp;</td></tr>
</table>
"""


def test_parse_search_results_extracts_id_appid_date():
    rows = fcc.parse_search_results(SEARCH_HTML)
    by_id = {r["fcc_id"]: r for r in rows}
    assert "SS3-DEN225" in by_id
    r = by_id["SS3-DEN225"]
    assert r["application_id"] == "Zc17qATP8T8uYsNEBDS+kA=="  # url-decoded
    assert r["grant_date"] == "2025-07-16"
    assert by_id["SS3-DN1A062624"]["grant_date"] == "2024-07-24"


def test_parse_exhibit_list_flags_internal_only():
    ex = fcc.parse_exhibit_list(EXHIBIT_HTML)
    internal = fcc.internal_photo_exhibits(ex)
    assert len(internal) == 1
    assert internal[0]["attachment_id"] == "8481875"
    # the confidential schematics row has no attachment id -> not surfaced
    assert all(e["attachment_id"] != "" for e in ex)


def test_attachment_and_report_urls_are_fcc_official():
    assert fcc.attachment_url("8481875") == \
        "https://apps.fcc.gov/eas/GetApplicationAttachment.html?id=8481875"
    url = fcc.exhibit_report_url("abc==", "SS3-DEN225")
    assert url.startswith("https://apps.fcc.gov/oetcf/eas/reports/ViewExhibitReport.cfm")
    assert "fcc_id=SS3-DEN225" in url


def test_inline_into_html_roundtrip(tmp_path):
    html = (
        '<html><body>x'
        '<script type="application/json" id="teardown-data">{"brands":[]}</script>'
        '</body></html>'
    )
    p = tmp_path / "index.html"
    p.write_text(html, encoding="utf-8")
    idx = {"schema": 1, "generated_at": "2026-07-21", "recent_window_days": 90,
           "brands": [{"brand": "DJI"}]}
    build.inline_into_html(idx, str(p))
    out = p.read_text(encoding="utf-8")
    # the inline block now parses to our index
    start = out.index(">", out.index('id="teardown-data"')) + 1
    end = out.index("</script>", start)
    assert json.loads(out[start:end])["brands"][0]["brand"] == "DJI"
