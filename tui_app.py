from textual.app import App, ComposeResult
from textual.widgets import Input, Static, Header, Footer
from textual.containers import VerticalScroll, Vertical
import threading

def run_tui(text_queue, trigger_event, status_val):
    class JOITUI(App):
        CSS = """
        Screen { align: center middle; }
        #chat_history { height: 1fr; border: solid #333; padding: 1; }
        #input_bar { height: 3; border: solid #444; }
        """

        def compose(self) -> ComposeResult:
            yield Header()
            yield VerticalScroll(Static("JOI 2.0 Sistemi Başlatıldı. Bekleniyor...", id="chat_history"))
            yield Input(placeholder="Bir komut yazın ve enter'a basın...", id="input_bar")
            yield Footer()

        def on_input_submitted(self, event: Input.Submitted):
            text_queue.put(event.value)
            self.query_one("#input_bar").value = ""
            self.query_one("#chat_history").update(f"Sen: {event.value}")

    app = JOITUI()
    app.run()