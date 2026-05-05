"""Entry point. Imports tools (which registers them) and runs the MCP server."""

from .app import mcp
from . import tools  # noqa: F401  — side-effect: registers all @mcp.tool() handlers


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
