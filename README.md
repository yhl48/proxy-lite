<div align="center">

  <img src="assets/proxy-lite.png" alt="Proxy Lite logo" width="600" height="auto" style="margin-bottom: 20px;" />

  <h2>
    A mini, open-weights, version of our Proxy assistant.
  </h2>


<!-- Badges -->
<p>
  <a href="https://github.com/convergence-ai/proxy-lite/contributors">
    <img src="https://img.shields.io/github/contributors/convergence-ai/proxy-lite" alt="contributors" />
  </a>
  <a href="">
    <img src="https://img.shields.io/github/last-commit/convergence-ai/proxy-lite" alt="last update" />
  </a>
  <a href="https://github.com/convergence-ai/proxy-lite/network/members">
    <img src="https://img.shields.io/github/forks/convergence-ai/proxy-lite" alt="forks" />
  </a>
  <a href="https://github.com/convergence-ai/proxy-lite/stargazers">
    <img src="https://img.shields.io/github/stars/convergence-ai/proxy-lite" alt="stars" />
  </a>
  <a href="https://github.com/convergence-ai/proxy-lite/issues/">
    <img src="https://img.shields.io/github/issues/convergence-ai/proxy-lite" alt="open issues" />
  </a>
  <a href="https://github.com/convergence-ai/proxy-lite/blob/master/LICENSE">
    <img src="https://img.shields.io/github/license/convergence-ai/proxy-lite.svg" alt="license" />
  </a>
</p>

</div>




<div align="center">
     <img src="assets/demo.gif" alt="Proxy Lite Demo" />
</div>



## Installation

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
pip install uv
uv venv --python 3.11 --python-preference managed
uv sync
uv pip install -e .
playwright install
```


## Usage

```bash
proxy --help
```
You can directly run Proxy Lite on a task with:

```bash
proxy "Book a table for 2 at an Italian restaurant in Kings Cross tonight at 7pm."
```

Alternatively you can run the local web ui with:

```bash
make app
```

### Proxy Lite Endpoint

By default, Proxy Lite will point to an endpoint set up on HuggingFace spaces.
> ‼ This is a demo endpoint and is not suitable for production, or even frequent hobbyist, use; it may be very slow when under heavy load.

We recommend hosting your own endpoint with vLLM, you can use the following command:

```bash
vllm serve --model convergence-ai/proxy-lite \
    --trust-remote-code \
    --enable-auto-tool-choice \
    --tool-call-parser hermes \
    --port 8008 \
```

The tool arguments are **very important** for parsing the tool calls from the model appropriately.

> **Important:** To run this, install vLLM and transformers with `uv sync --all-extras`. Qwen-2.5-VL Support in `transformers` is not yet available in the latest release so is done from source.

You can set the `api_base` to point to your local endpoint when calling Proxy Lite:

```bash
proxy --api-base http://localhost:8008/v1 "Book a table...
```
or by setting the environment variable:

```bash
export PROXY_LITE_API_BASE=http://localhost:8008/v1
```

### Scaffolding Proxy Lite in Python

We use the `RunnerConfig` to control the setup of the task.
The library is designed to be modular and extendable, you can easily swap the environment, solver, or agent.

Example:
```python
import asyncio
from proxy_lite import Runner, RunnerConfig

config = RunnerConfig.from_dict(
    {
        "environment": {
            "name": "webbrowser",
            "homepage": "https://www.google.com",
            "headless": True, # Don't show the browser
        },
        "solver": {
            "name": "simple",
            "agent": {
                "name": "proxy_lite",
                "client": {
                    "name": "convergence",
                    "model_id": "convergence-ai/proxy-lite",
                    "api_base": "https://convergence-ai-demo-api.hf.space/v1",
                },
            },
        },
        "max_steps": 50,
        "action_timeout": 1800,
        "environment_timeout": 1800,
        "task_timeout": 18000,
        "logger_level": "DEBUG",
    },
)

proxy = Runner(config=config)
result = asyncio.run(
    proxy.run("Book a table for 2 at an Italian restaurant in Kings Cross tonight at 7pm.")
)
```

### Webbrowser Environment

The `webbrowser` environment is a simple environment that uses the `playwright` library to navigate the web.

We launch a Chromium browser and navigate to the `homepage` provided in the `RunnerConfig`.

Actions in an environment are defined through available tool calls, which in the browser case are set as default in the `BrowserTool` class. This allows the model to click, type, etc. at relevant `mark_id` elements on the page. These elements are extracted using JavaScript injected into the page in order to make interaction easier for the models. 

If you want to not use this set-of-marks approach, you can set the `no_pois_in_image` flag to `True`, and the `include_poi_text` flag to `False` in the `EnvironmentConfig`. This way the model will only see the original image, and not the annotated image with these points-of-interest (POIs). In this case, you would want to update the `BrowserTool` to interact with pixel coordinates instead of the `mark_id`s.




