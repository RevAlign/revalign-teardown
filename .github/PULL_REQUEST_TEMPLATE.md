<!-- Thanks for contributing to revalign-dependents. Keep it honest: say what you validated on live data and what you did not. -->

## What this changes

<!-- One or two sentences. -->

## Type

- [ ] New ecosystem enumerator (PyPI / Go / crates / Maven)
- [ ] New enumeration or enrichment source
- [ ] Filter / attribution change (structural gate, org-vs-user, vendor exclusion)
- [ ] Bug fix
- [ ] Docs
- [ ] Other

## For enumeration, filter, or `--vs` changes: what did you validate?

<!-- Required if you touched the pipeline. Be specific and honest; run against a real package. -->

- **Package(s) tested:**
- **Enumeration source used:** `ecosyste.ms` / `github-code-search`
- **Token set:** yes / no
- **Run header you observed** (paste the `enumerated N ... / M survived ... / K company rows` lines):
- **Row count and roughly how many were real orgs vs personal users:**
- **False positives (what got kept that should have been dropped?):**
- **What is still un-validated:**

If your change touches `--vs`, confirm the displacement column still reads "no public evidence of X (crawl date)" and never a definitive negative like "not using X". This is a hard rule: the index is public, default-branch-only, and lagging.

Attach the `dependents.csv` and `proof.md` from a real run if you can. A proof link on every row is the whole point; show that it survived your change.

## Checklist

- [ ] `revalign-dependents --help` works
- [ ] `pytest -q` passes (offline, no network, no keys)
- [ ] Stdlib only; no third-party dependencies added
- [ ] No em dashes in code, comments, or docs
- [ ] The tool still fails loudly and never silently reports zero dependents
- [ ] `--vs` phrasing stays "no public evidence of X", never a definitive negative
- [ ] No secrets, keys, or private data added
