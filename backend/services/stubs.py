"""Service stubs — bootstrap leaves business logic for subsequent prompts.

Sec 8 of PROMPT_01: "NO implementes lógica de negocio del WorkflowEngine."
Each stub raises ``NotImplementedStubException`` so any caller fails loudly
until the proper implementation lands in PROMPT 02-12.

The class skeletons remain so that:
  - DI wiring is in place
  - Tests can import the module
  - Future PRs only add bodies, not architecture
"""
from __future__ import annotations
from core.errors import NotImplementedStubException


class WorkflowEngine:
    """R14 — only place where the 4 decision trees live (sec 5)."""

    async def process(self, ticket: dict) -> dict:
        raise NotImplementedStubException("WorkflowEngine.process — implementado en PROMPT_05")


class IngestService:
    async def ingest_webhook(self, *, client_id: str, signature: str, body: bytes) -> dict:
        raise NotImplementedStubException("IngestService.ingest_webhook — PROMPT_04")

    async def pull(self, client_id: str) -> dict:
        raise NotImplementedStubException("IngestService.pull — PROMPT_04")

    async def upload_layout(self, *, tenant_id: str, file_bytes: bytes) -> dict:
        raise NotImplementedStubException("IngestService.upload_layout — PROMPT_04")


class AutomationService:
    """R03 — only executes when permission AND non-restricted motivo."""

    async def execute(self, *, ticket: dict, solucion: dict, channel: str) -> dict:
        raise NotImplementedStubException("AutomationService.execute — PROMPT_05")


class NotificationService:
    async def send_to_client(self, *, ticket: dict, channel: str, body: str) -> dict:
        raise NotImplementedStubException("NotificationService.send_to_client — PROMPT_11")

    async def send_to_carrier(self, *, ticket: dict, channel: str, payload: dict) -> dict:
        raise NotImplementedStubException("NotificationService.send_to_carrier — PROMPT_11")


class SlaService:
    async def evaluate(self, ticket: dict) -> dict:
        raise NotImplementedStubException("SlaService.evaluate — PROMPT_09")


class InactivityService:
    """R15 — clock pauses on espera_* statuses."""

    async def scan(self) -> int:
        raise NotImplementedStubException("InactivityService.scan — PROMPT_09")
