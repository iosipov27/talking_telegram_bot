from __future__ import annotations


class MessageInputError(RuntimeError):
    """Raised when user text can not be processed safely."""


class MessageInputService:
    def normalize_text(self, raw_text: str) -> str:
        normalized_text = raw_text.strip()
        if normalized_text:
            return normalized_text
        raise MessageInputError("Message text is empty.")

