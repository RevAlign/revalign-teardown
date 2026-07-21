"""Two ways to pull a grantee's filing list — because the FCC gives you no choice.

The FCC's own site (apps.fcc.gov) 403s every script, from any IP, including
residential — verified. So a fork-and-run tool has exactly two options:

  ReportFetcher  (default) — read the public fcc.report mirror over plain HTTP.
                 Zero setup, stdlib only. Full history + released teardown docs.
                 Trade-off: a mirror, so it lags on the very newest filings.

  BrowserFetcher (--browser) — drive a *headful* Playwright Chrome against the
                 live FCC. Fresh, FCC-official, catches just-filed devices.
                 A headless browser gets blocked (Akamai); a visible one gets
                 through. Trade-off: needs the browser extra + pops a window.

Both return the same shape: [{fcc_id, grant_date, grantee_code, application_id?}].
The signal engine doesn't care which produced them.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request

from revalign_teardown import fcc

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


class FetchError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# default backend: fcc.report (HTTP, stdlib)
# ---------------------------------------------------------------------------

class ReportFetcher:
    name = "fcc.report"
    base = "https://fcc.report"

    def list_filings(self, grantee_code: str, timeout: int = 30) -> list[dict]:
        url = "%s/FCC-ID/%s" % (self.base, grantee_code)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                html = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return []          # unknown grantee, or the mirror blocked us
            raise FetchError("fcc.report HTTP %s for %s" % (e.code, grantee_code))
        except urllib.error.URLError as e:
            raise FetchError("fcc.report unreachable: %s" % e)
        return parse_report_company(html, grantee_code)

    def exhibit_url(self, fcc_id: str, application_id: str = "") -> str:
        return "%s/FCC-ID/%s" % (self.base, fcc_id)


_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def parse_report_company(html: str, grantee_code: str) -> list[dict]:
    """Extract {fcc_id, grant_date} from an fcc.report company page. Each row is
    `<td>YYYY-MM-DD</td> ... FCC ID {grantee}-{product} ...`."""
    fid_re = re.compile(r"\b(%s[-\s]?[A-Z0-9]+)\b" % re.escape(grantee_code), re.I)
    out: dict[str, dict] = {}
    for row in re.split(r"</tr>", html, flags=re.I):
        fm = fid_re.search(re.sub(r"<[^>]+>", " ", row))
        if not fm:
            continue
        fcc_id = re.sub(r"\s+", "", fm.group(1)).upper()
        # normalize "2AJ2XWS50" back toward "2AJ2X-WS50" only if the source had a dash
        if grantee_code.upper() + "-" in row.upper().replace(" ", ""):
            fcc_id = fcc_id if "-" in fcc_id else fcc_id.replace(grantee_code.upper(),
                                                                 grantee_code.upper() + "-", 1)
        dm = _DATE.search(row)
        if not dm:
            continue
        out.setdefault(fcc_id, {"fcc_id": fcc_id, "grant_date": dm.group(1),
                                "grantee_code": grantee_code})
    return list(out.values())


# ---------------------------------------------------------------------------
# fresh backend: headful Playwright against apps.fcc.gov
# ---------------------------------------------------------------------------

class BrowserFetcher:
    name = "live FCC (browser)"

    def __init__(self):
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as e:
            raise FetchError(
                "the --browser mode needs the browser extra:\n"
                '    pip install -e ".[browser]" && playwright install chromium'
            ) from e

    _EXTRACT = r"""() => {
      const rows = [];
      document.querySelectorAll('a[href*="application_id"]').forEach(a => {
        const h = a.getAttribute('href') || '';
        const mu = /application_id=([^&"'<>]+)/i.exec(h);
        const mf = /fcc_id=([^&"'<>]+)/i.exec(h);
        const tr = a.closest('tr');
        const txt = tr ? tr.innerText.replace(/\s+/g, ' ') : '';
        const md = /(\d{2})\/(\d{2})\/(\d{4})/.exec(txt);
        if (mu && mf) rows.push({
          fcc_id: decodeURIComponent(mf[1]).trim(),
          application_id: decodeURIComponent(mu[1]),
          grant_date: md ? `${md[3]}-${md[1]}-${md[2]}` : null });
      });
      const by = {}; rows.forEach(r => { if (!by[r.fcc_id]) by[r.fcc_id] = r; });
      return Object.values(by);
    }"""

    def list_filings(self, grantee_code: str, timeout: int = 45000) -> list[dict]:
        from playwright.sync_api import sync_playwright
        rows: list[dict] = []
        with sync_playwright() as p:
            # headless is detected + blocked by Akamai; a visible window is not.
            browser = p.chromium.launch(headless=False)
            page = browser.new_page(user_agent=USER_AGENT)
            try:
                page.goto("https://apps.fcc.gov/oetcf/eas/reports/GenericSearch.cfm",
                          wait_until="domcontentloaded", timeout=timeout)
                page.fill("input[name=grantee_code]", grantee_code)
                with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout):
                    page.eval_on_selector("form", "f => f.submit()")
                rows = page.evaluate(self._EXTRACT)
            finally:
                browser.close()
        for r in rows:
            r["grantee_code"] = grantee_code
        return [r for r in rows if r.get("grant_date")]

    def exhibit_url(self, fcc_id: str, application_id: str = "") -> str:
        if application_id:
            return fcc.exhibit_report_url(application_id, fcc_id)
        return "https://www.fcc.gov/oet/ea/fccid"


def get_fetcher(use_browser: bool):
    return BrowserFetcher() if use_browser else ReportFetcher()
