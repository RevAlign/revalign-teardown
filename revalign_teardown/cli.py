"""Command-line entry point for revalign-teardown.

    revalign-teardown validate <index.json>   # offline: check the baked index
    revalign-teardown build [--out ...]        # rebuild the index from the FCC
    revalign-teardown brands                   # list the curated launch brands

``validate`` and ``brands`` are pure-offline (no network, no deps) so CI and a
fresh clone always work. ``build`` reaches the FCC and, for photo rasterization,
uses the optional ``[build]`` extra.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys

from revalign_teardown import __version__


def _cmd_validate(args: argparse.Namespace) -> int:
    from revalign_teardown import schema
    try:
        with open(args.path, "r", encoding="utf-8") as fh:
            index = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        print("could not read %s: %s" % (args.path, e), file=sys.stderr)
        return 2
    errs = schema.validate(index)
    print(schema.summarize(index))
    if errs:
        print("\n%d problem(s):" % len(errs), file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        return 1
    print("\nOK — index is well-formed and every card links back to the FCC.")
    return 0


def _cmd_brands(args: argparse.Namespace) -> int:
    from revalign_teardown.brands import BRANDS
    for slug, b in BRANDS.items():
        print("%-10s %-12s %s" % (slug, ",".join(b["grantee_codes"]), b["brand"]))
    print("\n%d curated launch brands." % len(BRANDS))
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    from revalign_teardown.resolve import resolve_company
    cands = resolve_company(args.company)
    if not cands:
        print("no FCC grantee matched %r (try the legal name, or it may make no "
              "radio hardware)" % args.company, file=sys.stderr)
        return 1
    for c in cands:
        print("%-7s %.2f  %s" % (c["grantee_code"], c["score"], c["grantee_name"]))
    return 0


def _cmd_company(args: argparse.Namespace) -> int:
    from revalign_teardown import signals, fetchers
    from revalign_teardown.resolve import resolve_company

    cands = resolve_company(args.company)
    if not cands:
        print("no FCC grantee matched %r — does this company make radio hardware? "
              "(pure-software companies have no FCC filings)" % args.company,
              file=sys.stderr)
        return 1
    codes = [c["grantee_code"] for c in cands[:args.max_grantees]]
    name = cands[0]["grantee_name"]

    try:
        fetcher = fetchers.get_fetcher(args.browser)
    except fetchers.FetchError as e:
        print(str(e), file=sys.stderr)
        return 2
    print("resolved %r -> %s  (source: %s)"
          % (args.company, ", ".join(codes), fetcher.name), file=sys.stderr)

    filings: list[dict] = []
    for code in codes:
        try:
            filings.extend(fetcher.list_filings(code))
        except fetchers.FetchError as e:
            print("  ! %s: %s" % (code, e), file=sys.stderr)

    today = _dt.date.today().isoformat()
    sig = signals.compute_signals(filings, today, grantee_code=codes[0])
    brief = signals.render_brief(args.company, name, ",".join(codes), sig,
                                 exhibit_url=fetcher.exhibit_url)
    print(brief)
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    try:
        from revalign_teardown import build
    except Exception as e:  # pragma: no cover - defensive
        print("build module unavailable: %s" % e, file=sys.stderr)
        return 2
    return build.run(
        out_path=args.out,
        since=args.since,
        recent_days=args.recent_days,
        brands=args.brand or None,
        limit_per_brand=args.limit,
        embed_photos=not args.no_photos,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="revalign-teardown",
        description="A wall of real internal teardown photos from FCC filings — "
                    "every card verifiable on fcc.gov.",
    )
    p.add_argument("--version", action="version",
                   version="revalign-teardown %s" % __version__)
    sub = p.add_subparsers(dest="cmd")

    v = sub.add_parser("validate", help="validate a baked index.json (offline)")
    v.add_argument("path", nargs="?", default="web/data/index.json")
    v.set_defaults(func=_cmd_validate)

    b = sub.add_parser("brands", help="list the curated launch brands (offline)")
    b.set_defaults(func=_cmd_brands)

    r = sub.add_parser("resolve", help="company name -> FCC grantee code(s) (Socrata)")
    r.add_argument("company")
    r.set_defaults(func=_cmd_resolve)

    c = sub.add_parser("company",
                       help="account signal brief: what is this company about to ship?")
    c.add_argument("company", help="company name (or the brand you're targeting)")
    c.add_argument("--max-grantees", type=int, default=3,
                   help="how many candidate grantee codes to crawl")
    c.add_argument("--browser", action="store_true",
                   help="pull fresh from the live FCC via a headful Chrome "
                        "(needs the browser extra); default reads fcc.report")
    c.set_defaults(func=_cmd_company)

    bu = sub.add_parser("build", help="rebuild the index from the FCC (needs network)")
    bu.add_argument("--out", default="web/data/index.json")
    bu.add_argument("--since", default=None,
                    help="only grants on/after this ISO date (default: last ~2 years)")
    bu.add_argument("--recent-days", type=int, default=90,
                    help="a grant newer than this many days is flagged 'recent'")
    bu.add_argument("--brand", action="append",
                    help="limit to these brand slugs (repeatable); default: all curated")
    bu.add_argument("--limit", type=int, default=40,
                    help="max grants to keep per brand")
    bu.add_argument("--no-photos", action="store_true",
                    help="skip embedding thumbnails (grants + links only, fast)")
    bu.set_defaults(func=_cmd_build)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
