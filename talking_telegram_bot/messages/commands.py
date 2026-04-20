from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProcessTextMessage:
    message: Any
    raw_text: str


@dataclass(frozen=True, slots=True)
class ProcessDocumentMessage:
    message: Any
    file_name: str | None
    file_size: int | None
    content: bytes


@dataclass(frozen=True, slots=True)
class ListModels:
    message: Any


@dataclass(frozen=True, slots=True)
class ShowRole:
    message: Any


@dataclass(frozen=True, slots=True)
class UpdateRole:
    message: Any
    raw_role: str


@dataclass(frozen=True, slots=True)
class SelectModel:
    callback_query: Any
    callback_data: str

