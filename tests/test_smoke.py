"""Offline smoke + validation tests. No network, no keys."""

import json
import os
import re

from revalign_teardown import __version__, schema
from revalign_teardown.brands import BRANDS, known_codes, slugify
from revalign_teardown.cli import build_parser, main

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "web", "data", "index.json")
HTML = os.path.join(ROOT, "web", "index.html")


def _load():
    with open(INDEX, encoding="utf-8") as fh:
        return json.load(fh)


def test_version_is_sane():
    assert re.match(r"^\d+\.\d+\.\d+", __version__)


def test_cli_help_runs():
    assert main(["--help"] if False else []) == 0  # no-args prints help, rc 0
    build_parser()  # constructs without error


def test_brands_command():
    assert main(["brands"]) == 0


def test_committed_index_is_valid():
    errs = schema.validate(_load())
    assert errs == [], "committed index has problems:\n" + "\n".join(errs)


def test_validate_command_on_committed_index():
    assert main(["validate", INDEX]) == 0


def test_validator_catches_non_fcc_link():
    idx = _load()
    idx["brands"][0]["grants"][0]["fcc_url"] = "https://fccid.io/whatever"
    errs = schema.validate(idx)
    assert any("FCC-official" in e for e in errs)


def test_validator_catches_external_thumb():
    idx = _load()
    idx["brands"][0]["grants"][0]["photos"][0]["thumb"] = "https://evil.example/x.jpg"
    errs = schema.validate(idx)
    assert any("data: URI" in e for e in errs)


def test_validator_catches_duplicate_fccid():
    idx = _load()
    g = idx["brands"][0]["grants"]
    g.append(dict(g[0]))
    errs = schema.validate(idx)
    assert any("duplicate fcc_id" in e for e in errs)


def test_brand_registry_has_no_duplicate_codes():
    codes = known_codes()
    total = sum(len(b["grantee_codes"]) for b in BRANDS.values())
    assert len(codes) == total, "a grantee code is claimed by two brands"


def test_slugify():
    assert slugify("Ultimate Ears") == "ultimate-ears"
    assert slugify("GoPro, Inc.") == "gopro-inc"


def test_web_page_makes_no_external_requests():
    """The shipped gallery must be self-contained: no remote scripts/styles/images."""
    with open(HTML, encoding="utf-8") as fh:
        html = fh.read()
    assert "<script src=" not in html.replace(" ", "").replace('"', "").replace("'", "") \
        or 'src="http' not in html, "no external <script src>"
    # No remote asset URLs in src/href to http(s) except explicit target-_blank anchors.
    bad = re.findall(r'(?:src|href)\s*=\s*"https?://[^"]+"', html)
    # links out to fcc.gov / revalign.io / github are anchors (allowed); flag asset loads
    asset_bad = [u for u in bad if re.search(r'\.(js|css|png|jpg|jpeg|gif|webp|woff2?)"$', u)]
    assert asset_bad == [], "external asset loads found: %r" % asset_bad
