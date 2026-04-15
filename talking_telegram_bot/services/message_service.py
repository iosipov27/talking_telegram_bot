import logging
from datetime import UTC, datetime

from talking_telegram_bot.clients.chat_history_client import (
    ChatHistoryClient,
    ChatHistoryClientError,
)
from talking_telegram_bot.clients.ollama_client import OllamaClient, OllamaClientError
from talking_telegram_bot.constants import log_events
from talking_telegram_bot.constants.prompt_settings import (
    AGENT_SYSTEM_PROMPT,
    DEFAULT_AGENT_ROLE,
)
from talking_telegram_bot.constants.summary_settings import (
    SUMMARY_CONTEXT_PREFIX,
    SUMMARY_SYSTEM_PROMPT,
    SUMMARY_TRIGGER_ENTRIES,
    SUMMARY_UPDATE_PROMPT,
)
from talking_telegram_bot.logging_utils import MarkdownTable, format_markdown_event
from talking_telegram_bot.models.messages import (
    ChatHistoryEntry,
    ChatHistoryLog,
    ChatSummary,
    ConversationMessage,
    UserMessage,
)

logger = logging.getLogger(__name__)


class MessageProcessingError(RuntimeError):
    """Raised when a user message can not be processed safely."""


class AgentRoleSelectionError(RuntimeError):
    """Raised when the runtime agent role is invalid."""


class MessageService:
    def __init__(
        self,
        ollama_client: OllamaClient,
        chat_history_client: ChatHistoryClient,
        agent_role: str = DEFAULT_AGENT_ROLE,
    ) -> None:
        self._ollama_client = ollama_client
        self._chat_history_client = chat_history_client
        self._agent_role = self._normalize_agent_role(agent_role)

    async def generate_reply(self, raw_text: str, user_id: int) -> str:
        user_message = self._normalize_message(raw_text)
        history_log = await self._load_history(user_id)
        history_log = await self._summarize_history_if_needed(user_id, history_log)
        llm_messages = self._build_llm_messages(history_log, user_message)
        try:
            assistant_message = await self._ollama_client.generate_reply(llm_messages)
        except OllamaClientError as exc:
            raise MessageProcessingError("LLM is unavailable.") from exc
        reply_text = assistant_message.text.strip()
        if not reply_text:
            raise MessageProcessingError("LLM returned an empty response.")
        await self._save_history(user_id, user_message.text, reply_text)
        return reply_text

    def get_current_agent_role(self) -> str:
        return self._agent_role

    def set_agent_role(self, raw_role: str) -> str:
        self._agent_role = self._normalize_agent_role(raw_role)
        return self._agent_role

    def _normalize_message(self, raw_text: str) -> UserMessage:
        normalized_text = raw_text.strip()
        if normalized_text:
            return UserMessage(text=normalized_text)
        raise MessageProcessingError("Message text is empty.")

    def _normalize_agent_role(self, raw_role: str) -> str:
        normalized_role = raw_role.strip()
        if normalized_role:
            return normalized_role
        raise AgentRoleSelectionError("Agent role is empty.")

    async def _load_history(self, user_id: int) -> ChatHistoryLog:
        try:
            return await self._chat_history_client.read_history(user_id)
        except ChatHistoryClientError as exc:
            raise MessageProcessingError("Chat history is unavailable.") from exc

    async def _summarize_history_if_needed(
        self,
        user_id: int,
        history_log: ChatHistoryLog,
    ) -> ChatHistoryLog:
        if len(history_log.entries) < SUMMARY_TRIGGER_ENTRIES:
            return history_log
        summary_text = await self._generate_summary(history_log)
        summary = ChatSummary(
            text=summary_text,
            updated_at=datetime.now(UTC).isoformat(),
        )
        await self._save_summary(user_id, summary, len(history_log.entries))
        return ChatHistoryLog(summary=summary, entries=[])

    async def _generate_summary(self, history_log: ChatHistoryLog) -> str:
        summary_messages = self._build_summary_messages(history_log)
        logger.info(
            format_markdown_event(
                log_events.SUMMARY_REQUEST_SENT_TO_LLM,
                [
                    ("Entry Count", len(history_log.entries)),
                    ("Has Existing Summary", history_log.summary is not None),
                    ("Message Count", len(summary_messages)),
                ],
            ),
        )
        try:
            summary_message = await self._ollama_client.generate_reply(
                summary_messages,
            )
        except OllamaClientError as exc:
            raise MessageProcessingError("LLM is unavailable.") from exc
        summary_text = summary_message.text.strip()
        logger.info(
            format_markdown_event(
                log_events.SUMMARY_RESPONSE_RECEIVED_FROM_LLM,
                [("Summary Length", len(summary_text))],
                detail_tables=[
                    MarkdownTable(
                        headers=("Type", "Content"),
                        rows=(("summary", summary_text),),
                    ),
                ],
            ),
        )
        if summary_text:
            return summary_text
        raise MessageProcessingError("LLM returned an empty summary.")

    def _build_llm_messages(
        self,
        history_log: ChatHistoryLog,
        user_message: UserMessage,
    ) -> list[ConversationMessage]:
        messages = [self._build_system_prompt()]
        if history_log.summary is not None:
            messages.append(self._build_summary_context(history_log.summary))
        messages.extend(self._build_entry_messages(history_log.entries))
        messages.append(ConversationMessage(role="user", content=user_message.text))
        return messages

    def _build_summary_messages(
        self,
        history_log: ChatHistoryLog,
    ) -> list[ConversationMessage]:
        messages = [
            ConversationMessage(role="system", content=SUMMARY_SYSTEM_PROMPT),
        ]
        if history_log.summary is not None:
            messages.append(self._build_summary_context(history_log.summary))
        messages.extend(self._build_entry_messages(history_log.entries))
        messages.append(ConversationMessage(role="user", content=SUMMARY_UPDATE_PROMPT))
        return messages

    def _build_entry_messages(
        self,
        history_entries: list[ChatHistoryEntry],
    ) -> list[ConversationMessage]:
        messages = []
        for entry in history_entries:
            messages.append(ConversationMessage(role="user", content=entry.request))
            messages.append(
                ConversationMessage(role="assistant", content=entry.response),
            )
        return messages

    def _build_summary_context(self, summary: ChatSummary) -> ConversationMessage:
        return ConversationMessage(
            role="system",
            content=SUMMARY_CONTEXT_PREFIX.format(summary=summary.text),
        )

    def _build_system_prompt(self) -> ConversationMessage:
        return ConversationMessage(
            role="system",
            content=AGENT_SYSTEM_PROMPT.format(agent_role=self._agent_role),
        )

    async def _save_summary(
        self,
        user_id: int,
        summary: ChatSummary,
        summarized_entry_count: int,
    ) -> None:
        try:
            await self._chat_history_client.save_summary(
                user_id,
                summary,
                summarized_entry_count,
            )
        except ChatHistoryClientError as exc:
            raise MessageProcessingError("Chat history is unavailable.") from exc

    async def _save_history(
        self,
        user_id: int,
        request_text: str,
        response_text: str,
    ) -> None:
        entry = ChatHistoryEntry(
            request=request_text,
            response=response_text,
            created_at=datetime.now(UTC).isoformat(),
        )
        try:
            await self._chat_history_client.append_entry(user_id, entry)
        except ChatHistoryClientError as exc:
            raise MessageProcessingError("Chat history is unavailable.") from exc
