"""FCC Equipment Authorization System (EAS) client — stdlib only.

The data is public by law (47 CFR Part 2) but the ``apps.fcc.gov`` EAS app sits
behind an Akamai edge WAF that 403s anything that doesn't look like a real
browser, offers no CORS, and returns no JSON. So this client:

  * sends a realistic browser User-Agent on every request;
  * pulls the grantee legal name from the friendly Socrata dataset (which does
    answer plain clients and sends CORS);
  * crawls Generic Search -> exhibit report -> attachment download for photos.

The pull chain (per the data-access spike) is:

  GenericSearch.cfm?grantee_code=..&grant_date_from=..   (list FCC IDs + a per-
      filing *encrypted* application_id token; the token must be harvested, not
      constructed)
    -> ViewExhibitReport.cfm?application_id=..&fcc_id=..  (list exhibits +
      numeric attachment ids; an internal-photos attachment that is present and
      downloadable == the short-term confidentiality window has expired)
    -> GetApplicationAttachment.html?id=<int>            (the internal-photos PDF)

The HTML/text parsers are pure functions so they can be unit-tested offline; the
network wrappers just feed them bytes. If Akamai blocks the caller (common from
CI / datacenter IPs), :class:`FccBlocked` is raised with a clear explanation.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
EAS = "https://apps.fcc.gov/oetcf/eas/reports"
ATTACH = "https://apps.fcc.gov/eas/GetApplicationAttachment.html"
SOCRATA = "https://opendata.fcc.gov/resource/3b3k-34jp.json"

INTERNAL_PHOTO_HINTS = ("internal photo", "internal photos", "internal_photo")


class FccError(RuntimeError):
    pass


class FccBlocked(FccError):
    """The Akamai WAF refused the request (403). Not auth — the caller's egress
    (CI / datacenter IP) is blocked. Run from a residential IP or a real browser."""


def _request(url: str, timeout: int = 40) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": EAS + "/GenericSearch.cfm",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise FccBlocked(
                "apps.fcc.gov returned 403 (Akamai WAF). The FCC data is public "
                "but this network egress is blocked. Run `build` from a residential "
                "connection or capture hero photos with a real browser."
            ) from e
        raise FccError("HTTP %s for %s" % (e.code, url)) from e
    except urllib.error.URLError as e:
        raise FccError("network error for %s: %s" % (url, e)) from e


# ---------------------------------------------------------------------------
# grantee directory (Socrata — works from any client)
# ---------------------------------------------------------------------------

def grantee_name(code: str, timeout: int = 20) -> str | None:
    url = SOCRATA + "?" + urllib.parse.urlencode({"grantee_code": code.upper()})
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": USER_AGENT}),
            timeout=timeout,
        ) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
        return rows[0].get("grantee_name") if rows else None
    except (urllib.error.URLError, json.JSONDecodeError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Generic Search -> (fcc_id, application_id, grant_date)
# ---------------------------------------------------------------------------

# links in the results / detail pages carry the token pair we need.
_APPID_RE = re.compile(
    r"application_id=([^&\"'<>]+)[^\"'<>]*?fcc_id=([^&\"'<>]+)", re.I)
_APPID_RE_ALT = re.compile(
    r"fcc_id=([^&\"'<>]+)[^\"'<>]*?application_id=([^&\"'<>]+)", re.I)
_DATE_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")


def _norm_date(mmddyyyy: str) -> str:
    m, d, y = mmddyyyy.split("/")
    return "%s-%s-%s" % (y, m, d)


def parse_search_results(html: str) -> list[dict]:
    """Extract {fcc_id, application_id, grant_date?} rows from a Generic Search
    results page. Robust to column order; grant_date is best-effort (the nearest
    mm/dd/yyyy on the same row)."""
    out: dict[str, dict] = {}
    # Split on row boundaries only (not newlines) so a multi-line <tr> keeps its
    # token pair and grant date together.
    for row_html in re.split(r"</tr>", html, flags=re.I):
        appid = fccid = None
        m = _APPID_RE.search(row_html)
        if m:
            appid, fccid = urllib.parse.unquote(m.group(1)), m.group(2)
        else:
            m = _APPID_RE_ALT.search(row_html)
            if m:
                fccid, appid = m.group(1), urllib.parse.unquote(m.group(2))
        if not (appid and fccid):
            continue
        fccid = fccid.strip()
        row = out.setdefault(fccid, {"fcc_id": fccid, "application_id": appid})
        d = _DATE_RE.search(row_html)
        if d and "grant_date" not in row:
            row["grant_date"] = _norm_date(d.group(1))
    return list(out.values())


def search_grants(grantee_code: str, since: str | None = None,
                  timeout: int = 40) -> list[dict]:
    """All grants for a grantee code (optionally on/after ISO date `since`)."""
    params = {
        "grantee_code": grantee_code,
        "calledFromFrame": "N",
        "RequestTimeout": "500",
        "application_purpose": "",
    }
    if since:
        y, m, d = since.split("-")
        params["grant_date_from"] = "%s/%s/%s" % (m, d, y)
    url = EAS + "/GenericSearch.cfm?" + urllib.parse.urlencode(params)
    html = _request(url, timeout=timeout).decode("utf-8", "replace")
    rows = parse_search_results(html)
    if since:
        rows = [r for r in rows if r.get("grant_date", "9999") >= since]
    return rows


# ---------------------------------------------------------------------------
# Exhibit list -> internal-photo attachment ids
# ---------------------------------------------------------------------------

# rows look like: ...GetApplicationAttachment.html?id=8481875 ... Internal Photos ...
_ATTACH_RE = re.compile(r"GetApplicationAttachment\.html\?id=(\d+)", re.I)


def parse_exhibit_list(html: str) -> list[dict]:
    """Extract exhibits [{attachment_id, label, kind}] from ViewExhibitReport.
    `kind` is 'internal' when the row mentions internal photos, else 'other'.
    Only exhibits with a downloadable attachment id are returned (== released)."""
    out = []
    # split into row-ish chunks and pair an attachment id with nearby label text
    for chunk in re.split(r"</tr>|</p>|\n", html):
        m = _ATTACH_RE.search(chunk)
        if not m:
            continue
        label = re.sub(r"<[^>]+>", " ", chunk)
        label = re.sub(r"\s+", " ", label).strip()
        low = label.lower()
        kind = "internal" if any(h in low for h in INTERNAL_PHOTO_HINTS) else "other"
        out.append({"attachment_id": m.group(1), "label": label[:120], "kind": kind})
    return out


def list_exhibits(application_id: str, fcc_id: str, timeout: int = 40) -> list[dict]:
    params = {
        "mode": "Exhibits", "RequestTimeout": "500", "calledFromFrame": "N",
        "application_id": application_id, "fcc_id": fcc_id,
    }
    url = EAS + "/ViewExhibitReport.cfm?" + urllib.parse.urlencode(params)
    html = _request(url, timeout=timeout).decode("utf-8", "replace")
    return parse_exhibit_list(html)


def internal_photo_exhibits(exhibits: list[dict]) -> list[dict]:
    return [e for e in exhibits if e.get("kind") == "internal"]


def attachment_url(attachment_id: str) -> str:
    return "%s?id=%s" % (ATTACH, attachment_id)


def exhibit_report_url(application_id: str, fcc_id: str) -> str:
    return EAS + "/ViewExhibitReport.cfm?" + urllib.parse.urlencode({
        "mode": "Exhibits", "RequestTimeout": "500", "calledFromFrame": "N",
        "application_id": application_id, "fcc_id": fcc_id,
    })


def download_attachment(attachment_id: str, timeout: int = 60,
                        polite_delay: float = 1.0) -> bytes:
    if polite_delay:
        time.sleep(polite_delay)
    return _request(attachment_url(attachment_id), timeout=timeout)
