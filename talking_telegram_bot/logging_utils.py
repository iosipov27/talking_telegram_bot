from __future__ import annotations

import logging
import re
import shutil
import textwrap
from dataclasses import dataclass
from typing import Iterable, Sequence

DEFAULT_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
RESET_COLOR = "\033[0m"
ANSI_PATTERN = re.compile(r"\033\[[0-9;]*m")
LEVEL_COLORS = {
    "DEBUG": "\033[37m",
    "INFO": "\033[36m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[35m",
}
PANEL_BORDER_COLOR = "\033[38;5;240m"
PANEL_TITLE_COLOR = "\033[1;38;5;255;48;5;31m"
TABLE_HEADER_COLOR = "\033[1;38;5;255;48;5;24m"
TABLE_KEY_COLOR = "\033[1;38;5;153m"
TABLE_VALUE_COLOR = "\033[38;5;255m"
TEXT_COLOR = "\033[38;5;252m"
CODE_COLOR = "\033[38;5;151m"
SECTION_TITLE_COLOR = "\033[1;38;5;117m"


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
            message = self._render_console_message(message)
        return f"{header}\n{message}"

    def _colorize(self, header: str, level_name: str) -> str:
        color = LEVEL_COLORS.get(level_name)
        if color is None:
            return header
        return f"{color}{header}{RESET_COLOR}"

    def _render_console_message(self, message: str) -> str:
        if "### " not in message and "|" not in message and "```" not in message:
            return message
        lines = message.splitlines()
        blocks: list[str] = []
        line_index = 0
        while line_index < len(lines):
            line = lines[line_index]
            if not line.strip():
                line_index += 1
                continue
            if line.startswith("### "):
                blocks.append(self._render_title(line[4:].strip()))
                line_index += 1
                continue
            if line.startswith("#### "):
                title = line[5:].strip()
                if line_index + 1 < len(lines) and lines[line_index + 1].startswith("```"):
                    code_block, next_index = self._consume_code_block(lines, line_index + 1)
                    blocks.append(self._render_code_block(title, code_block))
                    line_index = next_index
                    continue
                blocks.append(self._paint(title, SECTION_TITLE_COLOR))
                line_index += 1
                continue
            if line.startswith("|"):
                table_lines, next_index = self._consume_table(lines, line_index)
                blocks.append(self._render_table(table_lines))
                line_index = next_index
                continue
            if line.startswith("```"):
                code_block, next_index = self._consume_code_block(lines, line_index)
                blocks.append(self._render_code_block("Details", code_block))
                line_index = next_index
                continue
            blocks.append(self._render_paragraph(line))
            line_index += 1
        return "\n\n".join(blocks)

    def _render_title(self, title: str) -> str:
        content_width = self._content_width()
        fill_width = max(content_width - len(title) - 2, 0)
        border = self._paint("━" * fill_width, PANEL_BORDER_COLOR)
        label = self._paint(f" {title} ", PANEL_TITLE_COLOR)
        return f"{label}{border}"

    def _render_table(self, lines: Sequence[str]) -> str:
        rows = [self._parse_markdown_row(line) for line in lines]
        if len(rows) < 2:
            return "\n".join(lines)
        headers = rows[0]
        body_rows = rows[2:] if len(rows) > 2 else [tuple("" for _ in headers)]
        column_widths = self._compute_column_widths(headers, body_rows)
        top_border = self._build_border("╭", "┬", "╮", column_widths)
        middle_border = self._build_border("├", "┼", "┤", column_widths)
        bottom_border = self._build_border("╰", "┴", "╯", column_widths)
        rendered_lines = [top_border]
        rendered_lines.extend(self._render_table_row(headers, column_widths, is_header=True))
        rendered_lines.append(middle_border)
        for row in body_rows:
            rendered_lines.extend(self._render_table_row(row, column_widths))
        rendered_lines.append(bottom_border)
        return "\n".join(rendered_lines)

    def _render_table_row(
        self,
        row: Sequence[str],
        column_widths: Sequence[int],
        is_header: bool = False,
    ) -> list[str]:
        wrapped_cells = [
            self._wrap_cell(cell, width)
            for cell, width in zip(row, column_widths, strict=False)
        ]
        row_height = max(len(cell_lines) for cell_lines in wrapped_cells)
        rendered_lines = []
        for line_number in range(row_height):
            rendered_cells = []
            for column_index, (cell_lines, width) in enumerate(
                zip(wrapped_cells, column_widths, strict=False),
            ):
                cell_text = cell_lines[line_number] if line_number < len(cell_lines) else ""
                padded_text = cell_text.ljust(width)
                if is_header:
                    rendered_cells.append(self._paint(padded_text, TABLE_HEADER_COLOR))
                elif column_index == 0:
                    rendered_cells.append(self._paint(padded_text, TABLE_KEY_COLOR))
                else:
                    rendered_cells.append(self._paint(padded_text, TABLE_VALUE_COLOR))
            separator = self._paint(" │ ", PANEL_BORDER_COLOR)
            rendered_lines.append(
                self._paint("│ ", PANEL_BORDER_COLOR)
                + separator.join(rendered_cells)
                + self._paint(" │", PANEL_BORDER_COLOR)
            )
        return rendered_lines

    def _render_code_block(self, title: str, content: str) -> str:
        content_width = self._content_width()
        wrapped_lines = []
        for raw_line in content.splitlines() or [""]:
            wrapped_lines.extend(
                textwrap.wrap(raw_line, width=content_width - 4) or [""]
            )
        top_border = self._paint(
            f"╭─ {title} " + "─" * max(content_width - len(title) - 4, 0) + "╮",
            PANEL_BORDER_COLOR,
        )
        bottom_border = self._paint("╰" + "─" * content_width + "╯", PANEL_BORDER_COLOR)
        body = [
            self._paint("│ ", PANEL_BORDER_COLOR)
            + self._paint(line.ljust(content_width - 2), CODE_COLOR)
            + self._paint(" │", PANEL_BORDER_COLOR)
            for line in wrapped_lines
        ]
        return "\n".join([top_border, *body, bottom_border])

    def _render_paragraph(self, paragraph: str) -> str:
        wrapped_lines = textwrap.wrap(paragraph, width=self._content_width()) or [""]
        return "\n".join(self._paint(line, TEXT_COLOR) for line in wrapped_lines)

    def _consume_table(self, lines: Sequence[str], start_index: int) -> tuple[list[str], int]:
        table_lines = []
        line_index = start_index
        while line_index < len(lines) and lines[line_index].startswith("|"):
            table_lines.append(lines[line_index])
            line_index += 1
        return table_lines, line_index

    def _consume_code_block(
        self,
        lines: Sequence[str],
        start_index: int,
    ) -> tuple[str, int]:
        line_index = start_index + 1
        content_lines = []
        while line_index < len(lines) and not lines[line_index].startswith("```"):
            content_lines.append(lines[line_index])
            line_index += 1
        if line_index < len(lines):
            line_index += 1
        return "\n".join(content_lines), line_index

    def _parse_markdown_row(self, line: str) -> tuple[str, ...]:
        stripped = line.strip()
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]
        cells = []
        current = []
        is_escaped = False
        for character in stripped:
            if is_escaped:
                current.append(character)
                is_escaped = False
                continue
            if character == "\\":
                is_escaped = True
                continue
            if character == "|":
                cells.append(self._normalize_console_cell("".join(current)))
                current = []
                continue
            current.append(character)
        cells.append(self._normalize_console_cell("".join(current)))
        return tuple(cell.strip() for cell in cells)

    def _normalize_console_cell(self, value: str) -> str:
        return value.replace("<br>", "\n")

    def _compute_column_widths(
        self,
        headers: Sequence[str],
        body_rows: Sequence[Sequence[str]],
    ) -> list[int]:
        max_content_width = self._content_width()
        column_count = len(headers)
        if column_count == 0:
            return []
        available_cell_width = max(max_content_width - (3 * column_count - 1), 16)
        if column_count == 2:
            first_target_width = max(
                self._visible_width(headers[0]),
                *(self._visible_width(row[0]) for row in body_rows),
            )
            first_width = min(max(first_target_width, 8), min(24, available_cell_width - 16))
            second_width = max(available_cell_width - first_width, 16)
            return [first_width, second_width]
        widths = [
            max(
                self._visible_width(header),
                *(self._visible_width(row[index]) for row in body_rows),
            )
            for index, header in enumerate(headers)
        ]
        if sum(widths) <= available_cell_width:
            return widths
        trimmed_widths = [min(width, 18) for width in widths[:-1]]
        last_width = max(available_cell_width - sum(trimmed_widths), 16)
        return [*trimmed_widths, last_width]

    def _wrap_cell(self, text: str, width: int) -> list[str]:
        wrapped_lines = []
        for line in text.splitlines() or [""]:
            wrapped_lines.extend(textwrap.wrap(line, width=width) or [""])
        return wrapped_lines or [""]

    def _build_border(
        self,
        left: str,
        center: str,
        right: str,
        column_widths: Sequence[int],
    ) -> str:
        segments = ["─" * (width + 2) for width in column_widths]
        return self._paint(left + center.join(segments) + right, PANEL_BORDER_COLOR)

    def _content_width(self) -> int:
        terminal_width = shutil.get_terminal_size(fallback=(100, 20)).columns
        return max(min(terminal_width - 2, 110), 40)

    def _paint(self, text: str, color: str) -> str:
        return f"{color}{text}{RESET_COLOR}"

    def _visible_width(self, text: str) -> int:
        stripped = ANSI_PATTERN.sub("", text)
        return max((len(line) for line in stripped.splitlines()), default=0)


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
