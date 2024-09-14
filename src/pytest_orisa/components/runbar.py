from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Button, Static


class RunButton(Button):
    DEFAULT_CSS = """
        RunButton > LoadingIndicator {
            color: $primary;
            width: 100%;
            content-align: center middle;
        }

        RunButton > LoadingIndicator.-textual-loading-indicator {
            background: transparent;
        }

    """

    def on_click(self) -> None:
        self.disabled = True
        self.loading = True
        self.post_message(self.Pressed(self))

    def reset(self) -> None:
        self.disabled = False
        self.loading = False


class NodePreview(Container):
    DEFAULT_CSS = """
        NodePreview {
            color: $text-muted;
            background: $surface;

            & > #show-code {
                dock: right;
                margin-right: 1;
            }

            #preview {
                margin-left: 1;
            }
             
        }
    """

    node_data = reactive(None)

    def compose(self) -> ComposeResult:
        self.can_focus = False
        yield Static("", id="preview")
        yield Button("</> Show code", id="show-code")
        self.display = False

    def watch_node_data(self, node_data) -> None:
        preview: Static = self.query_one("#preview", Static)
        show_code: Button = self.query_one("#show-code", Button)
        if node_data:
            node_type = node_data["type"]

            self.display = True
            path = self.app.build_breadcrumb_from_path()
            preview.update(f"[cyan]{node_type.upper()[0]}[/] | {path} ")
            show_code.display = node_type != "DIR"


class RunBar(Horizontal):
    DEFAULT_CSS = """
        RunBar {
            height: 3;
            background: $background;
            padding-top: 1;
            padding-bottom: 1;
 
            & > Button {
                margin-right: 1;
                width: 16;
                dock: right;
            }

        }
    """

    def compose(self) -> ComposeResult:
        yield RunButton("▷  Run", id="run")
        yield NodePreview()
