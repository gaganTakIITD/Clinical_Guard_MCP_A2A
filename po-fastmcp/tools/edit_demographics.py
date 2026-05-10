import datetime

from fastmcp import FastMCPApp
from fhir.resources.humanname import HumanName
from fhir.resources.patient import Patient
from prefab_ui.actions import SetState, ShowToast
from prefab_ui.actions.mcp import CallTool
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Button,
    Card,
    CardContent,
    CardHeader,
    CardTitle,
    Column,
    Input,
    Label,
)
from prefab_ui.rx import RESULT
from po_fastmcp import FhirClient, get_fhir_context
from pydantic import BaseModel, Field


class PatientDemographicsData(BaseModel):
    first_name: str = Field(title="First Name", min_length=1)
    last_name: str = Field(title="Last Name", min_length=1)
    birth_date: datetime.date = Field(title="Date of Birth")


editDemographics_app = FastMCPApp("A tool to edit patient demographics")


@editDemographics_app.ui("EditPatientDemographics")
async def edit_demographics() -> PrefabApp:
    refresh_action = CallTool(
        "RefreshPatientDemographics",
        on_success=[
            SetState("first_name", RESULT.first_name),
            SetState("last_name", RESULT.last_name),
            SetState("birth_date", RESULT.birth_date),
        ],
        on_error=ShowToast("{{ $error }}", variant="error"),
    )
    submit_action = CallTool(
        "UpdatePatientDemographics",
        arguments={
            "data": {
                "first_name": "{{ first_name }}",
                "last_name": "{{ last_name }}",
                "birth_date": "{{ birth_date }}",
            }
        },
        on_success=[
            ShowToast("Patient demographics updated.", variant="success"),
            refresh_action,
        ],
        on_error=ShowToast("{{ $error }}", variant="error"),
    )

    demographics = await get_current_demographics()
    if demographics is None:
        raise ValueError("Current patient demographics are not available.")

    with Card() as view:
        with CardHeader():
            CardTitle("Edit Patient Demographics")
        with CardContent():
            with Column(gap=4):
                with Column(gap=2):
                    Label("First Name")
                    Input(
                        name="first_name",
                        placeholder="First Name",
                        required=True,
                    )
                with Column(gap=2):
                    Label("Last Name")
                    Input(
                        name="last_name",
                        placeholder="Last Name",
                        required=True,
                    )
                with Column(gap=2):
                    Label("Date of Birth")
                    Input(
                        input_type="date",
                        name="birth_date",
                        required=True,
                    )
                Button("Update", on_click=submit_action)

    return PrefabApp(view=view, state=_demographics_state(demographics))


async def get_current_demographics() -> PatientDemographicsData | None:
    context = get_fhir_context()
    if context is None or not context.patient_id:
        return None

    patient_resource = await FhirClient(context).read("Patient", context.patient_id)
    patient = Patient.model_validate(patient_resource) if patient_resource else None
    if patient is None:
        return None

    try:
        return _patient_demographics(patient)
    except ValueError:
        return None


@editDemographics_app.tool("UpdatePatientDemographics")
async def update_patient_demographics(data: PatientDemographicsData) -> dict[str, str]:
    context = get_fhir_context()
    if context is None or not context.patient_id:
        raise ValueError("FHIR patient context is not available.")

    client = FhirClient(context)
    patient_resource = await client.read("Patient", context.patient_id)
    if patient_resource is None:
        raise ValueError(f"Patient {context.patient_id} was not found.")

    patient = Patient.model_validate(patient_resource)
    patient.id = context.patient_id

    name = _primary_name(patient)
    if name is None:
        name = HumanName(use="official")
        patient.name = [name]

    name.given = [data.first_name]
    name.family = data.last_name
    patient.birthDate = data.birth_date

    updated_resource = await client.put(
        "Patient",
        context.patient_id,
        patient.model_dump(mode="json", exclude_none=True),
    )
    updated_patient = Patient.model_validate(updated_resource)
    return _demographics_state(_patient_demographics(updated_patient))


@editDemographics_app.tool("RefreshPatientDemographics")
async def refresh_patient_demographics() -> dict[str, str]:
    demographics = await get_current_demographics()
    if demographics is None:
        raise ValueError("Current patient demographics are not available.")
    return _demographics_state(demographics)


def _patient_demographics(patient: Patient) -> PatientDemographicsData:
    name = _primary_name(patient)
    if name is None or patient.birthDate is None:
        raise ValueError("Patient resource is missing name or birth date.")

    given_names = [str(part) for part in name.given or []]
    first_name = given_names[0] if given_names else None
    last_name = str(name.family) if name.family else None
    if first_name is None or last_name is None:
        raise ValueError("Patient resource is missing given or family name.")

    return PatientDemographicsData(
        first_name=first_name,
        last_name=last_name,
        birth_date=patient.birthDate,
    )


def _primary_name(patient: Patient) -> HumanName | None:
    if not patient.name:
        return None

    for use in ("official", "usual"):
        for name in patient.name:
            if name.use == use:
                return name

    for name in patient.name:
        if name.use != "old":
            return name

    return patient.name[0]


def _demographics_state(data: PatientDemographicsData) -> dict[str, str]:
    return data.model_dump(mode="json")
