PY ?= python
export PYTHONPATH := src

.PHONY: all ingest run test
all: ingest run
ingest:
	$(PY) -m gih.ingest
run:
	$(PY) -m gih.pipeline
test:
	$(PY) -m pytest -q tests
