import os
import json
import shutil

BASE_DIR = "session_uploads"
VECTOR_DIR = "vectorstore"

def get_history_file(email):
    return os.path.join(BASE_DIR, email, "chat_history.json")

def append_message(email, sender, message):
    path = get_history_file(email)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    entry = {"sender": sender, "message": message}

    history = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            history = json.load(f)

    history.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def get_history(email):
    path = get_history_file(email)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def get_all_sessions():
    return os.listdir(BASE_DIR) if os.path.exists(BASE_DIR) else []

def clear_all_user_data(email):
    # Remove chat history + uploaded files
    session_path = os.path.join(BASE_DIR, email)
    if os.path.exists(session_path):
        shutil.rmtree(session_path)

    # Remove user vectorstore
    vector_path = os.path.join(VECTOR_DIR, email)
    if os.path.exists(vector_path):
        shutil.rmtree(vector_path)
