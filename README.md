![Proxy-Lite Logo](assets/proxy-lite.png)

A mini, open-weights version of our Proxy assistant.

![Proxy-Lite Demo](demo.gif)

---

## Getting Started

### Installation

Clone the repository: 

```bash
git clone https://github.com/convergence-ai/proxy-lite.git
```

Set-up the environment with:

```bash
make proxy
```

Or do it manually:

```bash
uv venv --python 3.11 --python-preference managed
uv sync
uv pip install -e .
playwright install
```


### Usage

```bash
proxy --help
```

You can directly run the proxy with:

```bash
proxy "Book a table for 2 at an Italian restaurant in Kings Cross tonight at 7pm."
```


### Proxy-Lite Endpoint

By default, Proxy-Lite will point to an endpoint set up on HuggingFace spaces. This is a demo endpoint and is not suitable for production use; it may be very slow when under heavy load.

We recommend hosting your own endpoint with vLLM, you can use the following command:

```bash
vllm serve --model convergence-ai/proxy-lite-7b \
    --trust-remote-code \
    --enable-auto-tool-choice \
    --tool-call-parser hermes \
    --port 8008 \
```

You can set the `api_base` to point to your local endpoint when calling Proxy-Lite:

```bash
proxy --api-base http://localhost:8008/v1 "Book a table...
```
or by setting the environment variable:

```bash
export PROXY_LITE_API_BASE=http://localhost:8008/v1
```




