from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Button, Static


class RunButton(Button):
    DEFAULT_CSS = """
        RunButton {
            width: 15;
            background: $primary;

            & > LoadingIndicator {
                color: black;
                width: 100%;
                content-align: center middle;
            }

            & > LoadingIndicator.-textual-loading-indicator {
                background: transparent;
            }
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
            margin: 0 1;

            & > #show-code {
                dock: right;
            }

        }
    """

    node_data = reactive(None)

    def compose(self) -> ComposeResult:
        self.can_focus = False
        yield Static("", id="preview")
        yield Button("</> Show code", id="show-code")
        self.display = False

    def watch_node_data(self, node_data: dict) -> None:
        if node_data:
            preview: Static = self.query_one("#preview", Static)
            show_code: Button = self.query_one("#show-code", Button)
            node_type = node_data["type"]

            self.display = True
            path = self.app.build_breadcrumb_from_path()  # type: ignore
            preview.update(f"[cyan]{node_type.upper()[0]}[/] | {path} ")
            show_code.display = node_type != "DIR"


class RunBar(Horizontal):
    DEFAULT_CSS = """
        RunBar {
            height: 3;
            background: $background;
            padding: 1 0;
 
            & > #run {
                dock: right;
            }

            & > #search,
            & > #flags {
                margin-right: 1;
                width: auto;
            }

        }
    """

    def compose(self) -> ComposeResult:
        yield Button(" ⌕ ", id="search")
        yield Button(" ☰ ", id="flags")
        yield RunButton("▷  Run", id="run")
        yield NodePreview()
