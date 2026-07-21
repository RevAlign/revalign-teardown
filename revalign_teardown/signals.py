"""Turn a hardware company's FCC filing history into go-to-market signals.

This is the heart of the account-in tool: given the list of equipment grants a
company has filed, compute the things a seller actually cares about —

  * are they shipping something new right now?
  * are they ramping (filing faster than they used to)?
  * is a launch imminent (internal photos about to unlock)?
  * did they just enter a product category they were never in before?

...and render it as an account brief with a verifiable FCC link on every claim.
Pure functions, no network — fed by :mod:`revalign_teardown.fcc`.
"""

from __future__ import annotations

import datetime as _dt

CONFIDENTIAL_DAYS = 180          # short-term confidentiality cap (auto-expires)
IMMINENT_UNLOCK_DAYS = 45        # "photos unlock in N days" window
JUST_PUBLIC_DAYS = 75            # "internals just went public" window
RECENT_DAYS = 365                # what counts as a recent filing


def _d(iso: str) -> _dt.date:
    return _dt.date.fromisoformat(iso)


def product_code(fcc_id: str, grantee_code: str) -> str:
    """FCC ID = grantee code + product code; strip the grantee prefix + separator."""
    rest = fcc_id[len(grantee_code):] if fcc_id.upper().startswith(grantee_code.upper()) else fcc_id
    return rest.lstrip("-_ ").strip() or fcc_id


def compute_signals(filings: list[dict], today: str,
                    grantee_code: str = "") -> dict:
    """`filings`: [{fcc_id, grant_date, application_id, device_class?}]. Returns a
    signal dict. `today` is an ISO date (stamped by the caller, never guessed)."""
    now = _d(today)
    rows = [f for f in filings if f.get("grant_date")]
    rows.sort(key=lambda f: f["grant_date"])
    if not rows:
        return {"total": 0, "headline": "No FCC filings found for this grantee.",
                "filings": []}

    for f in rows:
        gd = _d(f["grant_date"])
        age = (now - gd).days
        f["_age"] = age
        f["_released"] = age >= CONFIDENTIAL_DAYS
        f["_unlock_in"] = None if f["_released"] else CONFIDENTIAL_DAYS - age
        f.setdefault("product_code",
                     product_code(f["fcc_id"], grantee_code or f.get("grantee_code", "")))

    first, latest = rows[0], rows[-1]
    span_days = max(1, (_d(latest["grant_date"]) - _d(first["grant_date"])).days)
    span_years = max(span_days / 365.0, 0.25)
    total = len(rows)
    last_year = [f for f in rows if f["_age"] <= RECENT_DAYS]
    last_180 = [f for f in rows if f["_age"] <= CONFIDENTIAL_DAYS]

    baseline_per_year = total / span_years
    recent_rate = len(last_year)
    ramping = recent_rate >= 2 and recent_rate >= 1.5 * baseline_per_year

    # imminent launches: locked filings about to unlock, or just-unlocked ones
    unlocking = sorted(
        [f for f in rows if not f["_released"] and f["_unlock_in"] is not None
         and f["_unlock_in"] <= IMMINENT_UNLOCK_DAYS],
        key=lambda f: f["_unlock_in"])
    just_public = [f for f in rows
                   if f["_released"] and (f["_age"] - CONFIDENTIAL_DAYS) <= (JUST_PUBLIC_DAYS - 0)
                   and f["_age"] >= CONFIDENTIAL_DAYS]
    # a fresh grant whose photos are still fully locked = a product in the pipeline
    in_pipeline = [f for f in rows if not f["_released"]]

    # new product family: a product_code seen only in the last year
    fam_first: dict[str, str] = {}
    for f in rows:
        fam_first.setdefault(f["product_code"], f["grant_date"])
    new_families = [pc for pc, gd in fam_first.items()
                    if (now - _d(gd)).days <= RECENT_DAYS]

    signals = {
        "total": total,
        "grantee_code": grantee_code,
        "first_grant": first["grant_date"],
        "latest_grant": latest["grant_date"],
        "latest_days_ago": latest["_age"],
        "recent_count_365": len(last_year),
        "recent_count_180": len(last_180),
        "baseline_per_year": round(baseline_per_year, 1),
        "ramping": ramping,
        "in_pipeline": in_pipeline,      # filed, photos still confidential
        "unlocking": unlocking,          # photos unlock within IMMINENT window
        "just_public": just_public,      # photos went public recently
        "new_families": new_families,
        "filings": rows,
    }
    signals["headline"] = _headline(signals)
    return signals


