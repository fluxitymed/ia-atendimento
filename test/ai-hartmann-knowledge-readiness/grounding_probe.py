"""Local-only grounding probe. Every response, source and ID below is synthetic.

Run ``PYTHONPATH=src python3 test/ai-hartmann-knowledge-readiness/grounding_probe.py``
to inspect claim text. This module is never imported by the production runtime.
"""

from __future__ import annotations

import json
import re

from ai_agent_runtime.crm_dispatch import CrmDispatchProcessor, handle_crm_dispatch
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.organization_config import InMemoryOrganizationConfigRepository, OrganizationRuntimeConfig
from ai_agent_runtime.whatsapp.zapi_server import (
    OpenAIWhatsAppResponseGenerator,
    _grounding_claim_diagnostics,
    _grounding_claim_topic,
    _independent_grounding_claims,
    _response_requires_authorized_evidence,
    validate_live_grounding,
)


ORG = "11111111-1111-4111-8111-111111111111"
QUESTION = "Quanto custa Botox e como funciona o agendamento?"
SOURCES = [
    {"content": "Botox com revisão em 15 dias custa R$ 120."},
    {"content": "O orçamento final é definido após avaliação."},
    {"content": "O agendamento da avaliação funciona pelo WhatsApp."},
    {"content": "Botox sem revisão custa R$ 100."},
]
RESPONSES = {
    "literal_price": "Botox com revisão em 15 dias custa R$ 120.",
    "paraphrased_price": "O valor do Botox com revisão em 15 dias é R$ 120.",
    "modality": "Botox sem revisão custa R$ 100.",
    "budget_policy": "O orçamento final depende da avaliação.",
    "scheduling": "O agendamento da avaliação é feito pelo WhatsApp.",
    "commercial_invite": "Posso encaminhar seu agendamento?",
    "price_and_invite": "Botox com revisão em 15 dias custa R$ 120 e posso encaminhar seu agendamento?",
    "price_and_scheduling": "Botox com revisão em 15 dias custa R$ 120 e o agendamento da avaliação funciona pelo WhatsApp.",
    "neutral_question": "Quer conversar sobre o próximo passo?",
    "commercial_nonfact": "Posso ajudar com sua dúvida?",
    "invented_price": "Botox com revisão em 15 dias custa R$ 190.",
    "diverging_price": "Botox sem revisão custa R$ 120.",
    "invented_payment": "O agendamento da avaliação funciona pelo WhatsApp. Você pode parcelar em 10x sem juros.",
    "invented_time": "O agendamento da avaliação funciona pelo WhatsApp. A avaliação pode ser marcada amanhã às 10h.",
    "invented_result": "O agendamento da avaliação funciona pelo WhatsApp. O resultado é garantido.",
    "clinical_advice": "O agendamento da avaliação funciona pelo WhatsApp. Você deve tomar um medicamento.",
    "partial": "O agendamento da avaliação funciona pelo WhatsApp. Botox com revisão em 15 dias custa R$ 190. Posso ajudar?",
}


