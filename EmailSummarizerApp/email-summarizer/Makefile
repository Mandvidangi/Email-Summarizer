.PHONY: run dev test lint schema

run:
\tuvicorn services.api.main:app --host 0.0.0.0 --port 8080 --reload

dev:  ## install deps
\tpython -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

test:
\tpytest -q

lint:
\truff check .

schema:
\tpython libs/schema/email_summary_v1.py --export-json-schema
