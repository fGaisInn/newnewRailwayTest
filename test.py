import os
import gradio as gr
import asana
from asana.rest import ApiException
from dotenv import load_dotenv
from datetime import datetime, timedelta
import json
import re
import openai
from pydantic import BaseModel, ConfigDict
import difflib
import pandas as pd
import docx

# Debug-Logging-Funktion
def debug_log(message):
    with open("debug.log", "a", encoding="utf-8") as f:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[{timestamp}] {message}\n")

# Lade Umgebungsvariablen
load_dotenv()

# OpenAI API Key setzen
openai.api_key = os.getenv('OPENAI_API_KEY')

# Asana Client konfigurieren (OpenAPI)
configuration = asana.Configuration()
configuration.access_token = os.getenv('ASANA_API_TOKEN')
api_client = asana.ApiClient(configuration)
workspaces_api = asana.WorkspacesApi(api_client)
tasks_api = asana.TasksApi(api_client)
projects_api = asana.ProjectsApi(api_client)
users_api = asana.UsersApi(api_client)

# Pydantic-Konfiguration für die Anwendung
class Config:
    arbitrary_types_allowed = True

# Anzahl maximal unterstützter Aufgaben
MAX_TASKS = 10

# Liste der auszuschließenden (externen) Mitglieder
EXCLUDED_USERS = [
    "Tanja Fery",
    "Elisabeth Emprechtinger",
    "Ole Middendorf",
    "Martin Mandl",
    "Nicola Rudolf",
    "Elisabeth Laimer",
    "Sabine Pupeter",
    "Stefan Wimmer",  
    "Julia Bauinger",
    "Sandra Stadler",
    "Dr. Christian Zeilinger",
    "antonia.mair@ymail.com",
    "Stefanie Duringer",
    "j.hauska@tti-group.at",
    "anna.pointner@seocon.eu",
    "reiter@skymusicgroup.com",
    "marketing@elmag.at",
    "f.landwehr@clicks.digital",
    "st.wallner@outlook.com",
    "Alexander Ripota",
    "Alexandra"
]

def get_workspaces():
    """Holt alle verfügbaren Workspaces"""
    try:
        workspaces = list(workspaces_api.get_workspaces({}))
        workspace_dict = {}
        for workspace in workspaces:
            if isinstance(workspace, dict) and 'name' in workspace and 'gid' in workspace:
                workspace_dict[workspace['name']] = workspace['gid']
        return workspace_dict
    except ApiException as e:
        print(f"Fehler beim Abrufen der Workspaces: {str(e)}")
        return {}

def get_projects(workspace_gid):
    """Holt alle Projekte eines Workspaces"""
    if not workspace_gid:
        return {}
    try:
        opts = {
            'workspace': workspace_gid,
            'archived': False,
            'opt_fields': 'name,gid'
        }
        projects = list(projects_api.get_projects(opts))
        project_dict = {}
        for project in projects:
            if isinstance(project, dict) and 'name' in project and 'gid' in project:
                project_dict[project['name']] = project['gid']
        return project_dict
    except ApiException as e:
        print(f"Fehler beim Abrufen der Projekte: {str(e)}")
        return {}

def get_workspace_users(workspace_gid):
    """Holt alle Benutzer eines Workspaces, nur @innpuls.at-Adressen"""
    if not workspace_gid:
        return {}
    try:
        opts = {'workspace': workspace_gid, 'opt_fields': 'name,email,gid'}
        users = list(users_api.get_users(opts))
        # Debug: Logge alle User mit Name und E-Mail
        for user in users:
            name = user.get('name', '') if isinstance(user, dict) else str(user)
            email = user.get('email', '') if isinstance(user, dict) else ''
            debug_log(f"User: {name} | Email: {email}")
        user_dict = {}
        for user in users:
            if isinstance(user, dict) and 'name' in user and 'gid' in user:
                email = user.get('email', '')
                if email.endswith('@innpuls.at'):
                    user_dict[user['name']] = user['gid']
        return user_dict
    except ApiException as e:
        print(f"Fehler beim Abrufen der Benutzer: {str(e)}")
        return {}

def get_tasks(project_gid):
    """Holt alle Aufgaben eines Projekts und sortiert sie alphabetisch"""
    if not project_gid:
        print("DEBUG: Keine project_gid übergeben")
        return {}
    try:
        opts = {
            'project': project_gid,
            'opt_fields': 'name,gid,completed',
            'completed_since': 'now'
        }
        tasks = list(tasks_api.get_tasks(opts))
        task_dict = {}
        task_list = []
        for task in tasks:
            if isinstance(task, dict) and 'name' in task and 'gid' in task:
                if not task.get('completed', False):
                    task_list.append(task)
        task_list.sort(key=lambda x: x['name'].lower())
        for task in task_list:
            task_dict[task['name']] = task['gid']
        print(f"DEBUG: Gefundene Aufgaben (sortiert): {task_dict}")
        return task_dict
    except ApiException as e:
        print(f"Fehler beim Abrufen der Aufgaben: {str(e)}")
        return {}

def update_tasks(workspace_name, project_name):
    if not workspace_name or not project_name:
        return gr.update(choices=[])
    workspaces = get_workspaces()
    workspace_gid = workspaces.get(workspace_name)
    if workspace_gid:
        projects = get_projects(workspace_gid)
        project_gid = projects.get(project_name)
        if project_gid:
            tasks = get_tasks(project_gid)
            task_names = sorted(list(tasks.keys()))
            return gr.update(choices=task_names)
    return gr.update(choices=[])

