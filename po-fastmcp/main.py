from po_fastmcp import POFastMCP
from tools import register_tools

fhir_scopes = [
    {"name": "patient/Patient.rsu", "required": True},
    {"name": "patient/Observation.rs"},
    {"name": "patient/Condition.rs"},
]

mcp = POFastMCP(
    name="FHIR Ready MCP Server",
    instructions="A MCP server to test FHIR based EHR",
    fhir_scopes=fhir_scopes,
)

register_tools(mcp)

def main() -> None:
    try:
        print("Starting MCP server at http://127.0.0.1:9000/mcp")
        print("Press Ctrl+C to stop.")
        mcp.run(transport="http", host="127.0.0.1", port=9000)
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
