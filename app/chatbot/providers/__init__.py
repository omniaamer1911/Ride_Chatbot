from app.chatbot.providers.anthropic_provider import AnthropicProvider
from app.chatbot.providers.base import AssistantTurn, LLMProvider, ToolCall
from app.chatbot.providers.gemini_provider import GeminiProvider
from app.chatbot.providers.groq_provider import GroqProvider
from app.chatbot.providers.mock_provider import MockLLMProvider
from app.chatbot.providers.openai_provider import OpenAIProvider


def get_llm_provider() -> LLMProvider:
    from app.config import get_settings

    s = get_settings()
    if s.llm_provider == "mock":
        return MockLLMProvider()
    if s.llm_provider == "gemini":
        if not s.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
        return GeminiProvider(s.gemini_api_key, s.gemini_model)
    if s.llm_provider == "groq":
        if not s.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        return GroqProvider(s.groq_api_key, s.groq_model)
    if s.llm_provider == "anthropic":
        if not s.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        return AnthropicProvider(s.anthropic_api_key, s.anthropic_model)
    if s.llm_provider == "openai":
        if not s.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        return OpenAIProvider(s.openai_api_key, s.openai_model)
    raise RuntimeError(f"Unknown LLM_PROVIDER={s.llm_provider!r}")
