import argparse
import asyncio
import os
from pathlib import Path
from typing import Optional

from proxy_lite import Runner, RunnerConfig
from proxy_lite.logger import logger


def update_config_from_env(config: RunnerConfig) -> RunnerConfig:
    if os.getenv("PROXY_LITE_API_BASE"):
        config.solver.client.api_base = os.getenv("PROXY_LITE_API_BASE")
    if os.getenv("PROXY_LITE_MODEL"):
        config.solver.client.model_id = os.getenv("PROXY_LITE_MODEL")
    return config


def do_command(args):
    do_text = " ".join(args.task)
    logger.info("🤖 Let me help you with that...")
    # Take default config from YAML
    config = RunnerConfig.from_yaml(args.config)
    # Update config from environment variables
    config = update_config_from_env(config)
    # Update config from command-line arguments
    if args.api_base:
        config.solver.client.api_base = args.api_base
    if args.model:
        config.solver.client.model_id = args.model
    if args.homepage:
        config.homepage = args.homepage
    if args.viewport_width:
        config.viewport_width = args.viewport_width
    if args.viewport_height:
        config.viewport_height = args.viewport_height
    o = Runner(config=config)
    asyncio.run(o.run(do_text))


def main():
    parser = argparse.ArgumentParser(description="Proxy-Lite")
    parser.add_argument(
        "task",
        type=str,
        help="The task you want to accomplish",
        nargs="*",
    )
    parser.add_argument(
        "--model",
        type=Optional[str],
        default=None,
        help="The model to use.",
    )
    parser.add_argument(
        "--api_base",
        type=Optional[str],
        default=None,
        help="The API base URL to use.",
    )
    # New option for setting a homepage URL:
    parser.add_argument(
        "--homepage",
        type=Optional[str],
        default=None,
        help="The homepage URL to use.",
    )
    # New viewport controls:
    parser.add_argument(
        "--viewport-width",
        type=Optional[int],
        default=None,
        help="Viewport width in pixels.",
    )
    parser.add_argument(
        "--viewport-height",
        type=Optional[int],
        default=None,
        help="Viewport height in pixels.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "configs/default.yaml",
        help="Path to config file (default: configs/default.yaml)",
    )

    args = parser.parse_args()
    do_command(args)


if __name__ == "__main__":
    main()
