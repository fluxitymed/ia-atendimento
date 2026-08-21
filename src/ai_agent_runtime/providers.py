from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class CalendarProvider(ABC):
    @abstractmethod
    def get_availability(self, *, organization_id: str, criteria: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def create_appointment(self, *, organization_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def reschedule_appointment(self, *, organization_id: str, appointment_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def cancel_appointment(self, *, organization_id: str, appointment_id: str, reason: str | None = None) -> dict[str, Any]:
        raise NotImplementedError


class CRMProvider(ABC):
    @abstractmethod
    def upsert_contact(self, *, organization_id: str, contact: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def update_stage(self, *, organization_id: str, contact_id: str, stage: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def update_fields(self, *, organization_id: str, contact_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def add_note(self, *, organization_id: str, contact_id: str, note: str) -> dict[str, Any]:
        raise NotImplementedError


class RetrievalProvider(ABC):
    @abstractmethod
    def lexical_search(self, *, organization_id: str, query: str) -> list["RetrievalResult"]:
        raise NotImplementedError

    @abstractmethod
    def vector_search(self, *, organization_id: str, query: str) -> list["RetrievalResult"]:
        raise NotImplementedError


@dataclass(frozen=True)
class RetrievalResult:
    id: str
    organization_id: str
    document_version_id: str
    content: str
    score: float
    source: str