def analyze_text_with_ai(protocol_text):
    """Analysiert den Text mit OpenAI und extrahiert Aufgaben"""
    try:
        prompt = f"""Analysiere das folgende Meetingprotokoll und extrahiere daraus Aufgaben.
        Für jede Aufgabe solltest du folgende Informationen identifizieren:
        - Name der Aufgabe
        - Beschreibung (Details, Kontext, Anforderungen)
        - Wer könnte dafür verantwortlich sein (basierend auf dem Kontext)
        - Wann sollte die Aufgabe erledigt sein (basierend auf dem Kontext)

        Protokoll:
        {protocol_text}

        Gib die Antwort als JSON-Array zurück, wobei jedes Element ein Objekt mit den Feldern 'name', 'description', 'assignee' und 'due_date' enthält.
        Wenn du keine klare Zuweisung oder kein klares Datum findest, lass diese Felder leer.
        Das Datum sollte im Format YYYY-MM-DD sein.
        """

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Du bist ein Experte für die Analyse von Meetingprotokollen und die Extraktion von Aufgaben."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        # Extrahiere die JSON-Antwort
        tasks = json.loads(response.choices[0].message.content)
        
        # Stelle sicher, dass das Datum im richtigen Format ist
        for task in tasks:
            if task.get('due_date'):
                try:
                    # Versuche das Datum zu parsen und zu formatieren
                    date_obj = datetime.strptime(task['due_date'], '%Y-%m-%d')
                    # Für die Anzeige im UI: deutsches Format
                    task['due_date'] = date_obj.strftime('%d.%m.%Y')
                except ValueError:
                    # Wenn das Datum nicht im richtigen Format ist, setze es auf None
                    task['due_date'] = None
            else:
                task['due_date'] = None

        return tasks

    except Exception as e:
        print(f"Fehler bei der KI-Analyse: {str(e)}")
        return []

def create_tasks_in_asana(tasks, workspace_name, project_name):
    """Erstellt die Aufgaben in Asana"""
    try:
        # Hole Workspace und Projekt IDs
        workspaces = get_workspaces()
        workspace_gid = workspaces.get(workspace_name)
        if not workspace_gid:
            return "❌ Fehler: Workspace nicht gefunden"
        
        projects = get_projects(workspace_gid)
        project_gid = projects.get(project_name)
        if not project_gid:
            return "❌ Fehler: Projekt nicht gefunden"
        
        # Hole Benutzer
        users = get_workspace_users(workspace_gid)
        user_names = set(users.keys())
        
        # Erstelle die Aufgaben
        created_tasks = []
        for task in tasks:
            try:
                task_data = {
                    "name": task['name'],
                    "notes": task.get('description', ''),
                    "workspace": workspace_gid,
                    "projects": [project_gid]
                }
                # Füge Bearbeiter hinzu, wenn vorhanden und gültig
                assignee = task.get('assignee')
                if assignee and assignee in user_names:
                    task_data["assignee"] = users[assignee]
                # Füge Fälligkeitsdatum hinzu
                if task.get('due_date'):
                    task_data["due_on"] = task['due_date']
                # API-Aufruf mit opts
                opts = {"opt_fields": "name,gid,completed"}
                result = tasks_api.create_task({"data": task_data}, opts)
                created_tasks.append(f"✅ {task['name']}")
            except Exception as e:
                created_tasks.append(f"❌ {task['name']} - Fehler: {str(e)}")
        return "\n".join(created_tasks)
    except Exception as e:
        return f"❌ Fehler beim Erstellen der Aufgaben: {str(e)}"

def update_project_choices(workspace_name):
    """Aktualisiert die Projektliste basierend auf dem ausgewählten Workspace"""
    if not workspace_name:
        return gr.Dropdown(choices=[])
    
    workspaces = get_workspaces()
    workspace_gid = workspaces.get(workspace_name)
    
    if workspace_gid:
        projects = get_projects(workspace_gid)
        project_names = sorted(list(projects.keys()))
        return gr.Dropdown(choices=project_names)
    return gr.Dropdown(choices=[])

def update_user_choices(workspace_name):
    """Aktualisiert die Benutzerliste basierend auf dem ausgewählten Workspace"""
    if not workspace_name:
        return gr.Dropdown(choices=[])
    
    workspaces = get_workspaces()
    workspace_gid = workspaces.get(workspace_name)
    
    if workspace_gid:
        users = get_workspace_users(workspace_gid)
        user_names = sorted(list(users.keys()))
        return gr.Dropdown(choices=user_names)
    return gr.Dropdown(choices=[])