def _headline(s: dict) -> str:
    if s["unlocking"]:
        f = s["unlocking"][0]
        return ("Launch imminent: internal photos for %s unlock in ~%d days "
                "(filed %s)." % (f["fcc_id"], f["_unlock_in"], f["grant_date"]))
    if s["in_pipeline"]:
        n = len(s["in_pipeline"])
        return ("In the pipeline: %d device%s certified but photos still under "
                "confidentiality — new product(s) not yet public."
                % (n, "" if n == 1 else "s"))
    if s["just_public"]:
        f = s["just_public"][-1]
        return ("Fresh: internal photos for %s just went public (filed %s) — "
                "a recent launch." % (f["fcc_id"], f["grant_date"]))
    if s["ramping"]:
        return ("Ramping: %d filings in the last 12 months, up from ~%.1f/yr — "
                "they're spending on new hardware." %
                (s["recent_count_365"], s["baseline_per_year"]))
    if s["latest_days_ago"] <= RECENT_DAYS:
        return ("Active: last certified %d days ago (%s)."
                % (s["latest_days_ago"], s["latest_grant"]))
    return ("Quiet: no FCC filings in the last year (last was %s). "
            "No new-hardware signal right now." % s["latest_grant"])


def render_brief(company: str, grantee_name: str, grantee_code: str,
                 signals: dict, exhibit_url=None, limit: int = 8) -> str:
    """Human-readable account brief (markdown). `exhibit_url(fcc_id, app_id)` builds
    the verifiable FCC link per filing."""
    L = ["# %s — FCC signal brief" % company,
         "",
         "**%s** (grantee `%s`, %s)" % (company, grantee_code, grantee_name),
         "",
         "## Signal",
         signals["headline"],
         ""]
    if signals["total"] == 0:
        return "\n".join(L)

    L += ["- %d lifetime filings (this grantee), first %s, latest %s (%d days ago)"
          % (signals["total"], signals["first_grant"], signals["latest_grant"],
             signals["latest_days_ago"]),
          "- %d in the last 12 months (baseline ~%.1f/yr)"
          % (signals["recent_count_365"], signals["baseline_per_year"])]
    if signals["new_families"]:
        L.append("- new product code(s) this year: %s"
                 % ", ".join(signals["new_families"][:6]))
    L += ["", "## Recent filings"]
    recent = sorted(signals["filings"], key=lambda f: f["grant_date"],
                    reverse=True)[:limit]
    for f in recent:
        state = ("photos public" if f["_released"]
                 else "photos unlock in ~%d days" % f["_unlock_in"])
        link = ""
        if exhibit_url:
            link = " — %s" % exhibit_url(f["fcc_id"], f.get("application_id", ""))
        L.append("- `%s` granted %s · %s%s"
                 % (f["fcc_id"], f["grant_date"], state, link))

    L += ["", "## Reason to reach out",
          _reach_out(company, signals), ""]
    return "\n".join(L)


def _reach_out(company: str, s: dict) -> str:
    if s["unlocking"]:
        f = s["unlocking"][0]
        return ("%s just certified %s; its internal photos become public in ~%d "
                "days, so a new product ships within weeks. That's the window to "
                "reach out about [what you sell into it]." %
                (company, f["fcc_id"], f["_unlock_in"]))
    if s["in_pipeline"]:
        return ("%s has %d device(s) certified but not yet public — they're mid-"
                "launch. Open with the specific filing, not a generic pitch." %
                (company, len(s["in_pipeline"])))
    if s["ramping"]:
        return ("%s is filing faster than usual — a company ramping hardware is "
                "spending on components, compliance, tooling and retail. Time the "
                "outreach to the ramp." % company)
    return ("Lead with the most recent filing (%s) as the concrete, verifiable "
            "hook instead of a firmographic guess." % s["latest_grant"])
