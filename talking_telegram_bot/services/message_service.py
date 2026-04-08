from talking_telegram_bot.clients.ollama_client import OllamaClient, OllamaClientError
from talking_telegram_bot.models.messages import UserMessage


class MessageProcessingError(RuntimeError):
    """Raised when a user message can not be processed safely."""


class MessageService:
    def __init__(self, ollama_client: OllamaClient) -> None:
        self._ollama_client = ollama_client

    async def generate_reply(self, raw_text: str) -> str:
        user_message = self._normalize_message(raw_text)
        try:
            assistant_message = await self._ollama_client.generate_reply(user_message)
        except OllamaClientError as exc:
            raise MessageProcessingError("LLM is unavailable.") from exc
        reply_text = assistant_message.text.strip()
        if reply_text:
            return reply_text
        raise MessageProcessingError("LLM returned an empty response.")

    def _normalize_message(self, raw_text: str) -> UserMessage:
        normalized_text = raw_text.strip()
        if normalized_text:
            return UserMessage(text=normalized_text)
        raise MessageProcessingError("Message text is empty.")
