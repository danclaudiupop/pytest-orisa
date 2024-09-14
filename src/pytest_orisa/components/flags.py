from typing import cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.dom import DOMNode
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label



class PytestCliFlagsModal(ModalScreen):
    DEFAULT_CSS = """
        PytestCliFlagsModal {
            align: center middle;

            & .ignore-active {
                color: green;
            }

            & .ignore-inactive {
                color: $text-muted;
            }

            & > Container {
                width: 30%;
                height: auto;
                background: $background;
                border: solid darkgrey 50%;
                padding: 1 2;
            }

            & VerticalScroll {
                height: auto;
                max-height: 70vh;
            }

            & .input-row {
                height: 1;
                margin-bottom: 1;

                & > .ignore-button {
                    background: transparent;
                    dock: left;
                }

                & .remove-button {
                    dock: right;
                }
            }

            & #button-container {
                height: 2;
                dock: bottom;
                border-top: solid darkgrey 50%;
            }

            & #add-flag {
                dock: left;
            }

            & #done {
                dock: right;
            }
        }
    """

    @property
    def inputs_container(self) -> VerticalScroll:
        return self.query_one("#inputs-container", VerticalScroll)

    def compose(self) -> ComposeResult:
        with Container():
            yield VerticalScroll(id="inputs-container")
            with Horizontal(id="button-container"):
                yield Button("➕ Add", id="add-flag")
                yield Button("Done", id="done")

    def on_mount(self) -> None:
        self.load_saved_flags()

    def load_saved_flags(self) -> None:
        saved_flags = getattr(self.app, "pytest_cli_flags", [])
        self.inputs_container.remove_children()  # Clear existing inputs

        if saved_flags:
            for flag, is_active in saved_flags:
                new_input = self.add_input(flag, is_active)
                self.inputs_container.mount(new_input)
        else:
            new_input = self.add_input()
            self.inputs_container.mount(new_input)

        self.focus_last_input()

    def add_input(self, value: str = "", is_active: bool = True) -> Horizontal:
        input_id = f"flag-input-{len(self.inputs_container.query('.input-row'))}"
        input_widget = Input(
            value=value,
            placeholder="e.g., --foo=bar",
            id=input_id,
        )
        remove_button = Button(
            "🗑️",
            classes="remove-button",
            id=f"{input_id}-remove",
        )
        ignore_button = Button(
            "◼",
            tooltip="Disable this flag" if is_active else "Enable this flag",
            classes=f"ignore-button {'ignore-active' if is_active else 'ignore-inactive'}",
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

    @on(Button.Pressed, "#add-flag")
    async def add_new_input(self) -> None:
        new_input = self.add_input()
        await self.inputs_container.mount(new_input)
        self.focus_last_input()

    @on(Button.Pressed, "#done")
    def done(self) -> None:
        self.save_flags()
        self.dismiss()

    @on(Button.Pressed, ".remove-button")
    def remove_input(self, event: Button.Pressed) -> None:
        if len(self.inputs_container.children) > 1:
            cast(Horizontal, event.button.parent).remove()

    @on(Button.Pressed, ".ignore-button")
    def toggle_ignore(self, event: Button.Pressed) -> None:
        button = event.button
        input_row: DOMNode | None = button.parent

        if input_row is not None:
            if "ignore-active" in button.classes:
                button.remove_class("ignore-active")
                button.add_class("ignore-inactive")
                input_row.add_class("ignored")
                button.tooltip = "Enable this flag"
            else:
                button.remove_class("ignore-inactive")
                button.add_class("ignore-active")
                input_row.remove_class("ignored")
                button.tooltip = "Disable this flag"

    def save_flags(self) -> None:
        flags = set()
        for input_row in self.inputs_container.query(".input-row"):
            input_widget = input_row.query_one(Input)
            ignore_button = input_row.query_one(".ignore-button")
            is_active = "ignore-active" in ignore_button.classes
            if stripped_value := input_widget.value.strip():
                flags.add((stripped_value, is_active))

        self.app.pytest_cli_flags = list(flags)  # type: ignore

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss()
