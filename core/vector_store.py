from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_core.runnables import Runnable

CHROMA_DIR = "vector_db"
COLLECTION_NAME = "metting_transcript"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

_embeddings = None


def get_embedding():
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
        )
    return _embeddings


def build_vector_store(transcript: str, collection_name: str = COLLECTION_NAME) -> Chroma:
    """One collection per meeting, so chats never mix meetings or pile up duplicates."""
    vector_store = Chroma(
        collection_name=collection_name,
        embedding_function=get_embedding(),
        persist_directory=CHROMA_DIR,
    )
    if vector_store.get(limit=1)["ids"]:
        print("Reusing existing vector store")
        return vector_store

    print("Building vector store")
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    docs = [
        Document(page_content=chunk, metadata={"chunk_index": i})
        for i, chunk in enumerate(splitter.split_text(transcript))
    ]
    vector_store.add_documents(docs)
    return vector_store


def load_vector_store(collection_name: str = COLLECTION_NAME) -> Chroma:
    return Chroma(
        collection_name=collection_name,
        embedding_function=get_embedding(),
        persist_directory=CHROMA_DIR,
    )


def get_retriever(vector_store: Chroma, k: int = 4) -> Runnable:
    return vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k},
    )