def update_tasks_on_project_change(workspace_name, project_name):
    print(f"DEBUG: update_tasks_on_project_change aufgerufen mit workspace={workspace_name}, project={project_name}")
    if not workspace_name or not project_name:
        print("DEBUG: Kein Workspace oder Projekt ausgewählt")
        dropdown = gr.Dropdown(choices=["(Bitte Projekt wählen)"], value=None, interactive=True)
        suggestion = gr.Dropdown(choices=["(Bitte Projekt wählen)"], value=None, interactive=False)
        return dropdown, suggestion
    try:
        workspaces = get_workspaces()
        print(f"DEBUG: Gefundene Workspaces: {workspaces}")
        workspace_gid = workspaces.get(workspace_name)
        print(f"DEBUG: Workspace GID: {workspace_gid}")
        if not workspace_gid:
            print("DEBUG: Keine Workspace GID gefunden")
            dropdown = gr.Dropdown(choices=["(Kein Workspace gefunden)"], value=None, interactive=True)
            suggestion = gr.Dropdown(choices=["(Kein Workspace gefunden)"], value=None, interactive=False)
            return dropdown, suggestion
        projects = get_projects(workspace_gid)
        print(f"DEBUG: Gefundene Projekte: {projects}")
        project_gid = projects.get(project_name)
        print(f"DEBUG: Projekt GID: {project_gid}")
        if not project_gid:
            print("DEBUG: Keine Projekt GID gefunden")
            dropdown = gr.Dropdown(choices=["(Kein Projekt gefunden)"], value=None, interactive=True)
            suggestion = gr.Dropdown(choices=["(Kein Projekt gefunden)"], value=None, interactive=False)
            return dropdown, suggestion
        tasks = get_tasks(project_gid)
        print(f"DEBUG: Gefundene Aufgaben: {tasks}")
        if not tasks:
            print("DEBUG: Keine Aufgaben gefunden")
            dropdown = gr.Dropdown(choices=["(Keine Aufgaben gefunden)"], value=None, interactive=True)
            suggestion = gr.Dropdown(choices=["(Keine Aufgaben gefunden)"], value=None, interactive=False)
            return dropdown, suggestion
        task_names = sorted(list(tasks.keys()))
        print(f"DEBUG: Sortierte Aufgaben: {task_names}")
        dropdown = gr.Dropdown(choices=task_names, value=None, interactive=True)
        suggestion = gr.Dropdown(choices=task_names, value=None, interactive=False)
        return dropdown, suggestion
    except Exception as e:
        print(f"DEBUG: Fehler in update_tasks_on_project_change: {str(e)}")
        dropdown = gr.Dropdown(choices=["(Fehler beim Laden)"], value=None, interactive=True)
        suggestion = gr.Dropdown(choices=["(Fehler beim Laden)"], value=None, interactive=False)
        return dropdown, suggestion

def create_tasks(result_markdown, workspace_name, project_gid, *assignee_and_due_values):
    """Erstellt die Aufgaben in Asana direkt im gewählten Projekt (ohne Unteraufgabenstruktur)"""
    try:
        debug_log("create_tasks wurde aufgerufen")
        debug_log(f"workspace_name = {workspace_name}")
        debug_log(f"project_gid = {project_gid}")
        debug_log(f"result_markdown = {result_markdown}")
        debug_log(f"assignee_and_due_values = {assignee_and_due_values}")
        
        if not result_markdown or result_markdown.startswith("Bitte") or result_markdown.startswith("❌"):
            return "Bitte analysiere zuerst das Protokoll."
        
        # Extrahiere die Aufgaben
        tasks = []
        current_task = {}
        idx = 0
        num_fields = int(len(assignee_and_due_values) / 2)
        assignees = assignee_and_due_values[:num_fields]
        due_dates = assignee_and_due_values[num_fields:]
        today_str = datetime.today().strftime("%Y-%m-%d")
        
        debug_log(f"Anzahl der Assignees: {len(assignees)}")
        debug_log(f"Anzahl der Due Dates: {len(due_dates)}")
        
        for line in result_markdown.split('\n'):
            if line.startswith('- **'):
                if current_task:
                    if idx < len(assignees):
                        current_task['assignee'] = assignees[idx]
                    # Setze heutiges Datum, falls kein due_date
                    if idx < len(due_dates) and due_dates[idx] and due_dates[idx] != "YYYY-MM-DD":
                        current_task['due_date'] = due_dates[idx]
                    else:
                        current_task['due_date'] = today_str
                    tasks.append(current_task)
                    debug_log(f"Aufgabe extrahiert: {json.dumps(current_task, ensure_ascii=False, indent=2)}")
                    current_task = {}
                    idx += 1
                task_name = line.replace('- **', '').replace('**', '').strip()
                current_task = {'name': task_name}
            elif '📅 Fällig am:' in line:
                current_task['due_date'] = line.split(':', 1)[1].strip()
            elif '📝 Kontext:' in line:
                current_task['context'] = line.split(':', 1)[1].strip()
        if current_task:
            if idx < len(assignees):
                current_task['assignee'] = assignees[idx]
            # Setze heutiges Datum, falls kein due_date
            if idx < len(due_dates) and due_dates[idx] and due_dates[idx] != "YYYY-MM-DD":
                current_task['due_date'] = due_dates[idx]
            else:
                current_task['due_date'] = today_str
            tasks.append(current_task)
            debug_log(f"Letzte Aufgabe extrahiert: {json.dumps(current_task, ensure_ascii=False, indent=2)}")
        
        debug_log(f"Alle extrahierten Aufgaben: {json.dumps(tasks, ensure_ascii=False, indent=2)}")
        
        if not tasks:
            return "Keine Aufgaben zum Erstellen gefunden."
        
        # Hole Workspace und Projekt-IDs
        workspaces = get_workspaces()
        workspace_gid = workspaces.get(workspace_name)
        user_dict = get_workspace_users(workspace_gid)
        # Prüfe IDs
        if not workspace_gid:
            return f"❌ Fehler: Workspace-ID für '{workspace_name}' nicht gefunden."
        if not project_gid:
            return f"❌ Fehler: Projekt-ID nicht gefunden oder nicht ausgewählt."
        
        # Erstelle die Aufgaben in Asana direkt im Projekt
        created_tasks = []
        for task in tasks:
            try:
                # Erstelle die Task-Daten im korrekten Format
                task_data = {
                    "data": {
                        "name": task['name'],
                        "notes": task.get('context', ''),
                        "workspace": workspace_gid,
                        "projects": [str(project_gid)]  # Verwende projects für Hauptaufgaben
                    }
                }
                
                # Assignee
                if task.get('assignee') and user_dict.get(task['assignee']):
                    task_data["data"]["assignee"] = user_dict[task['assignee']]
                
                # Due Date
                if task.get('due_date'):
                    try:
                        parsed_date = datetime.strptime(task['due_date'], "%Y-%m-%d")
                        task_data["data"]["due_on"] = parsed_date.strftime("%Y-%m-%d")
                    except ValueError:
                        pass
                
                debug_log(f"Task Data für API-Aufruf: {json.dumps(task_data, ensure_ascii=False, indent=2)}")
                
                # Debug-Ausgaben für API-Aufruf
                api_data = {"data": task_data["data"]}
                api_opts = {"opt_fields": "name,gid,completed"}
                debug_log(f"API Data: {api_data}")
                debug_log(f"API Options: {api_opts}")
                debug_log(f"API Call: tasks_api.create_task({api_data}, {api_opts})")
                
                # API-Aufruf mit korrekter Struktur und Reihenfolge der Parameter
                result = tasks_api.create_task(api_data, api_opts)
                debug_log(f"API Response: {result}")
                
                created_name = None
                if hasattr(result, '_data'):
                    # Wenn result ein Objekt mit _data Attribut ist
                    data = result._data
                    if isinstance(data, dict):
                        created_name = data.get('name')
                elif isinstance(result, dict):
                    # Wenn result direkt ein Dictionary ist
                    if 'data' in result:
                        created_name = result['data'].get('name')
                    else:
                        created_name = result.get('name')
                
                created_tasks.append({
                    "name": created_name or task['name'],
                    "assignee": task.get('assignee', ''),
                    "due_date": task.get('due_date', ''),
                    "status": "erstellt"
                })
            except Exception as e:
                print("Unexpected Error:", str(e))  # Debug-Ausgabe
                created_tasks.append({
                    "name": task['name'],
                    "error": str(e),
                    "status": "fehlgeschlagen"
                })
        
        # Formatiere die Ausgabe
        output = "### Erstellte Aufgaben:\n\n"
        for task in created_tasks:
            output += f"- {task['name']}\n"
            if task.get('assignee'):
                output += f"  👤 Zugewiesen an: {task['assignee']}\n"
            if task.get('due_date'):
                output += f"  📅 Fällig am: {task['due_date']}\n"
            if task.get('status'):
                status_emoji = "✅" if task['status'] == "erstellt" else "❌"
                output += f"  {status_emoji} Status: {task['status']}\n"
            if task.get('error'):
                output += f"  ❗ Fehler: {task['error']}\n"
            output += "\n"
        return output
    except Exception as e:
        print("Unexpected Error:", str(e))  # Debug-Ausgabe
        return f"❌ Fehler beim Erstellen der Aufgaben: {str(e)}"

