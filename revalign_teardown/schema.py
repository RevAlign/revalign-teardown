"""Offline validation of the baked index (``web/data/index.json``).

Pure stdlib, no network. Shared by the ``validate`` CLI command and the test
suite so CI can guarantee the shipped index is well-formed and self-verifiable
(every card carries an FCC ID and a link back to the FCC record).
"""

from __future__ import annotations

import datetime as _dt
import re

FCC_HOSTS = ("fcc.gov", "apps.fcc.gov", "opendata.fcc.gov", "www.fcc.gov")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ValidationError(ValueError):
    pass


def _is_fcc_url(url: str) -> bool:
    if not isinstance(url, str) or "://" not in url:
        return False
    host = url.split("://", 1)[1].split("/", 1)[0].lower()
    return any(host == h or host.endswith("." + h) for h in FCC_HOSTS)


def _valid_date(s: str) -> bool:
    if not isinstance(s, str) or not _DATE_RE.match(s):
        return False
    try:
        _dt.date.fromisoformat(s)
        return True
    except ValueError:
        return False


def validate(index: dict) -> list[str]:
    """Return a list of human-readable problems. Empty list == valid."""
    errs: list[str] = []

    if not isinstance(index, dict):
        return ["top level is not an object"]
    if index.get("schema") != 1:
        errs.append("schema must be 1")
    if not _valid_date(index.get("generated_at", "")):
        errs.append("generated_at must be an ISO date (YYYY-MM-DD)")
    win = index.get("recent_window_days")
    if not isinstance(win, int) or win <= 0:
        errs.append("recent_window_days must be a positive integer")

    brands = index.get("brands")
    if not isinstance(brands, list):
        return errs + ["brands must be a list"]

    seen_codes: dict[str, str] = {}
    seen_fccids: set[str] = set()

    for bi, b in enumerate(brands):
        where = "brands[%d]" % bi
        if not isinstance(b, dict):
            errs.append("%s is not an object" % where)
            continue
        for key in ("brand", "slug"):
            if not b.get(key):
                errs.append("%s missing %s" % (where, key))
        codes = b.get("grantee_codes", [])
        if not isinstance(codes, list) or not codes:
            errs.append("%s.grantee_codes must be a non-empty list" % where)
        else:
            for c in codes:
                if c in seen_codes and seen_codes[c] != b.get("slug"):
                    errs.append("grantee_code %r claimed by both %s and %s"
                                % (c, seen_codes[c], b.get("slug")))
                seen_codes[c] = b.get("slug")

        grants = b.get("grants", [])
        if not isinstance(grants, list):
            errs.append("%s.grants must be a list" % where)
            continue
        for gi, g in enumerate(grants):
            gw = "%s.grants[%d]" % (where, gi)
            if not isinstance(g, dict):
                errs.append("%s is not an object" % gw)
                continue
            fid = g.get("fcc_id")
            if not fid:
                errs.append("%s missing fcc_id" % gw)
            elif fid in seen_fccids:
                errs.append("%s duplicate fcc_id %r" % (gw, fid))
            else:
                seen_fccids.add(fid)
            if not _valid_date(g.get("grant_date", "")):
                errs.append("%s.grant_date must be an ISO date" % gw)
            if not _is_fcc_url(g.get("fcc_url", "")):
                errs.append("%s.fcc_url must point at an FCC-official host (got %r)"
                            % (gw, g.get("fcc_url")))
            if not isinstance(g.get("recent"), bool):
                errs.append("%s.recent must be a boolean" % gw)

            photos = g.get("photos", [])
            if not isinstance(photos, list):
                errs.append("%s.photos must be a list" % gw)
                continue
            for pi, p in enumerate(photos):
                pw = "%s.photos[%d]" % (gw, pi)
                if not isinstance(p, dict):
                    errs.append("%s is not an object" % pw)
                    continue
                # A photo must be verifiable: an FCC-official full_url, and if a
                # thumb is embedded it must be a self-contained data: URI.
                if not (_is_fcc_url(p.get("full_url", ""))
                        or _is_fcc_url(g.get("fcc_url", ""))):
                    errs.append("%s has no FCC-official link to verify against" % pw)
                thumb = p.get("thumb")
                if thumb is not None and not str(thumb).startswith("data:"):
                    errs.append("%s.thumb must be a self-contained data: URI "
                                "(no external image hosts)" % pw)
    return errs


def summarize(index: dict) -> str:
    brands = index.get("brands", [])
    grants = sum(len(b.get("grants", [])) for b in brands)
    photos = sum(len(g.get("photos", []))
                 for b in brands for g in b.get("grants", []))
    recent = sum(1 for b in brands for g in b.get("grants", []) if g.get("recent"))
    seed = " (SEED data — run `build` for real FCC records)" if index.get("_seed") else ""
    lines = [
        "generated_at : %s%s" % (index.get("generated_at", "?"), seed),
        "brands       : %d" % len(brands),
        "grants       : %d" % grants,
        "internal photos (approx cards): %d" % photos,
        "recent grants (<= %sd): %d" % (index.get("recent_window_days", "?"), recent),
    ]
    top = sorted(brands, key=lambda b: len(b.get("grants", [])), reverse=True)[:8]
    if top:
        lines.append("top brands   : " + ", ".join(
            "%s(%d)" % (b.get("brand"), len(b.get("grants", []))) for b in top))
    return "\n".join(lines)
