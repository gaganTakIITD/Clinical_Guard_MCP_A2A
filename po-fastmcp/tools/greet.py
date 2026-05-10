from fastmcp import FastMCPApp
from fhir.resources.patient import Patient
from prefab_ui.app import PrefabApp
from prefab_ui.components import Badge, Column, Heading, Row, Text

from po_fastmcp import FhirClient, get_fhir_context


greet_app = FastMCPApp("Greet")


@greet_app.ui("Greet")
async def greet(name: str) -> PrefabApp:
    """Greet the current patient when FHIR context is available."""
    patient_name = await _current_patient_name()
    greeted_name = patient_name or name

    with Column(gap=4, css_class="p-6") as view:
        Heading(f"Hello, {greeted_name}!")
        with Row(gap=2, align="center"):
            Text("Status")
            Badge("Greeted", variant="success")

    return PrefabApp(view=view)


async def _current_patient_name() -> str | None:
    context = get_fhir_context()
    if context is None or not context.patient_id:
        return None

    patient_resource = await FhirClient(context).read("Patient", context.patient_id)
    print(patient_resource)
    patient = Patient.model_validate(patient_resource) if patient_resource else None
    if patient is None or not patient.name:
        return None

    first_name = patient.name[0]
    if first_name.text:
        return str(first_name.text)

    given = [str(part) for part in first_name.given or []]
    if first_name.family:
        given.append(str(first_name.family))

    return " ".join(given) or None
