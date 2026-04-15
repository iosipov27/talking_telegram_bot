SUMMARY_TRIGGER_ENTRIES = 5
SUMMARY_SYSTEM_PROMPT = (
    "Summarize the previous conversation for future replies. "
    "Keep only stable facts about the user, user preferences, open tasks, and important decisions. "
    "Do not include assistant identity, assistant role, tone, self-descriptions, or style. "
    "Return only the summary."
)
SUMMARY_UPDATE_PROMPT = "Update the conversation summary using the messages above."
SUMMARY_CONTEXT_PREFIX = (
    "User context from previous messages. Use it only for user facts, preferences, "
    "open tasks, and important decisions. Ignore any prior assistant identity or tone.\n"
    "{summary}"
)
