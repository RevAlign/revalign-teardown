"""Curated registry of launch brands whose FCC internal photos actually go public.

This hand-maintained map — grantee code(s) -> retail brand — is the real IP of
the tool. The FCC lists the *grantee* (often a contract manufacturer or a legal
entity), not the consumer brand, so mapping ``SS3`` -> "DJI" is a human call.

Grantee codes are the first 3-5 characters of an FCC ID. They are verified at
build time against the FCC grantee registry; treat the codes here as the seed
set and correct them from the live record when you run ``build``.

Deliberately excludes Apple: it keeps internal photos under long-term / permanent
confidentiality, so its filings yield model numbers but no board shots.
"""

from __future__ import annotations

# slug -> {brand, grantee_codes, grantee_names}
# Grantee codes verified against the FCC grantee registry (Socrata 3b3k-34jp).
# Several "obvious" guesses are wrong (RAX is Arcadyan, not Sonos; II6 is
# Supersonics, not GoPro) — always verify the code before trusting a brand.
BRANDS: dict[str, dict] = {
    "dji":      {"brand": "DJI",       "grantee_codes": ["SS3"],        "grantee_names": ["SZ DJI Technology Co., Ltd."]},
    "sonos":    {"brand": "Sonos",     "grantee_codes": ["SBV"],        "grantee_names": ["Sonos, Inc."]},
    "anker":    {"brand": "Anker",     "grantee_codes": ["2AOKB"],      "grantee_names": ["Anker Innovations Limited"]},
    "gopro":    {"brand": "GoPro",     "grantee_codes": ["CNF", "AWV"], "grantee_names": ["GoPro, Inc.", "Woodman Labs, Inc (GoPro)"]},
    "garmin":   {"brand": "Garmin",    "grantee_codes": ["IPH"],        "grantee_names": ["Garmin International, Inc."]},
    "nintendo": {"brand": "Nintendo",  "grantee_codes": ["BKE"],        "grantee_names": ["Nintendo Co., Ltd."]},
    "logitech": {"brand": "Logitech",  "grantee_codes": ["JNZ"],        "grantee_names": ["Logitech Far East Ltd."]},
    "bose":     {"brand": "Bose",      "grantee_codes": ["A94"],        "grantee_names": ["Bose Corporation"]},
    "razer":    {"brand": "Razer",     "grantee_codes": ["RWO", "OY7"], "grantee_names": ["Razer Inc.", "Razer USA Ltd."]},
    "ring":     {"brand": "Ring",      "grantee_codes": ["2AEUP"],      "grantee_names": ["Ring LLC"]},
    "valve":    {"brand": "Valve",     "grantee_codes": ["2AES4"],      "grantee_names": ["Valve Corporation"]},
    "beats":    {"brand": "Beats",     "grantee_codes": ["COW"],        "grantee_names": ["Beats Electronics, LLC"]},
    "skydio":   {"brand": "Skydio",    "grantee_codes": ["2ATQR"],      "grantee_names": ["Skydio, Inc."]},
}


def slugify(name: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in name.lower())
    return "-".join(p for p in out.split("-") if p)


def known_codes() -> dict[str, str]:
    """grantee_code -> slug, for reverse lookups."""
    m: dict[str, str] = {}
    for slug, b in BRANDS.items():
        for c in b["grantee_codes"]:
            m[c.upper()] = slug
    return m
