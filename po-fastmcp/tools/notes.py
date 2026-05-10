from prefab_ui.actions import SetState, ShowToast
from prefab_ui.actions.mcp import CallTool
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Badge, Button, Column, ForEach,
    Heading, Input, Row, Separator, Text,
)
from prefab_ui.rx import RESULT
from fastmcp import FastMCPApp

notes_app = FastMCPApp("Notes")

notes_db: list[dict] = []


@notes_app.tool()
def add_note(title: str, body: str) -> list[dict]:
    """Save a note and return all notes."""
    notes_db.append({"title": title, "body": body})
    return list(notes_db)


@notes_app.ui("notes_app")
def open_notes_app() -> PrefabApp:
    """Open the notes app."""
    with Column(gap=6, css_class="p-6") as view:
        Heading("Notes")

        with ForEach("notes") as note:
            with Row(gap=2, align="center"):
                Text(note.title, css_class="font-semibold")
                Badge(note.body)

        Separator()

        submit_action = CallTool(
            add_note,
            arguments={"title": "{{ title }}", "body": "{{ body }}"},
            on_success=[
                SetState("notes", RESULT),
                ShowToast("Note saved!", variant="success"),
            ],
            on_error=ShowToast("Failed to save", variant="error"),
        )

        with Column(gap=4):
            Input(name="title", label="Title", required=True)
            Input(name="body", label="Body", required=True)
            Button("Add Note", on_click=submit_action)

    return PrefabApp(view=view, state={"notes": list(notes_db)})


