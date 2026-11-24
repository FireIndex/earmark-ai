from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda

from core.llm import get_llm
from core.vector_store import COLLECTION_NAME, build_vector_store, load_vector_store, get_retriever

RAG_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert meeting assistant. Answer the user's question based ONLY on the meeting transcript context provided below. If the answer is not found in the context, say: I could not find this information in the meeting transcript. Always be concise and precise. If quoting someone, mention it clearly. Context from meeting transcript: {context}"""),
    ("human", "{question}"),
])


def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)


def _chain_from_store(vector_store):
    retriever = get_retriever(vector_store, k=4)
    return {
        "context": retriever | RunnableLambda(format_docs),
        "question": RunnablePassthrough(),
    } | RAG_PROMPT | get_llm() | StrOutputParser()


def build_rag_chain(transcript: str, collection_name: str = COLLECTION_NAME):
    return _chain_from_store(build_vector_store(transcript, collection_name))


def load_rag_chain(collection_name: str = COLLECTION_NAME):
    return _chain_from_store(load_vector_store(collection_name))


def ask_question(rag_chain, question: str) -> str:
    return rag_chain.invoke(question)
