.PHONY: proxy

proxy:
	uv venv --python 3.11 --python-preference managed
	uv sync
	uv pip install -e .
	playwright install
