from importlib.metadata import version
from typing import Annotated

import typer

from wingman import instance as inst

# NetBird's public cloud. Only self-hosted deployments need to override this,
# so it's a default rather than a required flag.
DEFAULT_MANAGEMENT_URL = "https://api.netbird.io:443"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"wingman {version('wingman')}")
        raise typer.Exit


app = typer.Typer(
    name="wingman",
    help="Manage multiple NetBird instances with isolated configs and interfaces.",
)


@app.callback()
def main(
    _version: Annotated[
        bool,
        typer.Option(
            "-v",
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
) -> None:
    pass


@app.command()
def up(
    name: str = typer.Argument(help="Instance name"),
    management_url: str = typer.Option(
        DEFAULT_MANAGEMENT_URL,
        "--management-url",
        envvar="WINGMAN_MANAGEMENT_URL",
        help="NetBird management URL (defaults to the public cloud)",
    ),
    setup_key: Annotated[
        str | None,
        typer.Option(
            "--setup-key",
            envvar="WINGMAN_SETUP_KEY",
            help="NetBird setup key (omit for OAuth login)",
        ),
    ] = None,
    interface_name: Annotated[
        str | None,
        typer.Option("--interface-name", help="Override WireGuard interface name"),
    ] = None,
    daemon_addr: Annotated[
        str | None,
        typer.Option("--daemon-addr", help="Override daemon address"),
    ] = None,
) -> None:
    """Start a named NetBird instance."""
    inst.up(
        name=name,
        management_url=management_url,
        setup_key=setup_key,
        interface_name=interface_name,
        daemon_addr=daemon_addr,
    )


@app.command()
def down(
    name: str = typer.Argument(help="Instance name"),
) -> None:
    """Stop a named NetBird instance."""
    inst.down(name)


@app.command()
def status(
    name: Annotated[
        str | None, typer.Argument(help="Instance name (omit for all)")
    ] = None,
) -> None:
    """Show status of one or all instances."""
    inst.status(name)


@app.command()
def peers(
    name: Annotated[
        str | None, typer.Argument(help="Instance name (omit for all)")
    ] = None,
) -> None:
    """List peers and their connection status for one or all instances."""
    inst.peers(name)


@app.command(name="list")
def list_cmd() -> None:
    """List all known instances and their state."""
    inst.list_all()
