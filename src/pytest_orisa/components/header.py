from typing import TYPE_CHECKING, cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input

if TYPE_CHECKING:
    from pytest_orisa.app import OrisaApp


class RunButton(Button):
    def on_click(self) -> None:
        self.disabled = True
        self.loading = True
        self.post_message(self.Pressed(self))

    def reset(self) -> None:
        self.disabled = False
        self.loading = False


class CustomArgsModal(ModalScreen):
    DEFAULT_CSS = """
        CustomArgsModal {
            align: center middle;
        }

        CustomArgsModal > Container {
            width: 30%;
            height: auto;
            background: $background;
            border: solid darkgrey 50%;
            padding: 1 2;
        }

        CustomArgsModal VerticalScroll {
            height: auto;
            max-height: 70vh;
        }

        CustomArgsModal .input-row {
            width: 100%;
            height: 1;
            margin-bottom: 1;
        }

        CustomArgsModal .input-row Input {
            width: 70%;
            dock: left;
        }

        CustomArgsModal .input-row .remove-button {
            dock: right;
        }

        CustomArgsModal .input-row .ignore-button {
            margin-left: 1;
        }

        CustomArgsModal #button-container {
            height: 1;
            dock: bottom;
        }

        CustomArgsModal #add-arg {
            dock: left;
        }

        CustomArgsModal #done {
            dock: right;
        }
    """

    def compose(self) -> ComposeResult:
        with Container():
            yield VerticalScroll(id="inputs-container")
            with Horizontal(id="button-container"):
                yield Button("➕ Add", id="add-arg")
                yield Button("Done", id="done")

    def on_mount(self) -> None:
        self.load_saved_args()

    def load_saved_args(self) -> None:
        saved_args = getattr(self.app, "pytest_cmd_args", [])
        inputs_container = self.query_one("#inputs-container")
        inputs_container.remove_children()  # Clear existing inputs

        if saved_args:
            for arg in saved_args:
                new_input = self.add_input(arg)
                inputs_container.mount(new_input)
        else:
            new_input = self.add_input()
            inputs_container.mount(new_input)

        self.focus_last_input()

    def add_input(self, value: str = "") -> Horizontal:
        input_id = f"custom-arg-input-{len(self.query('#inputs-container .input-row'))}"
        input_widget = Input(
            value=value,
            placeholder="Enter a custom pytest argument (e.g., --foo=bar)",
            id=input_id,
        )
        remove_button = Button(
            "🗑️",
            classes="remove-button",
            tooltip="Remove this argument",
            id=f"{input_id}-remove",
        )
        ignore_button = Button(
            "[green]■[/]",
            tooltip="Ignore this argument",
            classes="ignore-button",
            id=f"{input_id}-ignore",
        )

        input_row = Horizontal(
            input_widget, ignore_button, remove_button, classes="input-row"
        )
        return input_row

    def focus_last_input(self) -> None:
        inputs = self.query(Input)
        if inputs:
            inputs.last().focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-arg":
            new_input = self.add_input()
            self.query_one("#inputs-container").mount(new_input)
            self.focus_last_input()
        elif event.button.id == "done":
            self.save_custom_args()
            self.dismiss()
        elif "remove-button" in event.button.classes:
            event.button.parent.remove()

    def save_custom_args(self) -> None:
        custom_args = []
        for input_row in self.query(".input-row"):
            input_widget = input_row.query_one(Input)
            if stripped_value := input_widget.value.strip():
                custom_args.append(stripped_value)
        self.app.pytest_cmd_args = custom_args

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss()


class AppHeader(Horizontal):
    DEFAULT_CSS = """
        AppHeader {
            height: 3;
            background: $background;
            border: grey 50%;

            & > Button {
                margin-left: 1;
            }

            & > #search-tests {
                padding-left: 1;
                dock: right;
                background: $primary;
            }
        }
    """

    def compose(self) -> ComposeResult:
        # yield Label(f"PytestDva [dim]{'0.0.1'}[/]", id="app-title")
        yield Button("🔍", id="search-tests")
        yield RunButton("▷  Run", id="run")
        yield Button("☰ Options", id="options")

    @on(Button.Pressed, "#options")
    def show_custom_args_modal(self) -> None:
        self.app.push_screen(CustomArgsModal())

    @property
    def orisa(self) -> "OrisaApp":
        return cast("OrisaApp", self.app)
