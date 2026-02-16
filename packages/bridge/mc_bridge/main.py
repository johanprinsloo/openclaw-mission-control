"""
Bridge entry point.

Loads configuration, configures logging, and starts the bridge.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from .bridge import CommsBridge
from .config import load_config


def configure_logging(level: str = "info", fmt: str = "json") -> None:
    """Configure structlog with the specified level and format."""
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if fmt == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            structlog.get_level_from_name(level)
        ),
    )


def run() -> None:
    """CLI entry point for the bridge."""
    parser = argparse.ArgumentParser(description="OpenClaw ↔ Mission Control Comms Bridge")
    parser.add_argument(
        "-c", "--config",
        default="comms-bridge.yaml",
        help="Path to configuration file (default: comms-bridge.yaml)",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    configure_logging(config.logging.level, config.logging.format)
    log = structlog.get_logger()
    log.info("bridge.config_loaded", config_path=args.config, agents=len(config.agents))

    bridge = CommsBridge(config)
    try:
        asyncio.run(bridge.run_forever())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
