# revalign-teardown

[![CI](https://github.com/RevAlign/revalign-teardown/actions/workflows/ci.yml/badge.svg)](https://github.com/RevAlign/revalign-teardown/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](./LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Runtime: stdlib only](https://img.shields.io/badge/runtime-stdlib_only-brightgreen.svg)](#install)

**Point it at a hardware company. It reads the company's FCC certification filings and tells you what they're about to ship — often before they've announced it — with a public record you can verify. That's a reason to reach out that no data vendor sells.**

Every device with a radio has to pass FCC certification before it can be sold in the US. That filing is public the day it's granted: the product code, the grant date, the internal teardown photos (after a 180-day confidentiality clock runs out). A company filing a cert is a company about to ship — about to spend on components, compliance, tooling, packaging, retail. It just walked into a buying window, and almost nobody in go-to-market watches the one database that shows it.

`revalign-teardown` turns that into an account signal. Give it a company; it resolves the company to its FCC grantee code, pulls its filing history, and hands you a brief: are they **ramping**, do they have a device **in the pipeline** but not yet public, did they just enter a **new product category**, and the exact filing to open the conversation with.

> **Scope, up front:** this only works on companies that make **physical products with a radio** — wearables, audio, drones, IoT, medical devices, routers. A pure-software company has no FCC filings, so the tool says nothing about them. If your targets are hardware, this is a reason-to-reach-out engine. If they're SaaS, it's the wrong tool.

---

## The brief

```
$ revalign-teardown company Whoop --browser

# Whoop — FCC signal brief
Whoop (grantee 2AJ2X, Whoop Inc.)

## Signal
In the pipeline: 1 device certified but photos still under confidentiality —
new product(s) not yet public.

- 7 lifetime filings, first 2016-11-14, latest 2026-05-15 (67 days ago)
- new product code(s) this year: WM50        ← they've only ever filed WS/WD/WB

## Recent filings
- 2AJ2X-WM50  granted 2026-05-15 · photos unlock in ~113 days · [fcc.gov link]
- 2AJ2X-WD50  granted 2025-05-08 · photos public · [fcc.gov link]
- ...back to 2016

## Reason to reach out
Whoop has a device certified but not yet public — they're mid-launch. Open with
the specific filing, not a generic pitch.
```

`WM50` is a product code Whoop has never filed before, its photos are still locked, and the grant is public. That's a dated, verifiable "Whoop is about to ship something new" — the kind of hook you can't buy.

---

## Two ways to run it — the FCC forced this choice

The FCC's own site (`apps.fcc.gov`) returns **403 to every script**, from any IP, residential included — it only lets real browsers through. So the tool gives you two backends and you pick:

| Mode | Command | How it works | Trade-off |
|---|---|---|---|
| **default** | `revalign-teardown company Whoop` | reads the public **fcc.report** mirror over plain HTTP — stdlib, no setup | fork-and-run today; full history + released teardown photos, but a mirror, so it **lags on the newest filings** (it'll read "quiet" on a company whose freshest cert it hasn't crawled yet) |
| **fresh** | `revalign-teardown company Whoop --browser` | drives a **headful Chrome** against the live FCC | **fresh + FCC-official** (catches the just-filed stuff); needs the browser extra and pops a visible window for a few seconds |

Same brief either way — the fresh mode just sees the last few weeks the mirror hasn't caught up on. Headless doesn't work here (Akamai flags the automation); a visible browser does.

---

## Install

```bash
pip install revalign-teardown            # runtime is Python standard library only

revalign-teardown company "Eight Sleep"  # default: reads fcc.report, no setup
revalign-teardown resolve "Eight Sleep"  # just show the FCC grantee match
```

For the fresh, live-FCC mode:

```bash
pip install "revalign-teardown[browser]"
playwright install chromium
revalign-teardown company "Eight Sleep" --browser
```

## How it works

```
company name ──▶ resolve to FCC grantee code ──▶ pull filing history ──▶ signals ──▶ brief
  "Whoop"          Socrata (works anywhere)        fcc.report | browser    dates+180d   with FCC links
```

- **`resolve.py`** — company name → grantee code(s), via the free Socrata grantee registry, scored so a contract-manufacturer alias doesn't win over the real brand. (A company can hold several codes; it aggregates them.)
- **`fetchers.py`** — the two backends above, returning the same `{fcc_id, grant_date}` shape.
- **`signals.py`** — the brain: reads grant dates + the 180-day photo clock and fires the signal that matters — in-pipeline / launch-imminent / ramping / new-product-line / quiet — with a verifiable FCC link on every claim.
- **`web/`** — the teardown-photo gallery (a self-contained page). It's the *proof layer*: the guts you show once the signal earns the meeting. See [`web/README`](./web/) — it renders a baked, offline index.

## Data & honesty

FCC equipment-authorization data is public under 47 CFR Part 2. The default backend reads it from **fcc.report**, a public mirror, because the FCC's own site blocks programmatic access; that's low-volume, standard practice for this kind of tool, and every row links back so you can verify it. "Recent" is a timing signal, not a claim that a product is confirmed unreleased. This is a research tool, not affiliated with the FCC or any company shown.

## Install (dev)

```bash
git clone https://github.com/RevAlign/revalign-teardown
cd revalign-teardown
pip install -e ".[dev]"
make test          # offline test suite: no network, no keys
```

---

Built and open-sourced by [RevAlign](https://revalign.io).