def suggest_matching_parent_task(protocol_text, parent_task_names):
    """Analysiert den Protokolltext und schlägt die passendste Parent-Task vor."""
    # Konvertiere Text und Aufgabennamen zu Kleinbuchstaben für besseren Vergleich
    text_lower = protocol_text.lower()
    # Extrahiere potenzielle Projekt-IDs aus dem Text
    project_ids = re.findall(r'[A-Z]{3,4}(?:[A-Z0-9]+)?', protocol_text)
    project_ids = [pid.lower() for pid in project_ids]
    # Extrahiere Schlüsselwörter aus dem Text
    text_keywords = set(text_lower.split())
    # Schlüsselwörter und ihre Gewichtung
    keywords = {
        'website': 3,
        'web': 2,
        'entwicklung': 2,
        'relaunch': 5,
        'wordpress': 2,
        'aktualisierung': 2,
        'design': 2,
        'startseite': 3,
        'mockup': 3,
        'staging': 2
    }
    # Bewertung für jede Aufgabe
    task_scores = {}
    for task_name in parent_task_names:
        score = 0
        task_lower = task_name.lower()
        # Extrahiere Projekt-ID aus dem Task-Namen
        task_match = re.search(r'([A-Z]{3,4}[A-Z0-9]*)', task_name)
        if task_match:
            task_project_id = task_match.group(1).lower()
            # Prüfe auf exakte Projekt-ID Übereinstimmungen
            if task_project_id in project_ids:
                score += 50
            else:
                for pid in project_ids:
                    if pid[:3] == task_project_id[:3]:
                        score += 30
        # Prüfe auf thematische Übereinstimmungen
        task_words = set(task_lower.split())
        # Score für gemeinsame Wörter
        common_words = text_keywords.intersection(task_words)
        score += len(common_words) * 3
        # Score basierend auf Schlüsselwörtern
        for keyword, weight in keywords.items():
            if keyword in task_lower:
                score += weight
            if keyword in text_lower:
                score += weight
        # Zeitliche Relevanz
        if "2025" in task_name:
            score += 3
        elif "2024" in task_name:
            score += 2
        # Speichere Score nur für relevante Aufgaben
        if score > 0:
            task_scores[task_name] = score
    # Sortiere Aufgaben nach Score
    sorted_tasks = sorted(
        task_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )
    # Debug-Ausgabe der Scores
    debug_log("\nParent-Task-Scores:")
    for task, score in sorted_tasks[:10]:
        debug_log(f"{task}: {score}")
    # Gib die Top-Aufgabe zurück
    if sorted_tasks:
        return sorted_tasks[0][0]
    elif parent_task_names:
        return parent_task_names[0]
    else:
        return None

