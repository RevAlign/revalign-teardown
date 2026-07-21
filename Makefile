.PHONY: help install test brief serve build clean

help:
	@echo "make install       editable install (runtime is stdlib-only)"
	@echo "make test          run the offline test suite (no network, no keys)"
	@echo "make brief C=Whoop account signal brief for a company (reads fcc.report)"
	@echo "make serve         open the teardown-photo gallery (web/) locally"
	@echo "make build         rebuild the gallery index from FCC (curated brands)"
	@echo "make clean         remove build/scratch artifacts"
	@echo ""
	@echo "  add --browser for fresh live-FCC data: revalign-teardown company Whoop --browser"

install:
	pip install -e .

test:
	python -m pytest -q

# Account signal brief. Override the company with C=, e.g. make brief C="Eight Sleep"
C ?= Whoop
brief:
	python -m revalign_teardown company "$(C)"

# Serve the self-contained gallery. It has zero external calls, so a plain
# static server (or just opening the file) is enough.
serve:
	@echo "Serving web/ at http://localhost:8770  (Ctrl-C to stop)"
	cd web && python -m http.server 8770

# Rebuild the baked index from FCC for the curated brand set.
# Needs the optional build extra for PDF rasterization: pip install -e ".[build]"
build:
	python -m revalign_teardown build --out web/data/index.json

# Validate the committed index and summarize it (offline).
demo:
	python -m revalign_teardown validate web/data/index.json

clean:
	rm -rf build dist *.egg-info .pytest_cache .cache raw raw_* tmp
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
