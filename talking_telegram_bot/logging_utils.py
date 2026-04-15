from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Sequence

DEFAULT_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
RESET_COLOR = "\033[0m"
LEVEL_COLORS = {
    "DEBUG": "\033[37m",
    "INFO": "\033[36m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[35m",
}


@dataclass(frozen=True)
class MarkdownTable:
    headers: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]


class MarkdownLogFormatter(logging.Formatter):
    def __init__(
        self,
        use_colors: bool = False,
        datefmt: str = DEFAULT_LOG_DATE_FORMAT,
    ) -> None:
        super().__init__(datefmt=datefmt)
        self._use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            message = (
                f"{message}\n\n```text\n"
                f"{self.formatException(record.exc_info)}\n```"
            )
        header = f"[{record.levelname}] {self.formatTime(record, self.datefmt)} {record.name}"
        if self._use_colors:
            header = self._colorize(header, record.levelname)
        return f"{header}\n{message}"

    def _colorize(self, header: str, level_name: str) -> str:
        color = LEVEL_COLORS.get(level_name)
        if color is None:
            return header
        return f"{color}{header}{RESET_COLOR}"


def format_markdown_event(
    title: str,
    rows: Sequence[tuple[str, object]],
    detail_tables: Sequence[MarkdownTable] | None = None,
    detail_blocks: Sequence[str] | None = None,
) -> str:
    sections = [f"### {title}", build_markdown_table(("Field", "Value"), rows)]
    if detail_tables is None and detail_blocks is None:
        return "\n\n".join(sections)
    if detail_tables is not None:
        sections.extend(
            build_markdown_table(table.headers, table.rows)
            for table in detail_tables
        )
    if detail_blocks is not None:
        sections.extend(detail_blocks)
    return "\n\n".join(sections)


def build_markdown_table(
    headers: Sequence[str],
    rows: Iterable[Sequence[object]],
) -> str:
    normalized_headers = tuple(_escape_markdown_cell(header) for header in headers)
    body_rows = list(rows)
    lines = [
        _build_table_row(normalized_headers),
        _build_table_row(tuple("---" for _ in normalized_headers)),
    ]
    for row in body_rows:
        lines.append(_build_table_row(tuple(_escape_markdown_cell(cell) for cell in row)))
    if not body_rows:
        lines.append(_build_table_row(tuple("" for _ in normalized_headers)))
    return "\n".join(lines)


def _build_table_row(cells: Sequence[str]) -> str:
    return f"| {' | '.join(cells)} |"


def _escape_markdown_cell(value: object) -> str:
    text = str(value)
    text = text.replace("\\", "\\\\")
    text = text.replace("|", "\\|")
    text = text.replace("\r", "")
    return text.replace("\n", "<br>")


def build_markdown_code_block(
    title: str,
    content: str,
    language: str = "",
) -> str:
    language_suffix = language
    return f"#### {title}\n```{language_suffix}\n{content}\n```"
