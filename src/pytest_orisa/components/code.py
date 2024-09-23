import os
import platform
import subprocess
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Grid, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, TextArea


class CodeViewerScreen(ModalScreen):
    DEFAULT_CSS = """
        CodeViewerScreen {
            align: right middle;
            
            & > #code-grid {
                grid-gutter: 0;
                grid-size: 1 2;
                grid-rows: 1 100%;
                padding: 1;
                height: 90%;
                border: solid grey;
                background: $background;

                & > #code-viewer {
                    border: hkey $primary;
                    padding: 1;
                }

                & > Horizontal > Button {
                    margin-right: 1;
                }
            }
        }
    """

    BINDINGS = [("escape", "app.pop_screen", "Pop screen")]

    def __init__(self, current_selected_node: dict, location: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.current_selected_node = current_selected_node
        self.location = location

    def compose(self) -> ComposeResult:
        textarea = TextArea(
            text=Path(self.current_selected_node["path"]).read_text(encoding="utf-8"),
            show_line_numbers=True,
            language="python",
            read_only=True,
            id="code-viewer",
        )
        textarea.move_cursor((self.current_selected_node["lineno"], 0), center=True)

        grid = Grid(
            Horizontal(
                Button("Close", variant="primary", id="cancel"),
                Button("Open file in Editor", variant="primary", id="open-in-editor"),
            ),
            textarea,
            id="code-grid",
        )
        grid.border_title = self.location
        grid.styles.border_title_align = "center"
        yield grid

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.app.pop_screen()
        elif event.button.id == "open-in-editor":
            file_path = self.current_selected_node["path"]

            editor = os.getenv("EDITOR", "code")
            # handle better this part
            system = platform.system()

            if system == "Darwin":
                if editor == "code":
                    subprocess.run(["open", "-a", "Visual Studio Code", file_path])
                else:
                    subprocess.run([editor, file_path])
            elif system == "Linux":
                if editor == "code":
                    subprocess.run(["code", file_path])
                else:
                    subprocess.run([editor, file_path])
            elif system == "Windows":
                if editor == "code":
                    subprocess.run(["code", file_path], shell=True)
                else:
                    subprocess.run([editor, file_path], shell=True)
