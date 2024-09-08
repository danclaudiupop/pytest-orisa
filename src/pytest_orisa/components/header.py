from typing import cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.dom import DOMNode
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


class RunButton(Button):
    def on_click(self) -> None:
        self.disabled = True
        self.loading = True
        self.post_message(self.Pressed(self))

    def reset(self) -> None:
        self.disabled = False
        self.loading = False


class PytestCliFlagsModal(ModalScreen):
    DEFAULT_CSS = """
        PytestCliFlagsModal {
            align: center middle;

            & .ignore-button {
                margin-left: 0;
            }

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
                width: 100%;
                height: 1;
                margin-bottom: 1;

                & Input {
                    width: 70%;
                    dock: left;
                }

                & .remove-button {
                    dock: right;
                }
            }

            & #button-container {
                height: 1;
                dock: bottom;
            }

            & #add-flag {
                dock: left;
            }

            & #done {
                dock: right;
            }
        }
    """

    def compose(self) -> ComposeResult:
        with Container():
            yield VerticalScroll(id="inputs-container")
            with Horizontal(id="button-container"):
                yield Button("➕ Add", id="add-flag")
                yield Button("Done", id="done")

    def on_mount(self) -> None:
        self.load_saved_flags()

    def load_saved_flags(self) -> None:
        saved_args = getattr(self.app, "pytest_cli_flags", [])
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
            placeholder="e.g., --foo=bar",
            id=input_id,
        )
        remove_button = Button(
            "🗑️",
            classes="remove-button",
            tooltip="Remove this argument",
            id=f"{input_id}-remove",
        )
        ignore_button = Button(
            "◼",
            tooltip="Ignore this argument",
            classes="ignore-button ignore-active",
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
    def add_new_input(self) -> None:
        new_input = self.add_input()
        self.query_one("#inputs-container").mount(new_input)
        self.focus_last_input()

    @on(Button.Pressed, "#done")
    def done(self) -> None:
        self.save_flags()
        self.dismiss()

    @on(Button.Pressed, ".remove-button")
    def remove_input(self, event: Button.Pressed) -> None:
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
            else:
                button.remove_class("ignore-inactive")
                button.add_class("ignore-active")
                input_row.remove_class("ignored")

    def save_flags(self) -> None:
        args = []
        for input_row in self.query(".input-row"):
            if "ignored" not in input_row.classes:
                input_widget = input_row.query_one(Input)
                if stripped_value := input_widget.value.strip():
                    args.append(stripped_value)
        self.app.pytest_cli_flags = args  # type: ignore

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
                width: 16;
            }

            & > #app-title {
                padding-right: 1;
                dock: right;
            }
        }
    """

    def compose(self) -> ComposeResult:
        yield RunButton("▷  Run", id="run")
        yield Button("🔍 Search", id="search-tests")
        yield Button("☰ CLI Flags", id="cli-flags")
        yield Label(f"Orisa [dim]{'0.0.1'}[/]", id="app-title")

    @on(Button.Pressed, "#cli-flags")
    def show_pytest_cli_flags_modal(self) -> None:
        self.app.push_screen(PytestCliFlagsModal())
