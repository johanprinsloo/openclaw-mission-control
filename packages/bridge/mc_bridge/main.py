"""
Bridge entry point.

Connects to Mission Control via SSE and relays messages to/from the OpenClaw Gateway.
"""

import structlog

log = structlog.get_logger()


def run():
    """Start the Comms Bridge."""
    log.info("Starting OpenClaw Mission Control Bridge")
    # Production implementation will be built in Foundation Phase 16
    raise NotImplementedError("Bridge implementation pending — see POC at poc/bridge/")


if __name__ == "__main__":
    run()
