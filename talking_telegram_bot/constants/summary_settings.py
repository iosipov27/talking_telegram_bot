SUMMARY_TRIGGER_ENTRIES = 5
SUMMARY_SYSTEM_PROMPT = (
    "Summarize the previous conversation for future replies. "
    "Keep stable facts, user preferences, open tasks, and important decisions. "
    "Return only the summary."
)
SUMMARY_UPDATE_PROMPT = "Update the conversation summary using the messages above."
SUMMARY_CONTEXT_PREFIX = "Previous conversation summary:\n{summary}"
