from types import MethodType
from typing import Any

from fastmcp import FastMCP

_FHIR_CONTEXT_EXTENSION = "ai.promptopinion/fhir-context"
_FhirScope = dict[str, str | bool]

_DEFAULT_FHIR_SCOPES: list[_FhirScope] = [
    {"name": "patient/Patient.rs", "required": True},
    {"name": "patient/Observation.rs"},
    {"name": "patient/MedicationStatement.rs"},
    {"name": "patient/Condition.rs"},
]


class POFastMCP(FastMCP):
    def __init__(
        self,
        name: str = "FHIR Ready MCP Server",
        instructions: str = "A MCP server to test FHIR based EHR",
        *,
        fhir_scopes: list[_FhirScope] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(name, instructions=instructions, **kwargs)
        _add_fhir_context_extension(
            self,
            scopes=fhir_scopes,
        )


def _add_fhir_context_extension(
    mcp_server: FastMCP,
    scopes: list[_FhirScope] | None = None,
    extension_name: str = _FHIR_CONTEXT_EXTENSION,
) -> None:
    extension_scopes = _normalize_fhir_scopes(scopes)
    original_get_capabilities = mcp_server._mcp_server.get_capabilities

    def get_capabilities(self, notification_options, experimental_capabilities):
        caps = original_get_capabilities(
            notification_options,
            experimental_capabilities,
        )

        existing_extensions = getattr(caps, "extensions", None) or {}
        caps.extensions = {
            **existing_extensions,
            extension_name: {"scopes": extension_scopes},
        }

        return caps

    mcp_server._mcp_server.get_capabilities = MethodType(
        get_capabilities,
        mcp_server._mcp_server,
    )


def _normalize_fhir_scopes(
    scopes: list[_FhirScope] | None,
) -> list[dict[str, str | bool]]:
    selected_scopes = _DEFAULT_FHIR_SCOPES if scopes is None else scopes
    return [
        {
            "name": str(scope["name"]),
            "required": bool(scope.get("required", False)),
        }
        for scope in selected_scopes
    ]
