from typing import TYPE_CHECKING, cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Select
from textual.widgets._select import SelectCurrent

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


class LoggingModal(ModalScreen):
    BINDINGS = [("escape", "app.pop_screen", "Close")]

    DEFAULT_CSS = """
    LoggingModal {
        align: center middle;
    }

    #modal-container {
        width: 60%;
        height: 60%;
        border: thick $primary 80%;
        background: $surface;
        padding: 1 2;
    }

    #modal-title {
        text-style: bold;
        content-align: center middle;
        width: 100%;
        height: 3;
        background: $primary 20%;
        color: $text;
    }

    #logging-modal {
        height: 100%;
        margin: 1 0;
        background: $panel;
        border: round $primary;
        padding: 1 2;
    }

    Input {
        margin: 0 0;
        height: 1;
    }

    Select {
        margin: 0 0;
        height: 3;
    }

    #button-container {
        width: 100%;
        height: 3;
        dock: bottom;
    }

    Button {
        margin: 1 1;
    }

    #save-logging {
        dock: left;
        background: $success 50%;
    }

    #cancel-logging {
        dock: right;
        background: $error 50%;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-container"):
            yield Label("Logging Options", id="modal-title")
            with VerticalScroll(id="logging-modal"):
                yield Input(placeholder="Log Level", id="log-level")
                yield Input(placeholder="Log Format", id="log-format")
                yield Input(placeholder="Log Date Format", id="log-date-format")
                yield Input(placeholder="CLI Log Level", id="log-cli-level")
                yield Input(placeholder="CLI Log Format", id="log-cli-format")
                yield Input(placeholder="CLI Log Date Format", id="log-cli-date-format")
                yield Input(placeholder="Log File Path", id="log-file")
                yield Select(
                    [(mode, mode) for mode in ["w", "a"]],
                    prompt="Log File Mode",
                    id="log-file-mode",
                )
                yield Input(placeholder="Log File Level", id="log-file-level")
                yield Input(placeholder="Log File Format", id="log-file-format")
                yield Input(
                    placeholder="Log File Date Format", id="log-file-date-format"
                )
                yield Input(placeholder="Log Auto Indent", id="log-auto-indent")
                yield Input(placeholder="Disable Logger", id="log-disable")
            with Horizontal(id="button-container"):
                yield Button("Save", id="save-logging")
                yield Button("Cancel", id="cancel-logging")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-logging":
            # Here you would save the logging options
            self.dismiss(True)
        elif event.button.id == "cancel-logging":
            self.dismiss(False)


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

            & > #showlocals {
                border: none;
                background: $background;
            }
        }
    """

    def compose(self) -> ComposeResult:
        # yield Label(f"PytestDva [dim]{'0.0.1'}[/]", id="app-title")
        yield Button("🔍", id="search-tests")

        yield RunButton("▷  Run", id="run")
        yield Select(
            [(value, value) for value in ["-q", "-v", "-vv"]],
            prompt="Set verbosity",
            id="set-verbosity",
        )
        yield Select(
            [
                (value, value)
                for value in [
                    "--tb=auto",
                    "--tb=long",
                    "--tb=short",
                    "--tb=line",
                    "--tb=native",
                    "--tb=no",
                ]
            ],
            value="--tb=auto",
            allow_blank=False,
            id="set-traceback",
        )
        checkbox = Checkbox(
            "showlocals", id="showlocals", tooltip="Show local variables in tracebacks"
        )
        checkbox.BUTTON_INNER = "•"
        yield checkbox

        yield Button("⚙ Logging", id="live-logs")

    @on(Select.Changed, selector="#set-verbosity")
    def on_verbosity_selected(self, event: Select.Changed) -> None:
        if not event.select.is_blank():
            select_current: SelectCurrent = self.query_one(
                "#set-verbosity > SelectCurrent", expect_type=SelectCurrent
            )

            select_current.update(f"verbosity ({event.value})")
            self.orisa.pytest_cmd_args["verbosity"] = event.value
        else:
            self.orisa.pytest_cmd_args.pop("verbosity", None)

    @on(Select.Changed, selector="#set-traceback")
    def on_traceback_selected(self, event: Select.Changed) -> None:
        self.orisa.pytest_cmd_args["traceback"] = event.value

    @on(Checkbox.Changed, selector="#showlocals")
    def on_showlocal_checked(self, event: Checkbox.Changed) -> None:
        if event.value is True:
            self.orisa.pytest_cmd_args["showlocals"] = "--showlocals"
        else:
            self.orisa.pytest_cmd_args.pop("showlocals", None)

    @on(Button.Pressed, "#live-logs")
    def show_logging_modal(self) -> None:
        self.app.push_screen(LoggingModal())

    @property
    def orisa(self) -> "OrisaApp":
        return cast("OrisaApp", self.app)
