from typing import Any
from urllib.parse import quote

import httpx

from po_fastmcp.fhir_context import FhirContext

FhirResource = dict[str, Any]


class FhirClient:
    def __init__(self, context: FhirContext) -> None:
        self.context = context

    def _headers(self, *, include_content_type: bool = False) -> dict[str, str]:
        headers = {"Accept": "application/fhir+json"}
        if include_content_type:
            headers["Content-Type"] = "application/fhir+json"
            headers["Prefer"] = "return=representation"
        if self.context.token:
            token = self.context.token
            headers["Authorization"] = token if token.startswith("Bearer ") else f"Bearer {token}"
        return headers

    async def read(self, resource_type: str, resource_id: str) -> FhirResource | None:
        url = (
            f"{self.context.url}/"
            f"{quote(resource_type, safe='')}/"
            f"{quote(resource_id, safe='')}"
        )
        headers = self._headers()

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

        if response.status_code == 404:
            return None

        response.raise_for_status()
        return response.json()

    async def put(
        self,
        resource_type: str,
        resource_id: str,
        resource: FhirResource,
    ) -> FhirResource:
        url = (
            f"{self.context.url}/"
            f"{quote(resource_type, safe='')}/"
            f"{quote(resource_id, safe='')}"
        )
        headers = self._headers(include_content_type=True)

        async with httpx.AsyncClient() as client:
            response = await client.put(url, headers=headers, json=resource)

        response.raise_for_status()
        return response.json() if response.content else resource

    async def search(
        self,
        resource_type: str,
        search_parameters: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[FhirResource]:
        url = f"{self.context.url}/{quote(resource_type, safe='')}"
        headers = self._headers()

        params = search_parameters or {}
        if limit:
            params["_count"] = limit

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)

        response.raise_for_status()
        bundle = response.json()
        return [
            entry["resource"]
            for entry in bundle.get("entry", [])
            if "resource" in entry
        ]
