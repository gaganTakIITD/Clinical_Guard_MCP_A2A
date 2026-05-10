import base64
import binascii
from collections.abc import Mapping
from dataclasses import dataclass
import json
from fastmcp.server.dependencies import get_http_headers

_FHIR_ACCESS_TOKEN_HEADER = "x-fhir-access-token"
_FHIR_SERVER_URL_HEADER = "x-fhir-server-url"
_PATIENT_ID_HEADER = "x-patient-id"


@dataclass(frozen=True)
class FhirContext:
    url: str
    token: str | None
    patient_id: str | None


class FhirContextError(RuntimeError):
    """Raised when a tool requires FHIR launch context that is not available."""


def get_fhir_context() -> FhirContext | None:
    headers = get_http_headers(include_all=True)
    url = headers.get(_FHIR_SERVER_URL_HEADER)
    token = headers.get(_FHIR_ACCESS_TOKEN_HEADER)
    if not url or not token:
        return None
    patientId = headers.get(_PATIENT_ID_HEADER)
    return FhirContext(
        url=url.rstrip("/"),
        token=token,
        patient_id=patientId,
    )