def excel_to_text(file_path):
    """Wandelt eine Excel-Datei in einen gut lesbaren Text (CSV-ähnlich) um, auch ohne Header."""
    try:
        df = pd.read_excel(file_path, header=None)
        # Prüfe, ob die erste Zeile Header ist (grob: viele verschiedene Werte)
        first_row = df.iloc[0].tolist()
        unique_in_first_row = len(set(first_row))
        # Wenn die erste Zeile sehr unterschiedlich ist, nehme sie als Header
        if unique_in_first_row == len(first_row):
            df.columns = first_row
            df = df[1:]
        # Erzeuge Text (CSV-ähnlich)
        text_lines = []
        for row in df.itertuples(index=False, name=None):
            line = ', '.join([str(cell) for cell in row if pd.notna(cell)])
            if line.strip():
                text_lines.append(line)
        return '\n'.join(text_lines)
    except Exception as e:
        debug_log(f"Fehler beim Umwandeln von Excel in Text: {str(e)}")
        return ""

def word_to_text(file_path):
    """Extrahiert den Text aus einer Word-Datei (.docx)."""
    try:
        doc = docx.Document(file_path)
        text = '\n'.join([para.text for para in doc.paragraphs if para.text.strip()])
        return text
    except Exception as e:
        debug_log(f"Fehler beim Umwandeln von Word in Text: {str(e)}")
        return ""

def analyze_protocol_and_show(protocol_text, workspace_name, project_name, upload_file=None):
    print("DEBUG: analyze_protocol_and_show wurde aufgerufen")
    print(f"DEBUG: protocol_text: {protocol_text}")
    print(f"DEBUG: workspace_name: {workspace_name}")
    print(f"DEBUG: project_name: {project_name}")
    print(f"DEBUG: upload_file: {upload_file}")
    
    if not workspace_name or (not protocol_text and not upload_file):
        print("DEBUG: Fehlende Eingaben")
        return ([gr.update(visible=False) for _ in range(MAX_TASKS * 5)], [], [], [], None, None, "❌ Bitte füllen Sie alle erforderlichen Felder aus.")
    try:
        combined_text = protocol_text or ""
        if upload_file:
            if str(upload_file).lower().endswith('.xlsx') or str(upload_file).lower().endswith('.xls'):
                file_text = excel_to_text(upload_file)
            elif str(upload_file).lower().endswith('.docx'):
                file_text = word_to_text(upload_file)
            else:
                file_text = ""
            print(f"DEBUG: Umgewandelter Datei-Text: {file_text}")
            if not file_text.strip():
                warn = "❌ Datei konnte nicht in Text umgewandelt werden. Siehe debug.log."
                return ([gr.update(visible=False) for _ in range(MAX_TASKS * 5)] + [[], [], [], [], None, None], warn)
            if combined_text.strip():
                combined_text = combined_text.strip() + "\n" + file_text
            else:
                combined_text = file_text
        # Aufgaben extrahieren (immer über KI)
        tasks = analyze_text_with_ai(combined_text)
        print(f"DEBUG: Extrahierte Aufgaben: {tasks}")
        # User laden
        workspaces = get_workspaces()
        workspace_gid = workspaces.get(workspace_name)
        user_dict = get_workspace_users(workspace_gid)
        user_names = list(user_dict.keys())
        print(f"DEBUG: Verfügbare User: {user_names}")
        # Automatisches Mapping für Assignee
        for task in tasks:
            assignee = task.get('assignee')
            if assignee:
                matches = [uname for uname in user_names if assignee.lower() in uname.lower()]
                if len(matches) == 1:
                    task['assignee'] = matches[0]
                else:
                    task['assignee'] = None
        # Hole bestehende Aufgaben für Vorschlag
        project_names = get_projects(workspace_gid)
        project_gid = project_names.get(project_name)
        parent_tasks_dict = get_tasks(project_gid) if project_gid else {}
        parent_task_names = list(parent_tasks_dict.keys())
        # Erweiterte Vorschlagslogik
        best_match = suggest_matching_parent_task(protocol_text, parent_task_names)
        debug_log(f"Vorgeschlagener Parent-Task: {best_match}")
        # Updates für jede Zeile vorbereiten
        updates = []
        for i in range(MAX_TASKS):
            if i < len(tasks):
                task = tasks[i]
                print(f"DEBUG: Erstelle Update für Aufgabe {i+1}: {task.get('name','')}")
                # Korrektes Mapping der Felder
                name_value = task.get('name', '')
                description_value = task.get('description', '')
                assignee_value = task.get('assignee') if task.get('assignee') in user_names else None
                due_date_value = task.get('due_date') or ''
                updates.extend([
                    gr.update(visible=True),  # Block
                    gr.update(value=name_value, visible=True),  # Titel
                    gr.update(value=description_value, visible=True),  # Beschreibung
                    gr.update(choices=user_names, value=assignee_value, visible=True, interactive=True),  # Zugewiesen
                    gr.update(value=due_date_value, visible=True)  # Fälligkeitsdatum
                ])
            else:
                updates.extend([
                    gr.update(visible=False),  # Block
                    gr.update(value="", visible=False),  # Titel
                    gr.update(value="", visible=False),  # Beschreibung
                    gr.update(choices=[], value=None, visible=False),  # Zugewiesen
                    gr.update(value=None, visible=False)  # Fälligkeitsdatum
                ])
        print(f"DEBUG: Anzahl der Updates: {len(updates)}")
        print(f"DEBUG: Erste Updates: {updates[:4]}")
        while len(updates) < MAX_TASKS * 5:
            updates.extend([
                gr.update(visible=False),  # Block
                gr.update(value="", visible=False),  # Titel
                gr.update(value="", visible=False),  # Beschreibung
                gr.update(choices=[], value=None, visible=False),  # Zugewiesen
                gr.update(value=None, visible=False)  # Fälligkeitsdatum
            ])
        # Rückgabe: Updates für Aufgabenfelder, extrahierte Aufgaben, Assignees, Usernamen, Parent-Task-Namen, Vorschlag
        return (updates + [tasks, [task.get('assignee') for task in tasks], user_names, parent_task_names, best_match, best_match], None)
    except Exception as e:
        print(f"DEBUG: Fehler in analyze_protocol_and_show: {str(e)}")
        return ([gr.update(visible=False) for _ in range(MAX_TASKS * 5)] + [[], [], [], [], None, None], f"❌ Fehler: {str(e)}")

