# Prompt Opinion FastMCP FHIR Sample

This sample shows how to build a small FastMCP server that can use FHIR launch
context provided by the platform.

The reusable package code lives in `po_fastmcp/`. The files most people should
edit for their own sample app are:

- `main.py`: create the server, register tools, and run it
- `tools/`: add or change MCP tools

## Getting Started

This project uses `uv` for dependency and environment management. After cloning
or downloading the repo, run:

```shell
cd po-fastmcp
uv sync
```

`uv sync` creates or updates the local virtual environment from
`pyproject.toml` and `uv.lock`.

Then start the MCP server:

```shell
uv run python main.py
```

The server listens at:

```text
http://127.0.0.1:9000/mcp
```

During a demo, press `Ctrl+C` to stop it. The entry point catches that normal
shutdown signal and prints a short message instead of a Python traceback. To
start it again, press the up arrow in the terminal and run the same command.

## Server Setup

`main.py` creates a configured FastMCP server and registers the sample tools:

```python
from po_fastmcp import POFastMCP
from tools import register_tools

fhir_scopes = [
    {"name": "patient/Patient.rsu", "required": True},
    {"name": "patient/Observation.rs"},
    {"name": "patient/Condition.rs"},
]

mcp = POFastMCP(fhir_scopes=fhir_scopes)
register_tools(mcp)
```

The Patient scope uses `rsu` because the sample includes read, search, and
update flows for Patient resources. For tools that only read Patient data,
`patient/Patient.rs` is enough.

To run the server while changing code, use `watchfiles` so the server restarts
automatically whenever you save changes:

```shell
uv run watchfiles --target-type function --filter python --grace-period 1 main.main main.py po_fastmcp tools
```

This calls the `main()` function in `main.py` inside the uv environment, so the
restarted process uses the same dependencies as `uv run python main.py`.

`POFastMCP` is a small subclass of FastMCP that adds the platform FHIR context
capability extension with the sample patient scopes. You can pass custom scopes
when your tools need other FHIR resources:

```python
from po_fastmcp import POFastMCP

fhir_scopes = [
    {"name": "patient/Patient.rs", "required": True},
    {"name": "patient/Observation.rs"},
]

mcp = POFastMCP(
    name="Care Management Server",
    instructions="provides tools for care management",
    fhir_scopes=fhir_scopes,
)
```

## FHIR Context

For each tool call, the platform can pass FHIR context through request headers:

- `x-fhir-server-url`: base URL for the FHIR server
- `x-fhir-access-token`: bearer token for the FHIR server
- `x-patient-id`: current patient id

If any of these required values are missing for a patient-specific tool, the
tool should return `None` or raise a clear error depending on whether the UI can
continue without patient context.

## FHIR Calls

The FHIR client is intentionally small and uses normal HTTP JSON requests via
`httpx`. For application logic, prefer typed `fhir.resources` models over
manual nested dictionary traversal:

```python
from fhir.resources.observation import Observation
from fhir.resources.patient import Patient
from po_fastmcp import FhirClient, get_fhir_context

context = get_fhir_context()
if context is None or not context.patient_id:
    return None

client = FhirClient(context)

patient_resource = await client.read("Patient", context.patient_id)
patient = Patient.model_validate(patient_resource) if patient_resource else None

observation_resources = await client.search(
    "Observation",
    {"patient": context.patient_id},
    limit=10,
)
observations = [
    Observation.model_validate(resource)
    for resource in observation_resources
]

if patient is not None:
    patient.birthDate = "2000-02-01"
    updated_patient_resource = await client.put(
        "Patient",
        context.patient_id,
        patient.model_dump(mode="json", exclude_none=True),
    )
    updated_patient = Patient.model_validate(updated_patient_resource)
```

`read()` gets one resource by type and id. `search()` gets a list of resources
from a FHIR search bundle. `put()` updates a resource by type and id and sends
FHIR JSON with `Content-Type: application/fhir+json`.

Keep `FhirClient` generic and small. Tool-specific behavior should live in the
tool module. For example, `tools/edit_demographics.py` reads a Patient, chooses
the primary `HumanName`, updates first name, last name, and birth date, then
calls `client.put("Patient", patient_id, patient_json)`.

## Building UI Apps with MCP

This repo also includes examples of rendering small interactive apps inside the
chat experience. The app pattern is:

1. Create a `FastMCPApp` in a tool module.
2. Add a `@app.ui(...)` function that returns a `PrefabApp`.
3. Use Prefab components to build the view.
4. Use `PrefabApp(state={...})` for client-side state.
5. Use `CallTool(...)` actions to call backend MCP tools from buttons or other
   UI events.
6. Use `SetState(...)` to update the UI after a tool returns.

`tools/edit_demographics.py` is the main example. It renders a form that edits
FHIR Patient demographics from inside the chat:

```python
@editDemographics_app.ui("EditPatientDemographics")
async def edit_demographics() -> PrefabApp:
    demographics = await get_current_demographics()

    with Card() as view:
        Input(name="first_name", required=True)
        Input(name="last_name", required=True)
        Input(input_type="date", name="birth_date", required=True)
        Button("Update", on_click=submit_action)

    return PrefabApp(view=view, state=_demographics_state(demographics))
```

The `state` dictionary is the client-side data store for the UI. In the
demographics app, the initial state looks like:

```python
{
    "first_name": "Alex",
    "last_name": "Rivera",
    "birth_date": "2000-02-01",
}
```

Inputs with matching `name` values read from and write to those state keys. When
the user edits the form, the latest values are available to actions with
template expressions like `{{ first_name }}`.

The Update button calls an MCP tool with the current state:

```python
submit_action = CallTool(
    "UpdatePatientDemographics",
    arguments={
        "data": {
            "first_name": "{{ first_name }}",
            "last_name": "{{ last_name }}",
            "birth_date": "{{ birth_date }}",
        }
    },
)
```

After the update succeeds, the app calls a refresh tool and writes the returned
FHIR values back into Prefab state:

```python
refresh_action = CallTool(
    "RefreshPatientDemographics",
    on_success=[
        SetState("first_name", RESULT.first_name),
        SetState("last_name", RESULT.last_name),
        SetState("birth_date", RESULT.birth_date),
    ],
)
```

This keeps the UI synchronized with whatever the FHIR server actually saved.
The same pattern works for non-FHIR workflows too: render a small form or
dashboard, keep the editable values in `PrefabApp` state, call a backend MCP
tool, then update state from the tool result.
