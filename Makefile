.PHONY: proxy

proxy:
	pip install uv
	uv venv --python 3.11 --python-preference managed
	uv sync
	uv pip install -e .
	playwright install
