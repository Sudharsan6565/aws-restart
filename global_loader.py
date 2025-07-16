import os
from dotenv import load_dotenv
from file_utils import parse_file
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document  # just in case you need to patch

load_dotenv()
embedding = OpenAIEmbeddings(openai_api_key=os.getenv("OPENAI_API_KEY"))

def load_global_vectorstore(docs_dir="DOCS2PARSE", persist_directory="vectorstore"):
    if not os.path.exists(persist_directory) or not os.listdir(persist_directory):
        print("📂 Vectorstore missing — rebuilding from DOCS2PARSE...")
        all_files = [os.path.join(docs_dir, f) for f in os.listdir(docs_dir)]
        documents = []

        for file in all_files:
            print(f"🔍 Loading file: {file}")
            try:
                parsed_docs = parse_file(file)  # now returns List[Document]
                if parsed_docs:
                    documents.extend(parsed_docs)
                    print(f"✅ Parsed {file} into {len(parsed_docs)} document(s)")
                else:
                    print(f"⚠️ Skipped {file} (no content returned)")
            except Exception as e:
                print(f"[❌] Error parsing {file}: {e}")

        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=200)
        chunks = splitter.split_documents(documents)
        print(f"📄 Total parsed docs: {len(documents)}\n✂️ Split into {len(chunks)} chunks.")

        vectordb = Chroma.from_documents(chunks, embedding, persist_directory=persist_directory)
    else:
        vectordb = Chroma(persist_directory=persist_directory, embedding_function=embedding)

    return vectordb
