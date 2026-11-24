import os
from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

# Set in .env:
#   LLM_PROVIDER=groq    LLM_MODEL=openai/gpt-oss-20b   (needs GROQ_API_KEY)
#   LLM_PROVIDER=openai  LLM_MODEL=gpt-4o-mini          (needs OPENAI_API_KEY)
DEFAULT_MODELS = {
    "groq": "openai/gpt-oss-20b",
    "openai": "gpt-4o-mini",
}


@lru_cache(maxsize=None)
def get_llm(temperature: float = 0.3) -> BaseChatModel:
    """One shared chat model, chosen from .env. max_retries waits out 429 rate limits."""
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    if provider not in DEFAULT_MODELS:
        raise ValueError(f"LLM_PROVIDER must be one of {list(DEFAULT_MODELS)}, got '{provider}'")
    model = os.getenv("LLM_MODEL", "").strip() or DEFAULT_MODELS[provider]

    print(f"Using LLM: {provider} / {model}")
    if provider == "openai":
        from langchain_openai import ChatOpenAI  # pip install langchain-openai
        return ChatOpenAI(model=model, temperature=temperature, max_retries=6)

    from langchain_groq import ChatGroq
    return ChatGroq(model=model, temperature=temperature, max_retries=6)
