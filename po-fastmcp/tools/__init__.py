from fastmcp import FastMCP
from tools.greet import greet_app
from tools.notes import notes_app
from tools.echo import echo
from tools.edit_demographics import editDemographics_app

def register_tools(mcp: FastMCP)->None:
    mcp.add_provider(greet_app)
    mcp.add_provider(notes_app)
    mcp.add_provider(editDemographics_app)
    mcp.add_tool(echo)
