"""Build ``web/data/index.json`` (and inline it into ``web/index.html``) from the
FCC, for the curated launch brands.

Runs the pull chain in :mod:`revalign_teardown.fcc` per brand, rasterizes the
internal-photo PDFs via :mod:`revalign_teardown.photos`, and assembles the index
the gallery renders. Degrades gracefully: if the Akamai WAF blocks this network
(common on CI / datacenter IPs), it explains and leaves the committed index
untouched rather than clobbering it with an empty one.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys

from revalign_teardown import fcc, schema
from revalign_teardown.brands import BRANDS


def _today() -> dt.date:
    return dt.date.today()


def _default_since() -> str:
    return (_today() - dt.timedelta(days=730)).isoformat()


def _grant_record(brand_code: str, grantee_name: str, row: dict,
                  recent_days: int, embed_photos: bool) -> dict | None:
    fcc_id = row["fcc_id"]
    app_id = row["application_id"]
    grant_date = row.get("grant_date")
    if not grant_date:
        return None
    days = (_today() - dt.date.fromisoformat(grant_date)).days
    rec = {
        "fcc_id": fcc_id,
        "product": None,  # resolved from label/manual exhibits later; None is fine
        "grantee_code": brand_code,
        "grantee_name": grantee_name,
        "grant_date": grant_date,
        "days_since_grant": max(0, days),
        "recent": 0 <= days <= recent_days,
        "fcc_url": fcc.exhibit_report_url(app_id, fcc_id),
        "confidential_internal": True,   # flip to False once we see a released photo
        "photos": [],
    }
    exhibits = fcc.list_exhibits(app_id, fcc_id)
    internal = fcc.internal_photo_exhibits(exhibits)
    if not internal:
        return rec  # still confidential (short-term window not expired) or long-term
    rec["confidential_internal"] = False
    for ex in internal:
        photo = {
            "kind": "internal",
            "caption": ex.get("label") or "Internal photo",
            "full_url": fcc.attachment_url(ex["attachment_id"]),
        }
        if embed_photos:
            try:
                from revalign_teardown import photos as photomod
                pdf = fcc.download_attachment(ex["attachment_id"])
                thumbs = photomod.pdf_to_thumbnails(pdf)
                if thumbs:
                    photo["thumb"] = thumbs[0]
                    for extra in thumbs[1:]:
                        rec["photos"].append({
                            "kind": "internal", "caption": photo["caption"],
                            "full_url": photo["full_url"], "thumb": extra,
                        })
            except RuntimeError as e:
                print("  ! photo skipped (%s): %s" % (fcc_id, e), file=sys.stderr)
        rec["photos"].insert(0, photo)
    return rec


def run(out_path: str = "web/data/index.json", since: str | None = None,
        recent_days: int = 90, brands: list[str] | None = None,
        limit_per_brand: int = 40, embed_photos: bool = True) -> int:
    since = since or _default_since()
    slugs = brands or list(BRANDS.keys())
    out_brands = []
    blocked = False

    for slug in slugs:
        b = BRANDS.get(slug)
        if not b:
            print("unknown brand slug: %s" % slug, file=sys.stderr)
            continue
        grants = []
        for code in b["grantee_codes"]:
            name = fcc.grantee_name(code) or (b["grantee_names"] or [b["brand"]])[0]
            try:
                rows = fcc.search_grants(code, since=since)
            except fcc.FccBlocked as e:
                print("\nBLOCKED: %s\n" % e, file=sys.stderr)
                blocked = True
                break
            except fcc.FccError as e:
                print("  ! search failed for %s: %s" % (code, e), file=sys.stderr)
                continue
            print("%-10s %-6s %d grants since %s" % (b["brand"], code, len(rows), since))
            for row in rows[:limit_per_brand]:
                try:
                    rec = _grant_record(code, name, row, recent_days, embed_photos)
                except fcc.FccBlocked as e:
                    print("\nBLOCKED: %s\n" % e, file=sys.stderr)
                    blocked = True
                    break
                except fcc.FccError as e:
                    print("  ! %s: %s" % (row.get("fcc_id"), e), file=sys.stderr)
                    continue
                if rec:
                    grants.append(rec)
            if blocked:
                break
        if grants:
            grants.sort(key=lambda g: g["grant_date"], reverse=True)
            out_brands.append({
                "brand": b["brand"], "slug": slug,
                "grantee_codes": b["grantee_codes"],
                "grantee_names": b["grantee_names"],
                "grants": grants[:limit_per_brand],
            })
        if blocked:
            break

    if blocked and not out_brands:
        print("Nothing fetched — the FCC WAF blocked this network. The committed "
              "index was left untouched. Run from a residential IP, or capture "
              "hero photos with a real browser.", file=sys.stderr)
        return 3
    if not out_brands:
        print("No grants found for any brand.", file=sys.stderr)
        return 1

    index = {
        "schema": 1,
        "generated_at": _today().isoformat(),
        "source": "FCC OET Equipment Authorization System (fcc.gov/oet/ea/fccid)",
        "recent_window_days": recent_days,
        "brands": out_brands,
    }
    errs = schema.validate(index)
    if errs:
        print("built index failed validation:", file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        return 1

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2)
        fh.write("\n")
    print("\nwrote %s" % out_path)
    print(schema.summarize(index))

    html_path = out_path.replace("data/index.json", "index.html")
    try:
        inline_into_html(index, html_path)
        print("inlined index into %s" % html_path)
    except OSError as e:
        print("  ! could not inline into HTML: %s" % e, file=sys.stderr)
    return 0


_SCRIPT_RE = re.compile(
    r'(<script type="application/json" id="teardown-data">)(.*?)(</script>)',
    re.S)


def inline_into_html(index: dict, html_path: str) -> None:
    """Keep web/index.html self-contained: mirror the baked index into its inline
    <script id="teardown-data"> block so the page renders with zero external calls."""
    with open(html_path, "r", encoding="utf-8") as fh:
        html = fh.read()
    payload = "\n" + json.dumps(index, indent=2) + "\n"
    new, n = _SCRIPT_RE.subn(lambda m: m.group(1) + payload + m.group(3), html)
    if n:
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(new)
