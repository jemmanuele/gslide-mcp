"""Single shared FastMCP instance.

Tool modules import `mcp` from here and register handlers with @mcp.tool().
Keeping it in its own module avoids circular imports.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gslides-mcp")