def inspect_response(response: str, sources: list[dict[str, str]] | None = None) -> dict:
    evidence = SOURCES if sources is None else sources
    verdict = validate_live_grounding(response, evidence_count=len(evidence), evidence=evidence)
    diagnostics = iter(_grounding_claim_diagnostics(response, evidence))
    parts = [part.strip() for part in re.split(r"\.(?!\d)|[!?;]+", response.replace("Dra.", "Dra ").replace("Dr.", "Dr ")) if part.strip()]
    claims = []
    for part in parts:
        for claim in _independent_grounding_claims(part):
            factual = _response_requires_authorized_evidence(claim)
            claim_verdict = next(diagnostics, None) if factual else None
            matching = [source["content"] for source in evidence
                        if validate_live_grounding(claim, evidence_count=1, evidence=[source])["passed"]] if factual else []
            topic = _grounding_claim_topic(claim) if factual else None
            amount = re.search(r"r\s*\$\s*[\d.,]+", claim, flags=re.IGNORECASE)
            candidate = next((source["content"] for source in evidence
                              if (amount and amount.group().lower() in source["content"].lower())
                              or ("orçamento final" in claim.lower() and "orçamento final" in source["content"].lower())
                              or (re.search(r"\b(?:avaliação|consulta|agendamento|agenda|horário)\b", claim, flags=re.IGNORECASE)
                                  and "agendamento" in source["content"].lower())), None)
            claims.append({
                "text": claim.strip(),
                "classification": "FACTUAL" if factual else "NON_FACTUAL",
                "status": claim_verdict["status"] if claim_verdict else "NON_FACTUAL",
                "topic": topic,
                "candidateSyntheticSource": candidate,
                "supportingSyntheticSource": matching[0] if matching else None,
                "rule": ("_response_requires_authorized_evidence: no factual trigger" if not factual
                         else "_grounding_claim_diagnostics: source token/condition mismatch" if not matching
                         else "_grounding_claim_diagnostics: source supports claim"),
            })
    return {"syntheticResponse": response, "syntheticSources": [item["content"] for item in evidence],
            "claims": claims, "grounding": {"passed": verdict["passed"], "reason": verdict.get("reason"),
                                      "requiresEvidence": verdict["requiresEvidence"]}}


def _uid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


class SyntheticRetrieval:
    def search(self, organization_id: str, query: str, *, limit: int = 6) -> list[dict]:
        assert organization_id == ORG
        return [{"id": _uid(i), "organization_id": ORG, "document_id": _uid(i + 100),
                 "document_version_id": _uid(i + 200), **source} for i, source in enumerate(SOURCES, 1)]

    def closed_world_procedure_decision(self, organization_id: str, query: str):
        return None


class SyntheticTransport:
    def __init__(self, answers: list[str]):
        self.answers = answers
        self.calls = 0

    def post_json(self, url, *, headers, payload):
        answer = self.answers[min(self.calls, len(self.answers) - 1)]
        self.calls += 1
        return {"status": "completed", "output_text": answer}


def dispatch(answers: list[str]) -> dict:
    transport, logs = SyntheticTransport(answers), []
    graph = AgentRuntimeGraph(response_generator=OpenAIWhatsAppResponseGenerator(
        OpenAIResponsesProvider(IntegrationConfig(openai_api_key="synthetic-only"), transport),
        retrieval=SyntheticRetrieval(),
    ))
    worker = CrmDispatchProcessor(
        config_repository=InMemoryOrganizationConfigRepository([OrganizationRuntimeConfig(organization_id=ORG)]),
        graph_factory=lambda _: graph,
        logger=lambda event, fields: logs.append((event, fields)),
    )
    event = {"version": "1", "correlationId": _uid(301), "organizationId": ORG,
             "conversationId": _uid(302), "providerConnectionId": _uid(303),
             "contactId": None, "inboundMessageId": _uid(304), "mode": "AI", "modeVersion": 1,
             "message": {"type": "text", "text": QUESTION, "timestamp": "2026-10-10T12:00:00Z"}}
    status, body = handle_crm_dispatch(
        json.dumps(event).encode(), "Bearer synthetic-service-token-000000000000",
        token="synthetic-service-token-000000000000", processor=worker,
    )
    terminal = [fields for name, fields in logs if name == "crm_dispatch_decision"][-1]
    return {"http": status, "action": body.get("action"), "message": body.get("message"),
            "modelCalls": transport.calls, "reasonCode": terminal["reasonCode"],
            "decisionOrigin": terminal["decisionOrigin"],
            "initialGroundingFailureOrigin": terminal.get("initialGroundingFailureOrigin"),
            "groundingFailureOrigin": terminal.get("groundingFailureOrigin"),
            "regenerationUsed": terminal["regenerationUsed"],
            "promptTopicCoverage": terminal["promptTopicCoverage"],
            "promptChunkIds": terminal["promptChunkIds"],
            "safeTerminalLog": terminal}


if __name__ == "__main__":
    for name, response in RESPONSES.items():
        print(name + ": " + json.dumps(inspect_response(response), ensure_ascii=False))
