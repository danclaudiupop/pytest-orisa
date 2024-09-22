from textual.app import ComposeResult
from textual.widgets import Footer, Label

from pytest_orisa.version import VERSION


class OrisaFooter(Footer):
    DEFAULT_CSS = """
        OrisaFooter {
            & > Label {
                margin-right: 1;
                dock: right;
            }
        }
    """

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield Label(f"Orisa [dim]{VERSION}[/]", id="app-title")
