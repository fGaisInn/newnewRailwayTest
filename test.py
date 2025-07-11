import gradio as gr
import os

def simple_calculator(a, b, operation):
    """Einfacher Taschenrechner"""
    if operation == "Addieren":
        return a + b
    elif operation == "Subtrahieren":
        return a - b
    elif operation == "Multiplizieren":
        return a * b
    elif operation == "Dividieren":
        return a / b if b != 0 else "Fehler: Division durch Null"
    else:
        return "Unbekannte Operation"

def text_analyzer(text):
    """Analysiert einen Text und gibt Statistiken zurück"""
    if not text.strip():
        return "Bitte geben Sie einen Text ein."
    
    words = text.split()
    characters = len(text)
    characters_no_spaces = len(text.replace(" ", ""))
    sentences = text.count('.') + text.count('!') + text.count('?')
    
    # Einfache Wortfrequenz-Analyse
    word_freq = {}
    for word in words:
        clean_word = word.lower().strip('.,!?;:')
        if clean_word:
            word_freq[clean_word] = word_freq.get(clean_word, 0) + 1
    
    # Top 5 häufigste Wörter
    top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
    
    result = f"""
    **Textanalyse:**
    
    • Wörter: {len(words)}
    • Zeichen (mit Leerzeichen): {characters}
    • Zeichen (ohne Leerzeichen): {characters_no_spaces}
    • Sätze: {sentences}
    • Durchschnittliche Wortlänge: {characters_no_spaces/len(words):.1f} Zeichen
    
    **Häufigste Wörter:**
    """
    
    for word, count in top_words:
        result += f"• '{word}': {count}x\n"
    
    return result

def number_statistics(numbers):
    """Berechnet einfache Statistiken für Zahlen"""
    if not numbers:
        return "Bitte geben Sie Zahlen ein."
    
    try:
        num_list = [float(x.strip()) for x in numbers.split(',') if x.strip()]
        if not num_list:
            return "Keine gültigen Zahlen gefunden."
        
        total = sum(num_list)
        count = len(num_list)
        average = total / count
        min_val = min(num_list)
        max_val = max(num_list)
        
        result = f"""
        **Statistiken für Ihre Zahlen:**
        
        • Summe: {total:.2f}
        • Durchschnitt: {average:.2f}
        • Minimum: {min_val:.2f}
        • Maximum: {max_val:.2f}
        • Anzahl der Werte: {count}
        """
        return result
    except ValueError:
        return "Fehler: Bitte geben Sie nur Zahlen ein, getrennt durch Kommas."

# Erstelle die Gradio-Interface
with gr.Blocks(title="Einfache Gradio App", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🚀 Willkommen zu meiner einfachen Gradio App!")
    gr.Markdown("Diese App läuft auf Railway und bietet verschiedene nützliche Funktionen.")
    
    with gr.Tabs():
        # Tab 1: Taschenrechner
        with gr.TabItem("🧮 Taschenrechner"):
            gr.Markdown("### Einfacher Taschenrechner")
            
            with gr.Row():
                with gr.Column():
                    num1 = gr.Number(label="Erste Zahl", value=10)
                    num2 = gr.Number(label="Zweite Zahl", value=5)
                    operation = gr.Dropdown(
                        choices=["Addieren", "Subtrahieren", "Multiplizieren", "Dividieren"],
                        label="Operation",
                        value="Addieren"
                    )
                    calc_btn = gr.Button("Berechnen", variant="primary")
                
                with gr.Column():
                    result = gr.Textbox(label="Ergebnis")
            
            calc_btn.click(
                fn=simple_calculator,
                inputs=[num1, num2, operation],
                outputs=result
            )
        
        # Tab 2: Statistik-Rechner
        with gr.TabItem("📈 Statistik-Rechner"):
            gr.Markdown("### Berechnen Sie Statistiken für Ihre Zahlen")
            
            numbers_input = gr.Textbox(
                label="Zahlen (kommagetrennt)",
                placeholder="1, 2, 3, 4, 5, 6, 7, 8, 9, 10",
                lines=3
            )
            stats_btn = gr.Button("Statistiken berechnen", variant="primary")
            stats_output = gr.Markdown(label="Ergebnisse")
            
            stats_btn.click(
                fn=number_statistics,
                inputs=numbers_input,
                outputs=stats_output
            )
        
        # Tab 3: Text-Analyzer
        with gr.TabItem("📝 Text-Analyzer"):
            gr.Markdown("### Analysieren Sie Ihren Text")
            
            text_input = gr.Textbox(
                label="Text zum Analysieren",
                placeholder="Geben Sie hier Ihren Text ein...",
                lines=5
            )
            analyze_btn = gr.Button("Text analysieren", variant="primary")
            text_output = gr.Markdown(label="Analyse-Ergebnisse")
            
            analyze_btn.click(
                fn=text_analyzer,
                inputs=text_input,
                outputs=text_output
            )
    
    gr.Markdown("---")
    gr.Markdown("### ℹ️ Über diese App")
    gr.Markdown("""
    Diese vereinfachte Gradio-App wurde speziell für Railway entwickelt und bietet:
    - **🧮 Taschenrechner**: Einfache mathematische Operationen
    - **📈 Statistik-Rechner**: Berechnen Sie grundlegende Statistiken für Zahlenlisten
    - **📝 Text-Analyzer**: Analysieren Sie Texte und erhalten Sie Wortstatistiken
    
    Die App ist vollständig responsive und läuft in der Cloud auf Railway!
    """)

if __name__ == "__main__":
    # Railway-spezifische Konfiguration
    port = int(os.environ.get("PORT", 8080))
    # Für Railway: host="0.0.0.0" ist wichtig
    demo.launch(
        server_name="0.0.0.0",
        # server_name="127.0.0.1",
        server_port=port,
        share=False
    )