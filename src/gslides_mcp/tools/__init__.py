"""Tool modules. Each module registers its tools with the shared FastMCP server.

Importing this package imports all submodules, which is when @mcp.tool() decorators
fire and register tool handlers.
"""

from . import deck, slides, shapes, layout, content, qa, assets, semantic, cross_deck  # noqa: F401
