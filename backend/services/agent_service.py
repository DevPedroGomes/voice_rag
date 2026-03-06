import os

from agents import Agent, Runner, set_tracing_disabled


DEFAULT_TTS_INSTRUCTIONS = (
    "Speak in a clear, professional, and friendly tone. "
    "Use natural pacing with appropriate pauses for comprehension. "
    "Pronounce technical terms carefully and distinctly. "
    "Maintain a conversational style that is engaging but informative."
)


class AgentService:
    """Service for running the RAG processor agent."""

    def __init__(self, openai_api_key: str, processor_model: str = "gpt-4.1-mini"):
        os.environ["OPENAI_API_KEY"] = openai_api_key
        self._openai_api_key = openai_api_key

        # Disable tracing to prevent API key leakage in error logs
        set_tracing_disabled(True)

        self._processor_agent = Agent(
            name="Documentation Processor",
            instructions="""You are a helpful documentation assistant. Your task is to:
1. Analyze the provided documentation content
2. Answer the user's question clearly and concisely
3. Include relevant examples when available
4. Cite the source files when referencing specific content
5. Keep responses natural and conversational
6. Format your response in a way that's easy to speak out loud
7. Use short sentences and clear language for better TTS output""",
            model=processor_model,
        )

    async def process_query(
        self,
        query: str,
        context: list[dict],
    ) -> tuple[str, str, list[str]]:
        """
        Process a query with context from retrieved documents.

        Args:
            query: User's question
            context: List of dicts with 'content', 'file_name', 'page_number'

        Returns:
            Tuple of (text_response, voice_instructions, sources)
        """
        # Build context string
        context_str = "Based on the following documentation:\n\n"
        sources = []

        for i, doc in enumerate(context, 1):
            content = doc.get("content", "")
            source = doc.get("file_name", "Unknown Source")
            context_str += f"From {source}:\n{content}\n\n"
            if source not in sources:
                sources.append(source)

        context_str += f"\nUser Question: {query}\n\n"
        context_str += "Please provide a clear, concise answer that can be easily spoken out loud."

        # Generate text response (single LLM call)
        processor_result = await Runner.run(self._processor_agent, context_str)
        text_response = processor_result.final_output

        return text_response, DEFAULT_TTS_INSTRUCTIONS, sources


# Singleton instance
_agent_service: AgentService | None = None


def get_agent_service() -> AgentService:
    """Get the singleton agent service instance."""
    global _agent_service
    if _agent_service is None:
        from config import get_settings
        settings = get_settings()
        _agent_service = AgentService(
            openai_api_key=settings.openai_api_key,
            processor_model=settings.processor_model,
        )
    return _agent_service
