import os
import warnings
import shutil
warnings.filterwarnings("ignore", category=DeprecationWarning)

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from session_handler import handle_file_upload, load_or_create_session_vectorstore
from global_loader import load_global_vectorstore
from chat_logger import append_message, get_history, get_all_sessions
from auth import require_clerk_auth

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.chains import RetrievalQA
from langchain_core.documents import Document
from langchain_core.runnables import RunnableConfig

# Load .env variables
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
print("[DEBUG] OPENAI Key (masked):", os.getenv("OPENAI_API_KEY")[:10], "...")

# Init Flask app
app = Flask(__name__)
CORS(app, origins=["http://localhost:5173", "https://aws.maveriq.in"])

# Init embeddings and model
embedding = OpenAIEmbeddings(openai_api_key=openai_api_key)
llm = ChatOpenAI(model_name="gpt-4", temperature=0.3, openai_api_key=openai_api_key)

# Global vectorstore
persist_directory = "vectorstore"
docs_dir = "DOCS2PARSE"

if not os.path.exists(persist_directory) or not os.listdir(persist_directory):
    print("📂 Global vectorstore missing — rebuilding from DOCS2PARSE...")
    vectordb = load_global_vectorstore(docs_dir, persist_directory)
else:
    print("✅ Global vectorstore loaded from disk.")
    vectordb = Chroma(persist_directory=persist_directory, embedding_function=embedding)

retriever = vectordb.as_retriever()
qa_chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever, return_source_documents=False)

# --------- Routes --------- #

def verify_clerk_token(token):
    try:
        if isinstance(token, bytes):  # FIX: convert to str if needed
            token = token.decode("utf-8")

        header = jwt.get_unverified_header(token)
        key_data = next(k for k in jwks["keys"] if k["kid"] == header["kid"])
        public_key_pem = get_public_key(key_data)

        payload = jwt.decode(
            token,
            public_key_pem,
            algorithms=["RS256"],
            audience=CLERK_CLIENT_ID,
            issuer=CLERK_ISSUER
        )
        return payload
    except Exception as e:
        print(f"[AUTH ERROR] Invalid token: {e}")
        return None





@app.route("/upload", methods=["POST"])
@require_clerk_auth
def upload():
    file = request.files.get("file")
    email = request.email  # set by middleware

    if not file:
        return jsonify({"error": "Missing file"}), 400

    try:
        email, filename = handle_file_upload(file, email)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        print(f"[UPLOAD ERROR] {e}")
        return jsonify({"error": "File processing failed"}), 500

    append_message(email, "user", f"[Uploaded file: {filename}]")
    bot_msg = "Thanks! I've processed your file. Ask me anything."
    append_message(email, "bot", bot_msg)

    return jsonify({"email": email, "bot_response": bot_msg})


@app.route("/chat", methods=["POST"])
@require_clerk_auth
def chat():
    data = request.json
    query = data.get("message")
    email = request.email

    if not query:
        return jsonify({"error": "Missing message"}), 400

    append_message(email, "user", query)

    try:
        user_vectordb = load_or_create_session_vectorstore(email)
        user_retriever = user_vectordb.as_retriever(search_type="similarity", search_kwargs={"k": 4})

        # Attempt user vector answer
        user_chain = RetrievalQA.from_chain_type(llm=llm, retriever=user_retriever, return_source_documents=True)
        user_result = user_chain.invoke(query)
        user_answer = user_result.get("result", "")
        user_sources = user_result.get("source_documents", [])
    except Exception as e:
        print(f"[CHAT ERROR] Failed to use user vectorstore: {e}")
        user_answer = ""
        user_sources = []

    fallback_used = False
    if not user_answer.strip() or len(user_sources) == 0:
        fallback_chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever, return_source_documents=False)
        user_answer = fallback_chain.invoke(query)
        fallback_used = True

    append_message(email, "bot", user_answer)

    return jsonify({
        "response": user_answer,
        "email": email,
        "fallback": fallback_used
    })


@app.route("/history", methods=["GET"])
@require_clerk_auth
def history():
    email = request.email
    try:
        history = get_history(email)
        return jsonify({"email": email, "history": history})
    except Exception as e:
        print(f"[HISTORY ERROR] {e}")
        return jsonify({"error": "Failed to fetch history"}), 500


@app.route("/sessions", methods=["GET"])
@require_clerk_auth
def sessions():
    try:
        return jsonify({"sessions": get_all_sessions()})
    except Exception as e:
        print(f"[SESSION ERROR] {e}")
        return jsonify({"error": "Failed to fetch sessions"}), 500


@app.route("/files", methods=["GET"])
@require_clerk_auth
def list_user_files():
    email = request.email
    upload_dir = os.path.join("session_uploads", email)
    try:
        files = []
        if os.path.exists(upload_dir):
            files = [
                f for f in os.listdir(upload_dir)
                if f.lower().endswith(('.pdf', '.docx', '.csv', '.png', '.jpg'))
            ]
        return jsonify({"email": email, "files": files})
    except Exception as e:
        print(f"[FILES ERROR] {e}")
        return jsonify({"error": "Failed to list files"}), 500


@app.route("/clear", methods=["POST"])
@require_clerk_auth
def clear_memory():
    email = request.email
    try:
        history_path = os.path.join("session_uploads", email, "chat_history.json")
        vector_path = os.path.join("vectorstore", email)
        session_dir = os.path.join("session_uploads", email)

        if os.path.exists(history_path):
            os.remove(history_path)
        if os.path.exists(vector_path):
            shutil.rmtree(vector_path)
        if os.path.exists(session_dir):
            shutil.rmtree(session_dir)

        return jsonify({"message": "User data wiped"}), 200
    except Exception as e:
        print(f"[CLEAR ERROR] {e}")
        return jsonify({"error": "Failed to clear user data"}), 500


# --------- Start App --------- #
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
