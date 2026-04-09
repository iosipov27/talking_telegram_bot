SETTINGS_LOAD_FAILED = "Failed to load application settings."

TEXT_MESSAGE_RECEIVED = (
    "Telegram text message received. chat_id=%s user_id=%s text_length=%s"
)
TEXT_MESSAGE_PROCESSING_FAILED = "Failed to process message: %s"
UNEXPECTED_TELEGRAM_HANDLER_ERROR = "Unexpected error while handling Telegram message."
TEXT_MESSAGE_PROCESSED = (
    "Telegram text message processed. reply_length=%s elapsed_seconds=%.3f"
)

MODELS_COMMAND_RECEIVED = "Telegram /models command received. chat_id=%s user_id=%s"
MODEL_LIST_FAILED = "Failed to list Ollama models: %s"
MODEL_LIST_SENT = "Ollama model list sent. model_count=%s"
MODEL_SELECTION_RECEIVED = "Telegram model selection received. user_id=%s"
MODEL_SELECTION_FAILED = "Failed to select Ollama model: %s"
MODEL_SWITCHED = "Ollama model switched. model=%s"

TELEGRAM_REPLY_SENT = "Telegram reply sent. text_length=%s"
TELEGRAM_REPLY_SEND_FAILED = "Failed to send Telegram reply."
