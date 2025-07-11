import gradio as gr
import os

def simple_function(text_input):
    """Einfache Funktion die den Input zurückgibt"""
    return f"Sie haben eingegeben: {text_input}"

# Gradio Interface erstellen
demo = gr.Interface(
    fn=simple_function,
    inputs=gr.Textbox(label="Geben Sie etwas ein"),
    outputs=gr.Textbox(label="Ausgabe"),
    title="Einfaches Gradio Interface",
    description="Ein einfaches Test-Interface ohne spezielle Funktionen"
)

if __name__ == "__main__":
    # Verwende den PORT aus der Umgebungsvariable oder 8000 als Fallback
    port = int(os.environ.get("PORT", 8000))
    demo.launch(server_name="0.0.0.0", server_port=port) 