def analyze_protocol_with_loading(protocol_text, workspace_name, project_name, upload_file):
    yield gr.update(value="🔄 Lade...", visible=True), gr.update(interactive=False), *[gr.update() for _ in range(MAX_TASKS * 5 + 7)]  # 5 Felder pro Task (ohne Button)
    result = analyze_protocol_and_show(protocol_text, workspace_name, project_name, upload_file)
    
    # Prüfe, ob result ein Tupel mit Warnung ist oder nur die Ergebnisse
    if isinstance(result, tuple) and len(result) == 2:
        updates_and_data, warn = result
    else:
        updates_and_data = result
        warn = None
    
    parent_task_choices = updates_and_data[-3] if len(updates_and_data) > 2 else []
    best_match = updates_and_data[-2] if len(updates_and_data) > 1 else None
    suggested_parent_task_dropdown_update = gr.update(choices=parent_task_choices, value=best_match, interactive=False)
    parent_task_dropdown_update = gr.update(choices=parent_task_choices, value=best_match, interactive=True)
    status = warn if warn else ""
    yield gr.update(value=status, visible=True), gr.update(interactive=True), *(list(updates_and_data[:-3]) + [parent_task_dropdown_update, suggested_parent_task_dropdown_update])

# Gradio Interface erstellen
with gr.Blocks(title="Meeting-Protokoll zu Asana Aufgaben") as app:
    gr.Markdown("# Meeting Protokoll zu Asana")
    gr.Markdown("Füge dein Meetingprotokoll ein oder lade eine Excel-Datei hoch und erstelle automatisch Asana-Aufgaben.")
    
    loading_info = gr.Markdown("", visible=False)
    
    with gr.Row():
        with gr.Column(scale=1):
            workspaces = get_workspaces()
            workspace_names = list(workspaces.keys())
            default_workspace = workspace_names[0] if workspace_names else None

            initial_projects = []
            if default_workspace:
                workspace_gid = workspaces.get(default_workspace)
                if workspace_gid:
                    initial_projects = list(get_projects(workspace_gid).keys())

            workspace_dropdown = gr.Dropdown(
                choices=workspace_names,
                value=default_workspace,
                label="Workspace"
            )
            
            project_dropdown = gr.Dropdown(
                choices=initial_projects,
                value=None,
                label="Abteilung (Bitte vorher auswählen)"
            )
            
            suggested_parent_task_dropdown = gr.Dropdown(
                choices=[],
                value=None,
                label="Vorgeschlagenes Projekt",
                interactive=False
            )
            parent_task_dropdown = gr.Dropdown(
                choices=[],
                value=None,
                label="Projekt"
            )
        
        with gr.Column(scale=2):
            protocol_input = gr.Textbox(
                label="Meetingprotokoll",
                placeholder="Füge hier dein Protokoll ein...",
                lines=10
            )
            excel_upload = gr.File(
                label="Protokoll-Upload (.xlsx, .xls, .docx)",
                file_types=[".xlsx", ".xls", ".docx"],
                type="filepath"
            )
            analyze_button = gr.Button("Bitte Projekt auswählen", variant="secondary", interactive=False)
            
            # Aufgaben-Container: Für jede Aufgabe ein Block untereinander
            task_containers = []
            for i in range(MAX_TASKS):
                with gr.Column(visible=False) as task_block:
                    if i > 0:
                        gr.HTML("<div style='height: 32px;'></div>")  # Abstand zwischen den Aufgaben
                    
                    # Titel und Beschreibung als editierbare Felder
                    task_title = gr.Textbox(
                        label="Aufgabentitel",
                        placeholder="Titel der Aufgabe...",
                        visible=True,
                        interactive=True
                    )
                    task_description = gr.Textbox(
                        label="Beschreibung",
                        placeholder="Beschreibung der Aufgabe...",
                        lines=3,
                        visible=True,
                        interactive=True
                    )
                    
                    assignee_dropdown = gr.Dropdown(
                        choices=[],
                        label="Zugewiesen",
                        visible=True
                    )
                    due_date_picker = gr.Textbox(
                        label="Fälligkeitsdatum",
                        placeholder="TT.MM.JJJJ",
                        visible=True,
                        value=None,
                        interactive=True
                    )
                    with gr.Row():
                        today_button = gr.Button(
                            "Heute",
                            size="sm",
                            variant="secondary",
                            visible=True
                        )
                        tomorrow_button = gr.Button(
                            "Morgen",
                            size="sm",
                            variant="secondary",
                            visible=True
                        )
                        week_button = gr.Button(
                            "In einer Woche",
                            size="sm",
                            variant="secondary",
                            visible=True
                        )
                        month_button = gr.Button(
                            "In einem Monat",
                            size="sm",
                            variant="secondary",
                            visible=True
                        )
                task_containers.append((task_block, task_title, task_description, assignee_dropdown, due_date_picker, today_button, tomorrow_button, week_button, month_button))

            create_button = gr.Button("Aufgaben in Asana erstellen", variant="primary")
            status_output = gr.Markdown(label="Status")

    # Event-Handler
    def update_analyze_button_state(project_name):
        """Aktiviert den Analyze-Button nur wenn ein Projekt ausgewählt ist"""
        if project_name:
            return gr.update(value="Aufgaben extrahieren", variant="primary", interactive=True)
        else:
            return gr.update(value="Bitte Projekt auswählen", variant="secondary", interactive=False)
    
    workspace_dropdown.change(
        fn=update_project_choices,
        inputs=workspace_dropdown,
        outputs=project_dropdown
    ).then(
        fn=update_analyze_button_state,
        inputs=project_dropdown,
        outputs=analyze_button
    )
    project_dropdown.change(
        fn=update_tasks_on_project_change,
        inputs=[workspace_dropdown, project_dropdown],
        outputs=[parent_task_dropdown, suggested_parent_task_dropdown]
    )
    
    project_dropdown.change(
        fn=update_analyze_button_state,
        inputs=project_dropdown,
        outputs=analyze_button
    )

    # Event-Handler für Datums-Buttons
    def set_today_date():
        """Gibt das heutige Datum im deutschen Format zurück"""
        today = datetime.now().strftime("%d.%m.%Y")
        return gr.update(value=today)
    
    def set_tomorrow_date():
        """Gibt das morgige Datum im deutschen Format zurück"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
        return gr.update(value=tomorrow)
    
    def set_week_date():
        """Gibt das Datum in einer Woche im deutschen Format zurück"""
        week_later = (datetime.now() + timedelta(days=7)).strftime("%d.%m.%Y")
        return gr.update(value=week_later)
    
    def set_month_date():
        """Gibt das Datum in einem Monat im deutschen Format zurück"""
        month_later = (datetime.now() + timedelta(days=30)).strftime("%d.%m.%Y")
        return gr.update(value=month_later)
    
    # Verbinde jeden Datums-Button mit seinem Datums-Feld
    for i, container in enumerate(task_containers):
        task_block, task_title, task_description, assignee_dropdown, due_date_picker, today_button, tomorrow_button, week_button, month_button = container
        today_button.click(
            fn=set_today_date,
            outputs=due_date_picker
        )
        tomorrow_button.click(
            fn=set_tomorrow_date,
            outputs=due_date_picker
        )
        week_button.click(
            fn=set_week_date,
            outputs=due_date_picker
        )
        month_button.click(
            fn=set_month_date,
            outputs=due_date_picker
        )

    # State für Aufgaben und Assignees
    tasks_state = gr.State([])
    assignees_state = gr.State([])
    user_names_state = gr.State([])

    analyze_button.click(
        fn=analyze_protocol_with_loading,
        inputs=[protocol_input, workspace_dropdown, project_dropdown, excel_upload],
        outputs=[loading_info, analyze_button] + [item for container in task_containers for item in container[:5]] + [tasks_state, assignees_state, user_names_state, parent_task_dropdown, suggested_parent_task_dropdown],  # Nur die ersten 5 Felder (ohne Buttons)
        queue=True
    )

    def create_subtasks_wrapper(tasks, titles, descriptions, assignees, workspace_name, project_name, parent_task_name, user_names, due_dates=None):
        # Erweiterte Debug-Ausgaben für alle Felder
        debug_log(f"[create_subtasks_wrapper] Typen: tasks={type(tasks)}, assignees={type(assignees)}, due_dates={type(due_dates)}")
        debug_log(f"[create_subtasks_wrapper] tasks: {json.dumps(tasks, ensure_ascii=False)}")
        debug_log(f"[create_subtasks_wrapper] assignees: {assignees}")
        debug_log(f"[create_subtasks_wrapper] due_dates: {due_dates}")
        debug_log(f"[create_subtasks_wrapper] workspace_name: {workspace_name} ({type(workspace_name)})")
        debug_log(f"[create_subtasks_wrapper] project_name: {project_name} ({type(project_name)})")
        debug_log(f"[create_subtasks_wrapper] parent_task_name: {parent_task_name} ({type(parent_task_name)})")
        debug_log(f"[create_subtasks_wrapper] user_names: {user_names} ({type(user_names)})")
        fehlermeldung = None
        if not tasks:
            fehlermeldung = "❌ Keine Aufgaben gefunden."
        elif not workspace_name:
            fehlermeldung = "❌ Workspace fehlt."
        elif not project_name:
            fehlermeldung = "❌ Projekt fehlt."
        elif not parent_task_name:
            fehlermeldung = "❌ Übergeordnete Aufgabe fehlt."
        if fehlermeldung:
            debug_log(f"Fehlermeldung: {fehlermeldung}")
            # Gebe alle empfangenen Werte im UI aus
            debug_md = f"### Debug-Info\n- workspace_name: {workspace_name}\n- project_name: {project_name}\n- parent_task_name: {parent_task_name}\n- user_names: {user_names}\n- assignees: {assignees}\n- due_dates: {due_dates}\n- tasks: {json.dumps(tasks, ensure_ascii=False)}"
            return fehlermeldung + "\n" + debug_md, ""
        # Baue Aufgaben-JSON NUR aus den UI-Werten
        aufgaben = []
        num_tasks = max(len(titles), len(descriptions), len(assignees), len(due_dates)) if any([titles, descriptions, assignees, due_dates]) else 0
        for idx in range(num_tasks):
            name = titles[idx] if titles and idx < len(titles) else ""
            description = descriptions[idx] if descriptions and idx < len(descriptions) else ""
            assignee = assignees[idx] if assignees and idx < len(assignees) else ""
            due_date = due_dates[idx] if due_dates and idx < len(due_dates) else ""
            
            # Nur Aufgaben mit mindestens einem Namen hinzufügen
            if name.strip():
                aufgaben.append({
                    "name": name,
                    "description": description,
                    "assignee": assignee,
                    "due_date": due_date
                })
        # JSON-Vorschau erzeugen
        json_preview = json.dumps(aufgaben, ensure_ascii=False, indent=2)
        json_md = f"### Aufgaben-JSON-Vorschau\n```json\n{json_preview}\n```"
        # Erstelle Aufgaben in Asana mit den UI-Werten
        status = create_subtasks_in_asana(aufgaben, workspace_name, project_name, parent_task_name)
        return status, json_md

    def create_subtasks_with_loading(tasks, workspace_name, project_name, parent_task_name, user_names, *args):
        # args: [title1, description1, assignee1, due_date1, title2, description2, assignee2, due_date2, ...] (für jede Aufgabe 4 Felder)
        debug_log(f"[create_subtasks_with_loading] args length: {len(args)}")
        debug_log(f"[create_subtasks_with_loading] args: {args}")
        
        # Gruppiere die args in 4er-Gruppen (title, description, assignee, due_date)
        titles = []
        descriptions = []
        assignees = []
        due_dates = []
        
        for i in range(0, len(args), 4):
            if i < len(args):
                titles.append(args[i] if args[i] else "")
            if i+1 < len(args):
                descriptions.append(args[i+1] if args[i+1] else "")
            if i+2 < len(args):
                assignees.append(args[i+2] if args[i+2] else "")
            if i+3 < len(args):
                due_dates.append(args[i+3] if args[i+3] else "")
        
        # Debug-Ausgaben
        debug_log(f"[create_subtasks_with_loading] titles={titles}")
        debug_log(f"[create_subtasks_with_loading] descriptions={descriptions}")
        debug_log(f"[create_subtasks_with_loading] assignees={assignees}")
        debug_log(f"[create_subtasks_with_loading] due_dates={due_dates}")
        debug_log(f"workspace_name={workspace_name}")
        debug_log(f"project_name={project_name}")
        debug_log(f"parent_task_name={parent_task_name}")
        debug_log(f"user_names={user_names}")
        # Ladeanzeige einblenden, Button deaktivieren
        yield gr.update(value="🔄 Aufgaben werden erstellt..."), gr.update(interactive=False), gr.update()
        # Aufgaben erstellen (Titel, Beschreibungen, Assignees und Due Dates werden übernommen)
        result = create_subtasks_wrapper(tasks, titles, descriptions, assignees, workspace_name, project_name, parent_task_name, user_names, due_dates)
        # Ladeanzeige ausblenden, Button wieder aktivieren
        yield gr.update(value=result[0]), gr.update(interactive=True), gr.update(value=result[1])

    create_button.click(
        fn=create_subtasks_with_loading,
        inputs=[tasks_state, workspace_dropdown, project_dropdown, parent_task_dropdown, user_names_state] + [item for container in task_containers for item in container[1:5]],  # Nur title, description, assignee, due_date (ohne Block und Buttons)
        outputs=[status_output, create_button, gr.Markdown(label="JSON-Vorschau")],
        queue=True
    )

def create_subtasks_in_asana(tasks, workspace_name, project_name, parent_task_name):
    """Erstellt die Aufgaben als Subtasks einer bestehenden Aufgabe in Asana"""
    try:
        # Hole Workspace und Projekt IDs
        workspaces = get_workspaces()
        workspace_gid = workspaces.get(workspace_name)
        if not workspace_gid:
            return "❌ Fehler: Workspace nicht gefunden"
        projects = get_projects(workspace_gid)
        project_gid = projects.get(project_name)
        if not project_gid:
            return "❌ Fehler: Projekt nicht gefunden"
        # Hole Aufgaben im Projekt
        tasks_dict = get_tasks(project_gid)
        parent_task_gid = tasks_dict.get(parent_task_name)
        if not parent_task_gid:
            return "❌ Fehler: Übergeordnete Aufgabe nicht gefunden"
        # Hole Benutzer
        users = get_workspace_users(workspace_gid)
        user_names = set(users.keys())
        # Erstelle die Subtasks
        created_tasks = []
        for task in tasks:
            try:
                task_data = {
                    "name": task['name'],
                    "notes": task.get('description', ''),
                    "parent": parent_task_gid,
                    "assignee": users[task['assignee']] if task.get('assignee') and task['assignee'] in user_names else None,
                    "due_on": task.get('due_date') if task.get('due_date') else None
                }
                # Fälligkeitsdatum ggf. umwandeln
                due_date = task.get('due_date')
                if due_date:
                    try:
                        # Versuche deutsches Format zu erkennen
                        date_obj = datetime.strptime(due_date, '%d.%m.%Y')
                        due_on = date_obj.strftime('%Y-%m-%d')
                    except ValueError:
                        # Fallback: nehme das Feld wie es ist
                        due_on = due_date
                    task_data["due_on"] = due_on
                # Entferne None-Werte
                task_data = {k: v for k, v in task_data.items() if v}
                opts = {"opt_fields": "name,gid,completed"}
                result = tasks_api.create_task({"data": task_data}, opts)
                created_tasks.append(f"✅ {task['name']}")
            except Exception as e:
                created_tasks.append(f"❌ {task['name']} - Fehler: {str(e)}")
        return "\n".join(created_tasks)
    except Exception as e:
        return f"❌ Fehler beim Erstellen der Subtasks: {str(e)}"

# Starte die Anwendung
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.launch(
        server_name="0.0.0.0",
        
        # server_name="127.0.0.1",
        server_port=port,
        share=False,
        auth=("innpuls", "innpuls"),  # Benutzername und Passwort
        auth_message="Bitte melden Sie sich an, um auf die App zuzugreifen."
    ) 

