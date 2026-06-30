"""Launch the ModelDeck Ingress web UI server."""

from __future__ import annotations

import argparse

from modeldeck.core.logging import get_logger

logger = get_logger(__name__)

# B104: binding to 0.0.0.0 is intentional — the web UI runs inside the
# Home Assistant add-on container and must be reachable via the Supervisor
# Ingress proxy. It is never exposed directly on the host network.
_DEFAULT_HOST = "0.0.0.0"  # nosec B104


def run_webui(host: str = _DEFAULT_HOST, port: int = 8099) -> None:
    """Start the uvicorn server for the Ingress web UI."""
    try:
        import uvicorn
    except ImportError as exc:
        raise ImportError(
            "uvicorn is required for the web UI. "
            "Install with: pip install modeldeck[webui]"
        ) from exc

    from modeldeck.webui.app import create_app

    app = create_app()
    logger.info("Starting ModelDeck web UI on %s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="warning")


def cmd_webui(args: argparse.Namespace) -> int:
    """CLI entry for modeldeck webui."""
    run_webui(host=getattr(args, "host", _DEFAULT_HOST), port=getattr(args, "port", 8099))
    return 0


def register_webui_command(sub: argparse._SubParsersAction) -> None:
    """Register the webui subcommand."""
    webui = sub.add_parser("webui", help="Start the Ingress web UI server")
    webui.add_argument(
        "--host", default=_DEFAULT_HOST, help="Bind host (default: 0.0.0.0)"
    )
    webui.add_argument("--port", type=int, default=8099, help="Bind port (default: 8099)")
    webui.set_defaults(func=cmd_webui)
