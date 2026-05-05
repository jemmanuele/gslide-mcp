"""Tool modules. Each module registers its tools with the shared FastMCP server.

Importing this package imports all submodules, which is when @mcp.tool() decorators
fire and register tool handlers.
"""

from . import assets, content, cross_deck, deck, layout, qa, semantic, shapes, slides  # noqa: F401
