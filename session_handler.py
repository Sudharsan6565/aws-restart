import os
import shutil
import json
from datetime import datetime
from file_utils import parse_file
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from global_loader import load_global_vectorstore

BASE_SESSIONS_DIR = "session_uploads"
CHROMA_BASE_DIR = "chroma_sessions"
embedding = OpenAIEmbeddings()
MAX_VECTOR_BYTES = 100 * 1024 * 1024  # 100MB

def get_vectorstore_size(email: str) -> int:
    """Returns total vectorstore size in bytes for a user."""
    vector_dir = os.path.join(CHROMA_BASE_DIR, email)
    total = 0
    for root, dirs, files in os.walk(vector_dir):
        for f in files:
            fp = os.path.join(root, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total

def handle_file_upload(file, email: str) -> tuple:
    # Create upload dir
    session_dir = os.path.join(BASE_SESSIONS_DIR, email)
    os.makedirs(session_dir, exist_ok=True)

    file_path = os.path.join(session_dir, file.filename)
    file.save(file_path)

    # Vectorstore path
    vectorstore_path = os.path.join(CHROMA_BASE_DIR, email)

    # Check user vector quota
    if get_vectorstore_size(email) >= MAX_VECTOR_BYTES:
        raise ValueError("Your vector storage (100MB) is full. Please clear memory before uploading more files.")

    # Clean and rebuild vectorstore
    if os.path.exists(vectorstore_path):
        shutil.rmtree(vectorstore_path)

    try:
        documents = parse_file(file_path)
        chunks = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=200).split_documents(documents)
        Chroma.from_documents(chunks, embedding, persist_directory=vectorstore_path)
    except Exception as e:
        print(f"[ERROR] Vectorstore build failed for {email}: {e}")

    # Update session meta
    try:
        meta_path = os.path.join(session_dir, "meta.json")
        meta = {
            "files": [],
            "last_used": None,
            "title": "Untitled Chat"
        }

        if os.path.exists(meta_path):
            with open(meta_path, "r") as f:
                meta = json.load(f)

        if file.filename not in meta["files"]:
            meta["files"].append(file.filename)

        meta["last_used"] = datetime.utcnow().isoformat()

        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
    except Exception as e:
        print(f"[WARN] Failed to update meta.json for {email}: {e}")

    return email, file.filename

def load_or_create_session_vectorstore(email: str):
    persist_dir = os.path.join(CHROMA_BASE_DIR, email)
    user_dir = os.path.join(BASE_SESSIONS_DIR, email)

    if os.path.exists(user_dir) and os.listdir(user_dir):
        if os.path.exists(persist_dir) and os.listdir(persist_dir):
            try:
                return Chroma(persist_directory=persist_dir, embedding_function=embedding)
            except Exception as e:
                print(f"[ERROR] Load failed for {email} — using global: {e}")

    print(f"[WARN] No user vectorstore for {email} — using global.")
    return load_global_vectorstore()
