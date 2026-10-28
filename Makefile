# On Windows without make, run the python commands in each target directly (see README).
PY ?= python

.PHONY: install db ingest load metrics all test notebook dashboard

install:
	$(PY) -m pip install -r requirements.txt

db:            ## start the embedded Postgres and keep it running (skip if you use Docker)
	$(PY) -m src.db start

ingest:        ## fetch scheme lists and NAV histories into data/raw (cached, resumable)
	$(PY) -m src.pipeline ingest

load:          ## clean the raw cache and load base tables
	$(PY) -m src.pipeline load

metrics:       ## build the SQL metric views
	$(PY) -m src.pipeline metrics

all: ingest load metrics

test:
	$(PY) -m pytest -q

notebook:      ## regenerate and execute notebooks/findings.ipynb (also writes reports/figures)
	$(PY) notebooks/build_findings.py
	$(PY) -m jupyter nbconvert --to notebook --execute --inplace notebooks/findings.ipynb

dashboard:
	$(PY) -m streamlit run dashboard/app.py
