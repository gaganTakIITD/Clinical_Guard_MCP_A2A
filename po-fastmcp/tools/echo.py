from fastmcp.tools import tool

@tool()
def echo(hi: str) -> str:
    """Echo a greeting for the provided text."""
    return f"hello {hi}!"
