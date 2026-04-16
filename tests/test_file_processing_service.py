from __future__ import annotations

import unittest

from talking_telegram_bot.services.file_processing_service import (
    FileProcessingError,
    FileProcessingService,
    FileTooLargeError,
    UnsupportedFileTypeError,
)


class FileProcessingServiceTestCase(unittest.TestCase):
    def test_validate_metadata_accepts_supported_extensions(self) -> None:
        service = FileProcessingService(max_file_size_bytes=100)

        for file_name in ("notes.txt", "readme.md", "data.json", "rows.csv"):
            with self.subTest(file_name=file_name):
                service.validate_metadata(file_name, 100)

    def test_validate_metadata_rejects_unsupported_extension(self) -> None:
        service = FileProcessingService()

        with self.assertRaises(UnsupportedFileTypeError):
            service.validate_metadata("image.png", 10)

    def test_validate_metadata_rejects_large_file(self) -> None:
        service = FileProcessingService(max_file_size_bytes=10)

        with self.assertRaises(FileTooLargeError):
            service.validate_metadata("notes.txt", 11)

    def test_build_llm_prompt_includes_file_name_and_content(self) -> None:
        service = FileProcessingService(max_file_size_bytes=100)

        prompt = service.build_llm_prompt("notes.txt", b"\xef\xbb\xbfhello")

        self.assertIn("File name: notes.txt", prompt)
        self.assertIn("File content:\nhello", prompt)

    def test_build_llm_prompt_rejects_non_utf8_content(self) -> None:
        service = FileProcessingService(max_file_size_bytes=100)

        with self.assertRaises(FileProcessingError):
            service.build_llm_prompt("notes.txt", b"\xff")
