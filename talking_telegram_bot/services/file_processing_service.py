from __future__ import annotations

from pathlib import Path

_SUPPORTED_FILE_EXTENSIONS = frozenset({".txt", ".md", ".json", ".csv"})
_DEFAULT_MAX_FILE_SIZE_BYTES = 1_000_000


class FileProcessingError(RuntimeError):
    """Raised when a Telegram file can not be processed safely."""


class UnsupportedFileTypeError(FileProcessingError):
    """Raised when the uploaded file type is not allowed."""


class FileTooLargeError(FileProcessingError):
    """Raised when the uploaded file exceeds the configured size limit."""


class FileProcessingService:
    def __init__(self, max_file_size_bytes: int = _DEFAULT_MAX_FILE_SIZE_BYTES) -> None:
        self._max_file_size_bytes = max_file_size_bytes

    @property
    def max_file_size_megabytes(self) -> int:
        return max(1, self._max_file_size_bytes // 1_000_000)

    def validate_metadata(self, file_name: str | None, file_size: int | None) -> None:
        if self._extract_extension(file_name) not in _SUPPORTED_FILE_EXTENSIONS:
            raise UnsupportedFileTypeError("File type is not supported.")
        if file_size is not None and file_size > self._max_file_size_bytes:
            raise FileTooLargeError("File is too large.")

    def build_llm_prompt(self, file_name: str | None, content: bytes) -> str:
        self.validate_metadata(file_name, len(content))
        file_text = self._decode_content(content)
        return (
            "The user uploaded a file. Read the file content and respond based only on it.\n"
            f"File name: {file_name}\n"
            "File content:\n"
            f"{file_text}"
        )

    def _extract_extension(self, file_name: str | None) -> str:
        if not file_name:
            return ""
        return Path(file_name).suffix.lower()

    def _decode_content(self, content: bytes) -> str:
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise FileProcessingError("File content is not valid UTF-8.") from exc
