import gradio as gr

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
    demo.launch(server_name="0.0.0.0", server_port=8000) 