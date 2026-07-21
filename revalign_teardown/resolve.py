"""Resolve a company name to its FCC grantee code(s).

The FCC lists the *grantee* — a legal entity, often a contract manufacturer, and
a company can hold several codes (GoPro = CNF + AWV). This maps a plain company
name to candidate grantee codes so the account-in tool can take "DJI" and find
`SS3`.

Free path: the Socrata grantee registry (opendata.fcc.gov, dataset 3b3k-34jp),
which answers any client and sends CORS. Honest limit: that snapshot is frozen at
2021, so grantee codes registered since then are missing — for those, the live
FCC GranteeSearch (apps.fcc.gov, behind the Akamai WAF) is the fallback and needs
a residential/browser client. Names are scored by normalized-token overlap so a
contract-manufacturer alias doesn't masquerade as the brand.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

SOCRATA = "https://opendata.fcc.gov/resource/3b3k-34jp.json"
USER_AGENT = "revalign-teardown (+https://github.com/RevAlign/revalign-teardown)"

# corporate-form noise stripped before token matching
_STOP = {"inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation",
         "co", "company", "gmbh", "srl", "sa", "sas", "bv", "ab", "oy", "plc",
         "pte", "pty", "kk", "ag", "spa", "the", "technology", "technologies",
         "electronics", "international", "usa", "us", "america", "global",
         "holdings", "group", "labs", "systems", "devices"}


def _tokens(name: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", name.lower())
    core = {w for w in words if w not in _STOP and len(w) > 1}
    return core or set(words)


def _score(query: str, candidate: str) -> float:
    q, c = _tokens(query), _tokens(candidate)
    if not q or not c:
        return 0.0
    overlap = len(q & c)
    if overlap == 0:
        return 0.0
    # precision toward the query terms, with a small bonus for exact token cover
    return overlap / len(q) + (0.25 if q <= c else 0.0)


def _socrata_like(term: str, timeout: int = 20) -> list[dict]:
    where = "upper(grantee_name) like '%%%s%%'" % term.upper().replace("'", "")
    url = SOCRATA + "?" + urllib.parse.urlencode(
        {"$where": where, "$select": "grantee_code,grantee_name", "$limit": 50})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError):
        return []


def resolve_company(name: str, min_score: float = 0.5,
                    max_results: int = 6) -> list[dict]:
    """Return candidate grantees [{grantee_code, grantee_name, score}] best-first.

    Queries Socrata on the most distinctive token of the name (skipping corporate
    filler), then scores every returned grantee against the full name so a partial
    substring match ("Ring" -> "Ring Central") is ranked below a real one.
    """
    terms = sorted(_tokens(name), key=len, reverse=True)[:2] or [name]
    seen: dict[str, dict] = {}
    for term in terms:
        for row in _socrata_like(term):
            code = row.get("grantee_code")
            gname = row.get("grantee_name", "")
            if not code:
                continue
            s = _score(name, gname)
            if code not in seen or s > seen[code]["score"]:
                seen[code] = {"grantee_code": code, "grantee_name": gname,
                              "score": round(s, 2)}
    cands = [c for c in seen.values() if c["score"] >= min_score]
    cands.sort(key=lambda c: (-c["score"], len(c["grantee_name"])))
    return cands[:max_results]
