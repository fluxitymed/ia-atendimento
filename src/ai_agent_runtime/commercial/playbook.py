from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SalesStage(str, Enum):
    OPENING = "OPENING"
    DISCOVERY = "DISCOVERY"
    NEED_CONFIRMED = "NEED_CONFIRMED"
    VALUE_BRIDGE = "VALUE_BRIDGE"
    CTA = "CTA"
    OBJECTION_HANDLING = "OBJECTION_HANDLING"
    SCHEDULING = "SCHEDULING"
    HUMAN_HANDOFF = "HUMAN_HANDOFF"


class ConversationFatigue(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PatientEngagement(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ObjectionState(str, Enum):
    NONE = "NONE"
    PRICE = "PRICE"
    FEAR_OR_RISK = "FEAR_OR_RISK"
    TRUST = "TRUST"
    TIMING = "TIMING"


class AppointmentReadiness(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class NextBestAction(str, Enum):
    ASK_DISCOVERY = "ASK_DISCOVERY"
    BUILD_VALUE = "BUILD_VALUE"
    PROPOSE_NEXT_STEP = "PROPOSE_NEXT_STEP"
    ANSWER_FACTUAL = "ANSWER_FACTUAL"
    HANDLE_OBJECTION = "HANDLE_OBJECTION"
    SCHEDULE = "SCHEDULE"
    HUMAN_HANDOFF = "HUMAN_HANDOFF"
    RESPOND_ONLY = "RESPOND_ONLY"
    WAIT_FOR_PATIENT = "WAIT_FOR_PATIENT"
    ANSWER_CURRENT_TURN = "ANSWER_CURRENT_TURN"
    NO_COMMERCIAL_ADVANCE = "NO_COMMERCIAL_ADVANCE"


class CurrentTurnIntent(str, Enum):
    GREETING = "GREETING"
    IDENTITY_QUERY = "IDENTITY_QUERY"
    FACTUAL_QUERY = "FACTUAL_QUERY"
    OPERATIONAL_QUERY = "OPERATIONAL_QUERY"
    ACKNOWLEDGEMENT = "ACKNOWLEDGEMENT"
    CONVERSATIONAL_RESPONSE = "CONVERSATIONAL_RESPONSE"
    OBJECTION = "OBJECTION"
    SCHEDULING_RESPONSE = "SCHEDULING_RESPONSE"
    DISCOVERY_RESPONSE = "DISCOVERY_RESPONSE"
    TOPIC_CHANGE = "TOPIC_CHANGE"
    PROCEDURE_INTEREST = "PROCEDURE_INTEREST"
    CORRECTION = "CORRECTION"
    SMALL_TALK = "SMALL_TALK"
    CLINICAL_SAFETY = "CLINICAL_SAFETY"
    OTHER = "OTHER"


class ContextContinuity(str, Enum):
    STRONG_CONTINUATION = "STRONG_CONTINUATION"
    WEAK_CONTINUATION = "WEAK_CONTINUATION"
    NEW_NEUTRAL_TURN = "NEW_NEUTRAL_TURN"
    TOPIC_CHANGE = "TOPIC_CHANGE"
    SIDE_QUERY = "SIDE_QUERY"


class CommercialPressureLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class OrganizationCommercialConfig:
    assistant_name: str | None = None
    assistant_role: str | None = None
    clinic_name: str | None = None
    doctor_name: str | None = None
    tone: str = "natural, consultivo e objetivo"
    sales_goal: str = "conduzir o paciente ate o proximo passo adequado"
    primary_conversion_action: str = "avaliacao ou consulta"
    max_discovery_depth: int = 3
    cta_style: str = "natural e sem pressao"
    appointment_flow: str = "somente quando contexto de agendamento estiver ativo"
    locations: tuple[str, ...] = ()
    business_hours: str | None = None


@dataclass(frozen=True)
class CommercialState:
    sales_stage: SalesStage
    discovery_question_count: int
    discovery_depth: int
    minimum_discovery_complete: bool
    patient_need_summary: dict[str, str] = field(default_factory=dict)
    patient_engagement: PatientEngagement = PatientEngagement.MEDIUM
    conversation_fatigue: ConversationFatigue = ConversationFatigue.LOW
    objection_state: ObjectionState = ObjectionState.NONE
    appointment_readiness: AppointmentReadiness = AppointmentReadiness.LOW
    next_best_action: NextBestAction = NextBestAction.ASK_DISCOVERY
    should_introduce: bool = False
    should_avoid_recap: bool = False
    discovery_information_gain: int = 0
    contextual_short_answer_resolved: bool = False
    naturalness_policy: str = "ANTI_ECHO_NO_FORCED_CHOICE"
    operational_memory: dict[str, str] = field(default_factory=dict)
    registration_memory: dict[str, str] = field(default_factory=dict)
    missing_required_fields: tuple[str, ...] = ()
    registration_complete: bool = False
    assistant_introduced: bool = False
    answered_facts: dict[str, Any] = field(default_factory=dict)
    scheduling_state: str = "NONE"
    correction_state: dict[str, Any] = field(default_factory=dict)
    registration_collection_policy: str = "ASK_ONLY_MISSING_FIELDS"
    current_turn_intent: CurrentTurnIntent = CurrentTurnIntent.OTHER
    context_continuity: ContextContinuity = ContextContinuity.NEW_NEUTRAL_TURN
    active_topic: str | None = None
    persistent_memory: dict[str, str] = field(default_factory=dict)
    active_context: dict[str, Any] = field(default_factory=dict)
    context_age_seconds: int | None = None
    cta_policy: str = "CTA_ALLOWED_WHEN_NATURAL"
    commercial_pressure_level: CommercialPressureLevel = CommercialPressureLevel.LOW
    patient_name_resolution: dict[str, Any] = field(default_factory=dict)
    appointment_intent_resolution: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sales_stage": self.sales_stage.value,
            "discovery_question_count": self.discovery_question_count,
            "discovery_depth": self.discovery_depth,
            "minimum_discovery_complete": self.minimum_discovery_complete,
            "patient_need_summary": dict(self.patient_need_summary),
            "patient_engagement": self.patient_engagement.value,
            "conversation_fatigue": self.conversation_fatigue.value,
            "objection_state": self.objection_state.value,
            "appointment_readiness": self.appointment_readiness.value,
            "next_best_action": self.next_best_action.value,
            "should_introduce": self.should_introduce,
            "should_avoid_recap": self.should_avoid_recap,
            "discovery_information_gain": self.discovery_information_gain,
            "contextual_short_answer_resolved": self.contextual_short_answer_resolved,
            "naturalness_policy": self.naturalness_policy,
            "operational_memory": dict(self.operational_memory),
            "registration_memory": dict(self.registration_memory),
            "missing_required_fields": list(self.missing_required_fields),
            "registration_complete": self.registration_complete,
            "assistant_introduced": self.assistant_introduced,
            "answered_facts": dict(self.answered_facts),
            "scheduling_state": self.scheduling_state,
            "correction_state": dict(self.correction_state),
            "registration_collection_policy": self.registration_collection_policy,
            "current_turn_intent": self.current_turn_intent.value,
            "context_continuity": self.context_continuity.value,
            "active_topic": self.active_topic,
            "persistent_memory": dict(self.persistent_memory),
            "active_context": dict(self.active_context),
            "context_age_seconds": self.context_age_seconds,
            "cta_policy": self.cta_policy,
            "commercial_pressure_level": self.commercial_pressure_level.value,
            "patient_name_resolution": dict(self.patient_name_resolution),
            "appointment_intent_resolution": dict(self.appointment_intent_resolution),
        }


class CommercialPlaybook:
    def evaluate(
        self,
        messages: list[dict[str, Any]],
        *,
        current_message: str,
        organization_config: OrganizationCommercialConfig | None = None,
        scheduling_context_active: bool = False,
        previous_assistant_question: str = "",
        channel_contact_external_id: str | None = None,
        scheduling_status: str | None = None,
        assistant_introduced: bool | None = None,
        answered_facts: dict[str, Any] | None = None,
        current_message_at: Any | None = None,
        previous_assistant_message_at: Any | None = None,
    ) -> CommercialState:
        config = organization_config or OrganizationCommercialConfig()
        inbound_texts = [str(item.get("text") or "") for item in messages if item.get("direction") == "inbound" and item.get("text")]
        current = _normalize(current_message)
        previous_inbound_texts = list(inbound_texts)
        if previous_inbound_texts and _normalize(previous_inbound_texts[-1]) == current:
            previous_inbound_texts.pop()
        all_text = _normalize(" ".join([*inbound_texts, current_message]))
        previous_summary = _need_summary(
            _normalize(" ".join(previous_inbound_texts)),
            current_text=current,
            previous_assistant_question=previous_assistant_question,
        )
        full_summary = _need_summary(
            all_text,
            current_text=current,
            previous_assistant_question=previous_assistant_question,
        )
        current_summary = _need_summary(
            current,
            current_text=current,
            previous_assistant_question=previous_assistant_question,
        )
        persistent_memory = _operational_memory(
            messages,
            current_message=current_message,
            patient_need_summary=full_summary,
            channel_contact_external_id=channel_contact_external_id,
            previous_assistant_question=previous_assistant_question,
        )
        registration_memory, patient_name_resolution = _registration_memory(
            messages,
            current_message=current_message,
            previous_assistant_question=previous_assistant_question,
        )
        persistent_memory.update(registration_memory)
        context_age_seconds = _context_age_seconds(current_message_at, previous_assistant_message_at)
        current_turn_intent = _current_turn_intent(
            current,
            current_summary=current_summary,
            historical_summary=previous_summary,
            previous_assistant_question=previous_assistant_question,
        )
        context_continuity = _context_continuity(
            current,
            current_turn_intent=current_turn_intent,
            current_summary=current_summary,
            historical_summary=previous_summary,
            previous_assistant_question=previous_assistant_question,
            context_age_seconds=context_age_seconds,
        )
        summary = _active_need_summary(
            current_summary=current_summary,
            historical_summary=full_summary if context_continuity != ContextContinuity.TOPIC_CHANGE else previous_summary,
            context_continuity=context_continuity,
        )
        active_topic = summary.get("procedure_interest")
        appointment_intent_resolution = _resolve_appointment_intent(
            current,
            previous_assistant_question=previous_assistant_question,
            historical_appointment_intent=bool(persistent_memory.get("appointment_intent")),
            scheduling_context_active=scheduling_context_active,
            scheduling_status=scheduling_status,
            registration_data_present=bool(registration_memory),
        )
        operational_memory = dict(persistent_memory)
        operational_memory.update(registration_memory)
        if appointment_intent_resolution["active"]:
            operational_memory["appointment_intent"] = "true"
        else:
            operational_memory.pop("appointment_intent", None)
        missing_required_fields = _missing_required_registration_fields(registration_memory)
        registration_complete = not missing_required_fields and bool(registration_memory)
        correction_state = _correction_state(inbound_texts, current_message=current_message)
        scheduling_state = _scheduling_state(
            operational_memory,
            scheduling_context_active=scheduling_context_active,
            scheduling_status=scheduling_status,
            appointment_intent_active=bool(appointment_intent_resolution["active"]),
        )
        discovery_depth = _discovery_depth(summary)
        discovery_question_count = _estimate_discovery_question_count(inbound_texts, previous_assistant_question)
        minimum_complete = _minimum_discovery_complete(summary)
        contextual_short_answer = _contextual_short_answer_resolved(current, previous_assistant_question)
        fatigue = _conversation_fatigue(inbound_texts, discovery_question_count, discovery_depth=discovery_depth)
        objection = _objection_state(
            current,
            previous_assistant_question=previous_assistant_question,
            patient_has_fear_context=_patient_has_fear_context(all_text),
        )
        readiness = _appointment_readiness(current, minimum_complete)
        introduced = bool(assistant_introduced) if assistant_introduced is not None else len(inbound_texts) > 1
        should_introduce = not introduced
        active_scheduling = scheduling_state in {
            "COLLECTING_REQUIRED_DATA",
            "COLLECTING_SCHEDULING_PREFERENCES",
            "CHECKING_AVAILABILITY",
            "BOOKING_IN_PROGRESS",
            "APPOINTMENT_INTENT",
        }
        respond_only_intents = {
            CurrentTurnIntent.GREETING,
            CurrentTurnIntent.IDENTITY_QUERY,
            CurrentTurnIntent.ACKNOWLEDGEMENT,
            CurrentTurnIntent.SMALL_TALK,
            CurrentTurnIntent.CORRECTION,
        }
        neutral_turn_without_active_context = (
            current_turn_intent == CurrentTurnIntent.OTHER
            and context_continuity == ContextContinuity.NEW_NEUTRAL_TURN
            and not current_summary
            and not registration_memory
            and not active_scheduling
            and not _appointment_intent_detected(current, current_message=current, previous_assistant_question=previous_assistant_question)
        )

        if (
            current_turn_intent in respond_only_intents
            or neutral_turn_without_active_context
        ) and not _appointment_intent_detected(current, current_message=current, previous_assistant_question=previous_assistant_question):
            stage = SalesStage.OPENING
            next_action = NextBestAction.RESPOND_ONLY
        elif appointment_intent_resolution["active"] and (scheduling_context_active or active_scheduling):
            stage = SalesStage.SCHEDULING
            next_action = NextBestAction.SCHEDULE
        elif objection != ObjectionState.NONE and summary.get("fear_topics"):
            stage = SalesStage.VALUE_BRIDGE
            next_action = NextBestAction.BUILD_VALUE
        elif objection != ObjectionState.NONE:
            stage = SalesStage.OBJECTION_HANDLING
            next_action = NextBestAction.HANDLE_OBJECTION
        elif _looks_like_factual_attribute_question(current):
            stage = SalesStage.DISCOVERY
            next_action = NextBestAction.ANSWER_FACTUAL
        elif minimum_complete and (fatigue == ConversationFatigue.HIGH or discovery_question_count >= config.max_discovery_depth):
            stage = SalesStage.CTA
            next_action = NextBestAction.PROPOSE_NEXT_STEP
        elif minimum_complete:
            stage = SalesStage.VALUE_BRIDGE
            next_action = NextBestAction.BUILD_VALUE
        elif fatigue == ConversationFatigue.HIGH:
            stage = SalesStage.VALUE_BRIDGE
            next_action = NextBestAction.PROPOSE_NEXT_STEP
        elif should_introduce:
            stage = SalesStage.OPENING
            next_action = NextBestAction.ASK_DISCOVERY
        else:
            stage = SalesStage.DISCOVERY
            next_action = NextBestAction.ASK_DISCOVERY

        return CommercialState(
            sales_stage=stage,
            discovery_question_count=discovery_question_count,
            discovery_depth=discovery_depth,
            minimum_discovery_complete=minimum_complete,
            patient_need_summary=summary,
            patient_engagement=_patient_engagement(inbound_texts),
            conversation_fatigue=fatigue,
            objection_state=objection,
            appointment_readiness=readiness,
            next_best_action=next_action,
            should_introduce=should_introduce,
            should_avoid_recap=len(inbound_texts) >= 3 or fatigue != ConversationFatigue.LOW,
            discovery_information_gain=discovery_depth,
            contextual_short_answer_resolved=contextual_short_answer,
            operational_memory=operational_memory,
            registration_memory=registration_memory,
            missing_required_fields=missing_required_fields,
            registration_complete=registration_complete,
            assistant_introduced=introduced,
            answered_facts=dict(answered_facts or {}),
            scheduling_state=scheduling_state,
            correction_state=correction_state,
            registration_collection_policy=_registration_collection_policy(missing_required_fields),
            current_turn_intent=current_turn_intent,
            context_continuity=context_continuity,
            active_topic=active_topic,
            persistent_memory=persistent_memory,
            active_context={
                "active_topic": active_topic,
                "pending_question": previous_assistant_question if context_continuity == ContextContinuity.STRONG_CONTINUATION else "",
                "pending_cta": appointment_intent_resolution["source"] == "ACTIVE_APPOINTMENT_CTA",
                "context_is_stale": context_continuity == ContextContinuity.NEW_NEUTRAL_TURN and context_age_seconds is not None and context_age_seconds >= 1800,
            },
            context_age_seconds=context_age_seconds,
            cta_policy=_cta_policy(current_turn_intent, context_continuity, next_action),
            commercial_pressure_level=_commercial_pressure_level(current_turn_intent, next_action),
            patient_name_resolution=patient_name_resolution,
            appointment_intent_resolution=appointment_intent_resolution,
        )

    def prompt_sections(
        self,
        commercial_state: CommercialState,
        *,
        organization_config: OrganizationCommercialConfig | None = None,
        authorized_evidence: str = "",
    ) -> str:
        config = organization_config or OrganizationCommercialConfig()
        return "\n\n".join(
            [
                _base_safety_section(),
                _commercial_playbook_section(commercial_state, config),
                _organization_config_section(config, commercial_state.should_introduce),
                _authorized_evidence_section(authorized_evidence),
                _conversation_state_section(commercial_state),
            ]
        )


def organization_config_from_context(context: dict[str, Any] | None) -> OrganizationCommercialConfig:
    data = dict((context or {}).get("organizationConfig") or {})
    return OrganizationCommercialConfig(
        assistant_name=_optional_text(data.get("assistant_name") or data.get("assistantName")),
        assistant_role=_optional_text(data.get("assistant_role") or data.get("assistantRole")),
        clinic_name=_optional_text(data.get("clinic_name") or data.get("clinicName")),
        doctor_name=_optional_text(data.get("doctor_name") or data.get("doctorName")),
        tone=str(data.get("tone") or OrganizationCommercialConfig.tone),
        sales_goal=str(data.get("sales_goal") or data.get("salesGoal") or OrganizationCommercialConfig.sales_goal),
        primary_conversion_action=str(data.get("primary_conversion_action") or data.get("primaryConversionAction") or OrganizationCommercialConfig.primary_conversion_action),
        max_discovery_depth=int(data.get("max_discovery_depth") or data.get("maxDiscoveryDepth") or OrganizationCommercialConfig.max_discovery_depth),
        cta_style=str(data.get("cta_style") or data.get("ctaStyle") or OrganizationCommercialConfig.cta_style),
        appointment_flow=str(data.get("appointment_flow") or data.get("appointmentFlow") or OrganizationCommercialConfig.appointment_flow),
        locations=tuple(str(item) for item in data.get("locations", ()) if str(item).strip()),
        business_hours=_optional_text(data.get("business_hours") or data.get("businessHours")),
    )


def _base_safety_section() -> str:
    return (
        "BASE SAFETY\n"
        "- O playbook comercial nao e fonte factual autorizada.\n"
        "- Nao afirme fatos sobre clinica, medico, procedimento, preco, resultado, tecnica, duracao, agenda ou politicas sem evidencia autorizada.\n"
        "- Nunca mencione RAG, retrieval, grounding, base de conhecimento, documentos, score, falta de evidencia, equipe, humano, handoff ou limitacao interna ao paciente.\n"
        "- Nunca diga frases como 'nao consigo confirmar por aqui', 'nao tenho essa informacao', 'nao encontrei', 'nao consigo afirmar', 'nao tenho acesso', 'segundo os dados disponiveis' ou 'a equipe pode verificar'.\n"
        "- Se faltar um atributo factual essencial, use a politica de handoff silencioso existente. Se a lacuna nao for essencial para avancar, nao fale da lacuna: use fatos autorizados e conduza o proximo passo sem inventar."
    )


def _commercial_playbook_section(state: CommercialState, config: OrganizationCommercialConfig) -> str:
    return (
        "COMMERCIAL PLAYBOOK\n"
        "- Aja como vendedora consultiva: conduza a decisao, nao como FAQ ou formulario.\n"
        "- Antes de perguntar, decida se ja ha informacao suficiente para avancar.\n"
        "- Descoberta nao e checklist: use SPIN como raciocinio flexivel, nao como roteiro obrigatorio.\n"
        f"- Maximo normal de descoberta antes de reavaliar: {config.max_discovery_depth} perguntas consecutivas.\n"
        "- Se a necessidade ja estiver clara, construa ponte de valor ou proponha proximo passo.\n"
        "- Reconheca respostas brevemente; nao recapitule todo o historico em cada turno.\n"
        "- Nao ecoe nem parafraseie mecanicamente a ultima resposta do paciente.\n"
        "- Evite empatia performatica padrao; nao use bordoes recorrentes como 'Perfeito', 'Entendi', 'Certo', 'Otimo', 'Combinado', 'Compreendo', 'E compreensivel', 'muitas pessoas', 'vou te orientar', 'voce tem razao' ou 'corrigindo'.\n"
        "- Use linguagem simples de WhatsApp: sem Markdown artificial, sem negrito com asteriscos, sem travessao como estilo padrao, sem texto de SAC e sem cara de LLM.\n"
        "- Evite menus A/B/C, alternativas numeradas e escolha forcada; use conversa natural, com pergunta aberta curta quando precisar.\n"
        "- Nao force o paciente a escolher subtipo tecnico antes da avaliacao quando o interesse geral ja permite avancar.\n"
        "- Faca no maximo uma pergunta principal por mensagem.\n"
        f"- Next best action atual: {state.next_best_action.value}."
    )


def _organization_config_section(config: OrganizationCommercialConfig, should_introduce: bool) -> str:
    parts = [
        "ORGANIZATION CONFIGURATION",
        f"- Tom: {config.tone}.",
        f"- Objetivo comercial: {config.sales_goal}.",
        f"- Conversao principal: {config.primary_conversion_action}.",
        f"- Estilo de CTA: {config.cta_style}.",
        f"- Agenda: {config.appointment_flow}.",
    ]
    if config.doctor_name:
        parts.append(f"- Profissional de referencia: {config.doctor_name}.")
    if config.business_hours:
        parts.append(f"- Horarios autorizados: {config.business_hours}.")
    if config.locations:
        parts.append(f"- Locais autorizados: {' | '.join(config.locations)}.")
    if should_introduce:
        identity = _configured_identity(config)
        if identity:
            parts.append(f"- Primeiro contato: apresente-se naturalmente como {identity}.")
        else:
            parts.append("- Primeiro contato: cumprimente de forma natural sem inventar nome, papel ou clinica.")
    else:
        parts.append("- Nao repita apresentacao inicial quando a conversa ja tem historico.")
    return "\n".join(parts)


def _authorized_evidence_section(authorized_evidence: str) -> str:
    if authorized_evidence.strip():
        return f"AUTHORIZED EVIDENCE\n{authorized_evidence.strip()}"
    return "AUTHORIZED EVIDENCE\n- Nenhuma evidencia factual autorizada foi fornecida para este turno."


def _conversation_state_section(state: CommercialState) -> str:
    return (
        "CONVERSATION STATE\n"
        f"- sales_stage: {state.sales_stage.value}\n"
        f"- discovery_question_count: {state.discovery_question_count}\n"
        f"- discovery_depth: {state.discovery_depth}\n"
        f"- minimum_discovery_complete: {str(state.minimum_discovery_complete).lower()}\n"
        f"- patient_need_summary: {state.patient_need_summary}\n"
        f"- patient_engagement: {state.patient_engagement.value}\n"
        f"- conversation_fatigue: {state.conversation_fatigue.value}\n"
        f"- objection_state: {state.objection_state.value}\n"
        f"- appointment_readiness: {state.appointment_readiness.value}\n"
        f"- next_best_action: {state.next_best_action.value}\n"
        f"- avoid_excessive_recap: {str(state.should_avoid_recap).lower()}\n"
        f"- discovery_information_gain: {state.discovery_information_gain}\n"
        f"- contextual_short_answer_resolved: {str(state.contextual_short_answer_resolved).lower()}\n"
        f"- naturalness_policy: {state.naturalness_policy}\n"
        f"- operational_memory: {state.operational_memory}\n"
        f"- registration_memory: {state.registration_memory}\n"
        f"- missing_required_fields: {list(state.missing_required_fields)}\n"
        f"- registration_complete: {str(state.registration_complete).lower()}\n"
        f"- assistant_introduced: {str(state.assistant_introduced).lower()}\n"
        f"- answered_facts: {state.answered_facts}\n"
        f"- scheduling_state: {state.scheduling_state}\n"
        f"- correction_state: {state.correction_state}\n"
        f"- registration_collection_policy: {state.registration_collection_policy}\n"
        f"- current_turn_intent: {state.current_turn_intent.value}\n"
        f"- context_continuity: {state.context_continuity.value}\n"
        f"- active_topic: {state.active_topic}\n"
        f"- persistent_memory: {state.persistent_memory}\n"
        f"- active_context: {state.active_context}\n"
        f"- context_age_seconds: {state.context_age_seconds}\n"
        f"- cta_policy: {state.cta_policy}\n"
        f"- commercial_pressure_level: {state.commercial_pressure_level.value}\n"
        "- Prioridade de decisao: current_turn_intent > active_context > persistent_memory.\n"
        "- Persistent memory personaliza e evita repeticao, mas nao torna automaticamente o assunto antigo ativo.\n"
        "- Se next_best_action=RESPOND_ONLY, responda somente ao turno atual, sem CTA, discovery, pitch, agendamento ou retomada espontanea de procedimento.\n"
        "- Se context_continuity=SIDE_QUERY, responda a pergunta lateral sem apagar a memoria persistente e sem mencionar o topico antigo no mesmo turno.\n"
        "- Se context_continuity=NEW_NEUTRAL_TURN, trate como retomada neutra; nao reutilize active topic antigo sem sinal semantico atual.\n"
        "- Antes de pedir dado operacional, confira operational_memory. Nao pergunte novamente dado conhecido, salvo contradicao, ambiguidade ou confirmacao final.\n"
        "- Nao repita espontaneamente fatos ja presentes em answered_facts; repita apenas se o paciente perguntar de novo ou houver correcao.\n"
        "- Se patient_phone veio do WhatsApp, nao pergunte qual e o WhatsApp do paciente.\n"
        "- Na coleta cadastral, use missing_required_fields; pergunte somente os campos faltantes relacionados em uma unica mensagem ou bloco curto.\n"
        "- Se registration_complete=true, pare de pedir cadastro e avance para unidade, data, horario ou verificacao de disponibilidade.\n"
        "- Aceite dados claros sem perguntar 'confirma?' ou 'correto?', salvo conflito, baixa confianca, formato invalido ou acao irreversivel.\n"
        "- Nao complete cidade, bairro, estado ou logradouro usando conhecimento externo; preserve o que o paciente informou com normalizacao deterministica simples.\n"
        "- Confirmacao definitiva de agendamento so e permitida quando scheduling_state=BOOKED por retorno de ferramenta. Antes disso use linguagem de verificacao/solicitacao.\n"
        "- Se houver correcao de nome, genero linguistico, pronome ou preferencia de tratamento no turno atual, reconheca uma vez de modo breve; depois apenas use corretamente sem repetir a correcao."
    )


def _need_summary(text: str, *, current_text: str = "", previous_assistant_question: str = "") -> dict[str, str]:
    summary: dict[str, str] = {}
    procedure = _first_match(text, {
        "Botox": ("botox", "toxina botulinica"),
        "Preenchimento": ("preenchimento",),
        "Limpeza de pele": ("limpeza de pele",),
        "Blefaroplastia": ("blefaroplastia",),
        "implante": ("implante", "implantes", "protocolo", "protese", "proteses"),
        "lentes": ("lente", "lentes", "faceta", "facetas"),
        "harmonizacao": ("harmonizacao", "harmonização"),
    })
    if procedure:
        summary["procedure_interest"] = procedure
    if any(_contains_term(text, term) for term in ("substituir", "perdi", "perdeu", "perdido", "perdida", "faltando", "extrai", "arranquei")) and _contains_term(text, "dente"):
        summary["situation"] = "substituir dente perdido"
    elif any(_contains_term(text, term) for term in ("reabilitacao", "mastigar", "sorriso", "sem dente")):
        summary["situation"] = "reabilitacao oral"
    region = _first_match(text, {
        "testa": ("testa",),
        "sobrancelhas": ("sobrancelha", "sobrancelhas"),
        "olhos": ("olhos", "olhar"),
        "rosto": ("rosto", "face"),
    })
    if region:
        summary["region_interest"] = region
    complaint = _first_match(text, {
        "marcas em repouso": ("repouso", "relaxado", "visiveis"),
        "linhas de expressao": ("linhas", "marcas", "rugas"),
        "aparencia cansada": ("cansado", "cansada", "cansaco"),
    })
    if complaint:
        summary["main_concern"] = complaint
    motivation = _first_match(text, {
        "suavizar": ("suavizar", "melhorar", "amenizar"),
        "aparencia menos cansada": ("cansado", "cansada", "cansaco"),
        "naturalidade": ("natural", "travado", "artificial"),
    })
    if motivation:
        summary["motivation"] = motivation
    if any(_contains_term(text, term) for term in ("medo", "receio", "nervoso", "nervosa", "ansioso", "ansiosa", "inseguro", "insegura")):
        summary["main_objection"] = "medo"
        if any(_contains_term(current_text, term) for term in ("medo", "receio", "nervoso", "nervosa", "ansioso", "ansiosa", "inseguro", "insegura")):
            if any(_contains_term(current_text, term) for term in ("procedimento", "fazer", "cirurgia")):
                summary["fear_topics"] = "procedimento"
            elif any(_contains_term(current_text, term) for term in ("pos", "pós", "recuperacao", "recuperação", "operatorio", "operatório")):
                summary["fear_topics"] = "pos_operatorio"
    if summary.get("main_objection") == "medo" and _contextual_short_answer_resolved(current_text, previous_assistant_question) and _previous_question_mentions_fear(previous_assistant_question):
        previous = _normalize(previous_assistant_question)
        current = _normalize(current_text)
        if any(term in previous for term in ("procedimento", "fazer", "cirurgia")) and any(term in previous for term in ("pos", "recuperacao", "operatorio")) and current in {"os dois", "ambos", "as duas", "tudo isso"}:
            summary["fear_topics"] = "procedimento,pos_operatorio"
        elif any(term in previous for term in ("procedimento", "fazer", "cirurgia")) and current in {"sim", "isso", "exatamente"}:
            summary["fear_topics"] = "procedimento"
        elif any(term in previous for term in ("pos", "recuperacao", "operatorio")) and current in {"sim", "isso", "exatamente"}:
            summary["fear_topics"] = "pos_operatorio"
    if re.search(r"\b(ano|anos|mes|meses|semana|semanas)\b", text):
        summary["duration_context"] = "informado"
    return summary


def _discovery_depth(summary: dict[str, str]) -> int:
    return sum(1 for key in ("procedure_interest", "region_interest", "main_concern", "motivation", "duration_context", "situation", "main_objection", "fear_topics") if key in summary)


def _operational_memory(
    messages: list[dict[str, Any]],
    *,
    current_message: str,
    patient_need_summary: dict[str, str],
    channel_contact_external_id: str | None = None,
    previous_assistant_question: str = "",
) -> dict[str, str]:
    inbound_texts = [str(item.get("text") or "") for item in messages if item.get("direction") == "inbound" and item.get("text")]
    text = _normalize(" ".join([*inbound_texts, current_message]))
    memory: dict[str, str] = dict(patient_need_summary)
    phone = _normalized_phone(channel_contact_external_id)
    if phone:
        memory["patient_phone"] = phone
    email = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", " ".join([*inbound_texts, current_message]), re.IGNORECASE)
    if email:
        memory["email"] = email.group(0)
    cpf = re.search(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", " ".join([*inbound_texts, current_message]))
    if cpf:
        memory["cpf"] = cpf.group(0)
    rg = re.search(r"\brg\s*[:\-]?\s*([0-9.\-]{5,})", text)
    if rg:
        memory["rg"] = rg.group(1)
    cep = re.search(r"\b\d{5}-?\d{3}\b", " ".join([*inbound_texts, current_message]))
    if cep:
        memory["cep"] = cep.group(0)
    location = _first_match(text, {
        "Brotas": ("brotas", "matatu"),
        "Pituba": ("pituba", "hospital da bahia"),
    })
    if location:
        memory["preferred_location"] = location
    date = _preferred_date(text)
    if date:
        memory["preferred_date"] = date
    time = _preferred_time(text)
    if time:
        memory["preferred_time"] = time
    if any(_appointment_intent_detected(item, current_message=item, previous_assistant_question="") for item in inbound_texts):
        memory["appointment_intent"] = "true"
    if any(_contains_term(text, term) for term in ("endereco", "endereço", "rua", "avenida", "av.", "numero", "bairro")):
        memory["address"] = "informado"
    return memory


def _registration_memory(
    messages: list[dict[str, Any]],
    *,
    current_message: str,
    previous_assistant_question: str = "",
) -> tuple[dict[str, str], dict[str, Any]]:
    inbound_texts = [str(item.get("text") or "") for item in messages if item.get("direction") == "inbound" and item.get("text")]
    texts = [*inbound_texts]
    if not texts or texts[-1] != current_message:
        texts.append(current_message)
    joined = " ".join(texts)
    memory: dict[str, str] = {}
    email = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", joined, re.IGNORECASE)
    if email:
        memory["email"] = email.group(0)
    cpf = _extract_cpf(joined)
    if cpf:
        memory["cpf"] = cpf
    rg = _extract_rg(joined)
    if rg:
        memory["rg"] = rg
    cep = _extract_cep(joined, rg=rg, cpf=cpf)
    if cep:
        memory["cep"] = cep
    name, name_resolution = _extract_patient_name(
        texts,
        current_message=current_message,
        previous_assistant_question=previous_assistant_question,
    )
    if name:
        memory["patient_name"] = name
    address = _extract_address(texts, memory)
    memory.update(address)
    return memory, name_resolution


def _extract_cpf(text: str) -> str | None:
    match = re.search(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", text)
    if not match:
        return None
    digits = re.sub(r"\D+", "", match.group(0))
    return digits if len(digits) == 11 else None


def _extract_cep(text: str, *, rg: str | None, cpf: str | None) -> str | None:
    labelled = re.search(r"\bcep\s*[:\-]?\s*(\d{5}-?\d{3})(?![\d-])", text, re.IGNORECASE)
    if labelled:
        return re.sub(r"\D+", "", labelled.group(1))
    blocked = {re.sub(r"\D+", "", item or "") for item in (rg, cpf)}
    for match in re.finditer(r"(?<![\d-])\d{5}-?\d{3}(?![\d-])", text):
        digits = re.sub(r"\D+", "", match.group(0))
        if len(digits) == 8 and digits not in blocked:
            return digits
    return None


def _extract_rg(text: str) -> str | None:
    labelled = re.search(r"\brg\s*[:\-]?\s*([0-9.\-]{5,14})", text, re.IGNORECASE)
    if labelled:
        return labelled.group(1).strip(" .,;")
    hyphenated = re.search(r"(?<!\d)(\d{5,10}-\d{1,2})(?!\d)", text)
    if hyphenated:
        return hyphenated.group(1).strip(" .,;")
    for token in re.findall(r"(?<!\d)\d{1,2}\.?\d{3}\.?\d{3}-?\d{1,2}(?!\d)", text):
        digits = re.sub(r"\D+", "", token)
        if len(digits) != 11 and ("-" in token or "." in token):
            return token.strip(" .,;")
    return None


def _extract_patient_name(
    texts: list[str],
    *,
    current_message: str,
    previous_assistant_question: str,
) -> tuple[str | None, dict[str, Any]]:
    accepted: tuple[str, str] | None = None
    rejected = False
    for index, text in enumerate(texts):
        explicit = re.search(
            r"\b(?:meu nome (?:e|é)|me chamo|sou|pode (?:me )?chamar de|pode colocar)\s+([^,;.!?\n]+)",
            text,
            re.IGNORECASE,
        )
        if explicit:
            candidate = _trim_patient_name_candidate(explicit.group(1))
            if _is_plausible_patient_name(candidate):
                source = "CURRENT_TURN_EXPLICIT" if index == len(texts) - 1 else "HISTORICAL_EXPLICIT"
                accepted = (_title_preserving_patient_text(candidate), source)
            else:
                rejected = True

    current = texts[-1] if texts else current_message
    if _previous_question_requests_name(previous_assistant_question):
        candidate = _first_registration_candidate(current)
        if _is_plausible_patient_name(candidate):
            accepted = (_title_preserving_patient_text(candidate), "ACTIVE_NAME_QUESTION")
        elif candidate:
            rejected = True

    if accepted is None and _previous_question_requests_registration(previous_assistant_question):
        candidate = _first_registration_candidate(current)
        if _registration_anchor_in_same_text(current) and _is_plausible_patient_name(candidate):
            accepted = (_title_preserving_patient_text(candidate), "ACTIVE_REGISTRATION_REQUEST")
        elif candidate:
            rejected = True

    if accepted is None:
        for text in reversed(texts):
            if not _registration_anchor_in_same_text(text):
                continue
            candidate = _first_registration_candidate(text)
            if _is_plausible_patient_name(candidate):
                accepted = (_title_preserving_patient_text(candidate), "HISTORICAL_REGISTRATION_BLOCK")
                break
            if candidate:
                rejected = True

    if accepted:
        return accepted[0], {"status": "ACCEPTED", "source": accepted[1], "reason": "STRONG_SEMANTIC_EVIDENCE"}
    return None, {
        "status": "REJECTED" if rejected or any(_looks_like_weak_name_candidate(item) for item in texts) else "ABSENT",
        "source": "NONE",
        "reason": "AMBIGUOUS_OR_NON_NAME_TEXT" if rejected or texts else "NO_CANDIDATE",
    }


def _trim_patient_name_candidate(value: str) -> str:
    words = re.findall(r"[A-Za-zÀ-ÿ]+", str(value or ""))
    stop_words = {"e", "quero", "gostaria", "preciso", "tenho", "para", "porque", "sobre", "mas"}
    trimmed: list[str] = []
    for word in words:
        if _normalize(word) in stop_words:
            break
        trimmed.append(word)
        if len(trimmed) == 5:
            break
    return " ".join(trimmed)


def _first_registration_candidate(text: str) -> str:
    first = re.split(r"[,;\n]", str(text or ""), maxsplit=1)[0]
    if "@" in first or re.search(r"\d", first):
        return ""
    return _trim_patient_name_candidate(first)


def _registration_anchor_in_same_text(text: str) -> bool:
    return bool(
        re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.IGNORECASE)
        or re.search(r"\b(?:cpf|rg|cep|endereco|endereço|rua|avenida|av\.?|travessa)\b|\d{5,}", text, re.IGNORECASE)
    )


def _previous_question_requests_name(text: str) -> bool:
    normalized = _normalize(text)
    return any(phrase in normalized for phrase in ("qual seu nome", "qual e seu nome", "qual é seu nome", "nome completo", "como voce se chama", "como você se chama"))


def _previous_question_requests_registration(text: str) -> bool:
    normalized = _normalize(text)
    return any(term in normalized for term in ("cadastro", "cpf", "rg", "cep", "e-mail", "email", "endereco", "endereço"))


def _looks_like_weak_name_candidate(text: str) -> bool:
    words = re.findall(r"[A-Za-zÀ-ÿ]+", str(text or ""))
    return 1 <= len(words) <= 6


def _is_plausible_patient_name(candidate: str) -> bool:
    words = re.findall(r"[A-Za-zÀ-ÿ]+", str(candidate or ""))
    if not 1 <= len(words) <= 5:
        return False
    normalized_words = {_normalize(word) for word in words}
    blocked = {
        "dente", "dentes", "cima", "baixo", "frente", "lado", "esquerdo", "direito", "boca", "rosto", "testa",
        "implante", "implantes", "dentario", "dentária", "protese", "prótese", "lente", "lentes", "botox", "procedimento",
        "dor", "sangramento", "inchaco", "inchaço", "medo", "pituba", "matatu", "brotas", "rua", "avenida", "bairro",
        "hoje", "amanha", "amanhã", "segunda", "terca", "terça", "quarta", "quinta", "sexta", "sabado", "sábado", "domingo",
        "manha", "manhã", "tarde", "noite", "horario", "horário", "avaliacao", "avaliação", "consulta", "cadastro",
        "quero", "gostaria", "preciso", "obrigado", "obrigada", "sim", "nao", "não", "homem", "mulher", "atendido", "atendida",
    }
    return not bool(normalized_words & blocked)


def _extract_address(texts: list[str], existing: dict[str, str]) -> dict[str, str]:
    memory: dict[str, str] = {}
    joined = " ".join(texts)
    street_match = re.search(r"\b(?:endereco|endereço|logradouro|rua|avenida|av\.?|travessa)\s*[:\-]?\s+([A-Za-zÀ-ÿ0-9 ]{2,80})", joined, re.IGNORECASE)
    if street_match:
        street = street_match.group(0)
        street = re.split(r"[,;\n]", street, maxsplit=1)[0]
        number = re.search(r"\b(\d+[A-Za-z]?)\s*$", street)
        if number:
            memory["address_number"] = number.group(1)
            street = street[: number.start()].strip()
        memory["address_street"] = _title_preserving_patient_text(street)
    current_parts = [part.strip() for part in re.split(r"[,;\n]", texts[-1]) if part.strip()]
    if existing.get("address_street") or memory.get("address_street"):
        if current_parts and re.fullmatch(r"\d+[A-Za-z]?", current_parts[0]):
            memory["address_number"] = current_parts[0]
            if len(current_parts) > 1:
                memory["address_neighborhood"] = _title_preserving_patient_text(current_parts[1])
            if len(current_parts) > 2:
                memory["address_city"] = _title_preserving_patient_text(current_parts[2])
            if len(current_parts) > 3:
                memory["address_state"] = _title_preserving_patient_text(current_parts[3])
    return memory


def _missing_required_registration_fields(registration_memory: dict[str, str]) -> tuple[str, ...]:
    required = (
        "patient_name",
        "email",
        "cpf",
        "rg",
        "cep",
        "address_street",
        "address_number",
        "address_neighborhood",
        "address_city",
        "address_state",
    )
    return tuple(field for field in required if field not in registration_memory)


def _title_preserving_patient_text(value: str) -> str:
    return " ".join(part.capitalize() for part in str(value).strip().split())


def _appointment_intent_detected(text: str, *, current_message: str, previous_assistant_question: str) -> bool:
    current = _normalize(current_message)
    previous = _normalize(previous_assistant_question)
    explicit = ("quero marcar", "quero agendar", "pode agendar", "pode marcar", "vamos marcar", "vamos agendar", "marcar horario", "agendar horario", "solicitar horario", "quero uma avaliacao", "quero uma avaliação", "qual horario voces tem", "qual horário vocês têm")
    if any(term in current for term in explicit):
        return True
    if any(term in current for term in ("marcar", "agendar")) and any(term in current for term in ("horario", "avaliacao", "consulta")):
        return True
    affirmative = current in {"sim", "quero", "vamos", "pode", "claro", "quero sim", "pode sim", "vamos sim"}
    appointment_cta = _previous_question_is_appointment_cta(previous)
    return bool(affirmative and appointment_cta)


def _resolve_appointment_intent(
    current: str,
    *,
    previous_assistant_question: str,
    historical_appointment_intent: bool,
    scheduling_context_active: bool,
    scheduling_status: str | None,
    registration_data_present: bool,
) -> dict[str, Any]:
    if _appointment_intent_detected(current, current_message=current, previous_assistant_question=""):
        return {"active": True, "source": "CURRENT_TURN_EXPLICIT", "reason": "CURRENT_TURN_SCHEDULING_EVIDENCE"}
    if _appointment_intent_detected(current, current_message=current, previous_assistant_question=previous_assistant_question):
        return {"active": True, "source": "ACTIVE_APPOINTMENT_CTA", "reason": "SEMANTICALLY_COMPATIBLE_AFFIRMATION"}
    current_has_scheduling_data = bool(_preferred_date(current) or _preferred_time(current))
    previous_requests_scheduling_data = any(
        term in _normalize(previous_assistant_question)
        for term in ("qual dia", "qual horario", "qual horário", "qual periodo", "qual período", "qual unidade", "voce prefere", "você prefere")
    )
    status_active = _normalize(str(scheduling_status or "")).upper() in {
        "BOOKING_IN_PROGRESS", "SLOT_AVAILABLE", "CHECKING_AVAILABILITY", "COLLECTING_REQUIRED_DATA", "COLLECTING_SCHEDULING_PREFERENCES"
    }
    if registration_data_present and historical_appointment_intent and _previous_question_requests_registration(previous_assistant_question):
        return {"active": True, "source": "ACTIVE_SCHEDULING_CONTEXT", "reason": "CURRENT_REGISTRATION_DATA_COMPATIBLE_WITH_SCHEDULING"}
    if current_has_scheduling_data and (historical_appointment_intent or scheduling_context_active or status_active or previous_requests_scheduling_data):
        return {"active": True, "source": "ACTIVE_SCHEDULING_CONTEXT", "reason": "CURRENT_TURN_COMPATIBLE_WITH_SCHEDULING"}
    return {
        "active": False,
        "source": "NONE_CURRENT_TURN",
        "reason": "PERSISTENT_MEMORY_SUPPRESSED" if historical_appointment_intent else "NO_SCHEDULING_EVIDENCE",
    }


def _normalized_phone(value: str | None) -> str | None:
    digits = re.sub(r"\D+", "", value or "")
    if len(digits) < 8:
        return None
    return digits[:15]


def _preferred_date(text: str) -> str | None:
    if _contains_term(text, "amanha") or _contains_term(text, "amanhã"):
        return "amanha"
    if _contains_term(text, "hoje"):
        return "hoje"
    for day in ("segunda", "terca", "terça", "quarta", "quinta", "sexta", "sabado", "sábado", "domingo"):
        if _contains_term(text, day):
            return _normalize(day)
    return None


def _preferred_time(text: str) -> str | None:
    match = re.search(r"\b([01]?\d|2[0-3])\s*(?::|h)\s*([0-5]\d)?\b", text)
    if match:
        return f"{int(match.group(1)):02d}:{match.group(2) or '00'}"
    match = re.search(r"\b(?:as|às|a)\s+([01]?\d|2[0-3])\b", text)
    if match:
        return f"{int(match.group(1)):02d}:00"
    return None


def _correction_state(inbound_texts: list[str], *, current_message: str) -> dict[str, Any]:
    current = _normalize(current_message)
    all_text = _normalize(" ".join(inbound_texts))
    state: dict[str, Any] = {"acknowledge_once": False}
    masculine_current = any(term in current for term in ("ser atendido", "sou homem", "nao sou mulher", "não sou mulher", "quem disse que sou mulher"))
    feminine_current = any(term in current for term in ("ser atendida", "sou mulher", "nao sou homem", "não sou homem", "quem disse que sou homem"))
    masculine_history = any(term in all_text for term in ("ser atendido", "sou homem", "nao sou mulher", "não sou mulher", "quem disse que sou mulher"))
    feminine_history = any(term in all_text for term in ("ser atendida", "sou mulher", "nao sou homem", "não sou homem", "quem disse que sou homem"))
    if masculine_current:
        state.update({"treatment_preference": "masculine", "acknowledge_once": True})
    elif masculine_history:
        state["treatment_preference"] = "masculine"
    if feminine_current and not masculine_current:
        state.update({"treatment_preference": "feminine", "acknowledge_once": True})
    elif feminine_history and not masculine_history:
        state["treatment_preference"] = "feminine"
    return state


def _scheduling_state(
    operational_memory: dict[str, str],
    *,
    scheduling_context_active: bool,
    scheduling_status: str | None,
    appointment_intent_active: bool,
) -> str:
    status = _normalize(str(scheduling_status or "")).upper()
    if status == "BOOKED":
        return "BOOKED"
    if appointment_intent_active and status in {"BOOKING_IN_PROGRESS", "SLOT_AVAILABLE", "CHECKING_AVAILABILITY", "COLLECTING_REQUIRED_DATA"}:
        return status
    if operational_memory.get("appointment_intent") and operational_memory.get("preferred_date") and operational_memory.get("preferred_time"):
        return "CHECKING_AVAILABILITY" if scheduling_context_active else "APPOINTMENT_INTENT"
    if operational_memory.get("preferred_date") and operational_memory.get("preferred_time"):
        return "CHECKING_AVAILABILITY" if scheduling_context_active else "APPOINTMENT_INTENT"
    if operational_memory.get("appointment_intent"):
        return "COLLECTING_REQUIRED_DATA"
    return "NONE"


def _registration_collection_policy(missing: tuple[str, ...]) -> str:
    if len(missing) > 3:
        return "GROUP_MISSING_FIELDS"
    return "ASK_ONLY_MISSING_FIELDS"


def _minimum_discovery_complete(summary: dict[str, str]) -> bool:
    has_interest = "procedure_interest" in summary
    has_complaint = "main_concern" in summary or "region_interest" in summary or "situation" in summary
    has_context = "motivation" in summary or "duration_context" in summary or "main_objection" in summary or "fear_topics" in summary or ("region_interest" in summary and "main_concern" in summary)
    return has_interest and has_complaint and has_context


def _current_turn_intent(
    current: str,
    *,
    current_summary: dict[str, str],
    historical_summary: dict[str, str],
    previous_assistant_question: str,
) -> CurrentTurnIntent:
    if _is_greeting_only(current):
        return CurrentTurnIntent.GREETING
    if _is_acknowledgement_only(current):
        return CurrentTurnIntent.ACKNOWLEDGEMENT
    if _is_identity_query(current):
        return CurrentTurnIntent.IDENTITY_QUERY
    if _is_correction_turn(current):
        return CurrentTurnIntent.CORRECTION
    if _appointment_intent_detected(current, current_message=current, previous_assistant_question=previous_assistant_question):
        return CurrentTurnIntent.SCHEDULING_RESPONSE
    if _looks_like_clinical_safety(current):
        return CurrentTurnIntent.CLINICAL_SAFETY
    current_procedure = current_summary.get("procedure_interest")
    historical_procedure = historical_summary.get("procedure_interest")
    if current_procedure and historical_procedure and current_procedure != historical_procedure:
        return CurrentTurnIntent.TOPIC_CHANGE
    if current_procedure:
        return CurrentTurnIntent.PROCEDURE_INTEREST
    objection = _objection_state(current, previous_assistant_question=previous_assistant_question)
    if objection != ObjectionState.NONE:
        return CurrentTurnIntent.OBJECTION
    if _looks_like_factual_attribute_question(current):
        if any(_contains_term(current, term) for term in ("onde", "horario", "funciona", "unidade", "endereco", "endereço")):
            return CurrentTurnIntent.OPERATIONAL_QUERY
        return CurrentTurnIntent.FACTUAL_QUERY
    if _contextual_short_answer_resolved(current, previous_assistant_question):
        return CurrentTurnIntent.CONVERSATIONAL_RESPONSE
    if _looks_like_patient_description(current):
        return CurrentTurnIntent.DISCOVERY_RESPONSE
    if _is_small_talk(current):
        return CurrentTurnIntent.SMALL_TALK
    return CurrentTurnIntent.OTHER


def _context_continuity(
    current: str,
    *,
    current_turn_intent: CurrentTurnIntent,
    current_summary: dict[str, str],
    historical_summary: dict[str, str],
    previous_assistant_question: str,
    context_age_seconds: int | None,
) -> ContextContinuity:
    if current_turn_intent in {CurrentTurnIntent.IDENTITY_QUERY, CurrentTurnIntent.OPERATIONAL_QUERY} and historical_summary.get("procedure_interest"):
        return ContextContinuity.SIDE_QUERY
    if current_turn_intent in {CurrentTurnIntent.GREETING, CurrentTurnIntent.ACKNOWLEDGEMENT, CurrentTurnIntent.SMALL_TALK}:
        return ContextContinuity.NEW_NEUTRAL_TURN
    if current_turn_intent == CurrentTurnIntent.TOPIC_CHANGE:
        return ContextContinuity.TOPIC_CHANGE
    if current_turn_intent == CurrentTurnIntent.SCHEDULING_RESPONSE:
        return ContextContinuity.STRONG_CONTINUATION
    if _explicit_scheduling_continuation(current):
        return ContextContinuity.STRONG_CONTINUATION
    if _contextual_short_answer_resolved(current, previous_assistant_question):
        return ContextContinuity.STRONG_CONTINUATION
    if current_summary.get("procedure_interest"):
        return ContextContinuity.STRONG_CONTINUATION
    if current_turn_intent == CurrentTurnIntent.FACTUAL_QUERY and historical_summary.get("procedure_interest"):
        return ContextContinuity.WEAK_CONTINUATION
    if _looks_like_patient_description(current) and historical_summary.get("procedure_interest"):
        return ContextContinuity.WEAK_CONTINUATION
    if context_age_seconds is not None and context_age_seconds >= 1800:
        return ContextContinuity.NEW_NEUTRAL_TURN
    return ContextContinuity.NEW_NEUTRAL_TURN


def _active_need_summary(
    *,
    current_summary: dict[str, str],
    historical_summary: dict[str, str],
    context_continuity: ContextContinuity,
) -> dict[str, str]:
    if context_continuity in {ContextContinuity.NEW_NEUTRAL_TURN, ContextContinuity.SIDE_QUERY}:
        return dict(current_summary)
    if context_continuity == ContextContinuity.TOPIC_CHANGE:
        return dict(current_summary)
    summary = dict(historical_summary)
    for key, value in current_summary.items():
        if key == "region_interest" and summary.get(key) and value == "rosto":
            continue
        summary[key] = value
    return summary


def _context_age_seconds(current_message_at: Any | None, previous_assistant_message_at: Any | None) -> int | None:
    current = _parse_timestamp(current_message_at)
    previous = _parse_timestamp(previous_assistant_message_at)
    if current is None or previous is None:
        return None
    return max(int(current - previous), 0)


def _parse_timestamp(value: Any | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text)
        if parsed > 10_000_000_000 or 100_000 <= parsed < 10_000_000:
            return parsed / 1000
        return parsed
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _cta_policy(intent: CurrentTurnIntent, continuity: ContextContinuity, next_action: NextBestAction) -> str:
    if next_action in {NextBestAction.RESPOND_ONLY, NextBestAction.WAIT_FOR_PATIENT, NextBestAction.NO_COMMERCIAL_ADVANCE}:
        return "CTA_SUPPRESSED_CURRENT_TURN"
    if intent in {CurrentTurnIntent.GREETING, CurrentTurnIntent.IDENTITY_QUERY, CurrentTurnIntent.ACKNOWLEDGEMENT, CurrentTurnIntent.SMALL_TALK, CurrentTurnIntent.CORRECTION}:
        return "CTA_SUPPRESSED_CURRENT_TURN"
    if continuity in {ContextContinuity.NEW_NEUTRAL_TURN, ContextContinuity.SIDE_QUERY}:
        return "CTA_SUPPRESSED_CONTEXT_NOT_ACTIVE"
    return "CTA_ALLOWED_WHEN_NATURAL"


def _commercial_pressure_level(intent: CurrentTurnIntent, next_action: NextBestAction) -> CommercialPressureLevel:
    if next_action == NextBestAction.RESPOND_ONLY:
        return CommercialPressureLevel.LOW
    if intent in {CurrentTurnIntent.GREETING, CurrentTurnIntent.IDENTITY_QUERY, CurrentTurnIntent.ACKNOWLEDGEMENT, CurrentTurnIntent.SMALL_TALK}:
        return CommercialPressureLevel.LOW
    if next_action in {NextBestAction.PROPOSE_NEXT_STEP, NextBestAction.SCHEDULE}:
        return CommercialPressureLevel.MEDIUM
    return CommercialPressureLevel.LOW


def _is_greeting_only(text: str) -> bool:
    stripped = text.strip(" .,!?:;")
    if not stripped:
        return False
    greeting_terms = {"oi", "ola", "olá", "bom dia", "boa tarde", "boa noite", "opa", "e ai", "e aí"}
    return stripped in {_normalize(item) for item in greeting_terms} or (stripped in {"tudo bem", "boa"} and len(stripped.split()) <= 2)


def _is_acknowledgement_only(text: str) -> bool:
    stripped = text.strip(" .,!?:;")
    return stripped in {"obrigado", "obrigada", "valeu", "agradeco", "agradeço", "ta bom", "tá bom", "ok", "certo", "beleza"}


def _is_identity_query(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "qual seu nome",
            "qual e seu nome",
            "qual é seu nome",
            "como voce se chama",
            "como você se chama",
            "quem e voce",
            "quem é você",
            "quem esta falando",
            "quem está falando",
        )
    )


def _is_correction_turn(text: str) -> bool:
    return any(term in text for term in ("corrigindo", "na verdade", "quis dizer", "corrigir", "correcao", "correção", "quem disse que"))


def _is_small_talk(text: str) -> bool:
    return text in {"tudo bem", "como vai", "boa", "beleza"} or any(_contains_term(text, term) for term in ("bom trabalho", "legal", "show"))


def _looks_like_clinical_safety(text: str) -> bool:
    return any(_contains_term(text, term) for term in ("dor intensa", "sangramento", "sangrando", "inchado", "inchada", "trauma"))


def _looks_like_patient_description(text: str) -> bool:
    description_terms = (
        "testa",
        "sobrancelha",
        "sobrancelhas",
        "olhos",
        "rosto",
        "linha",
        "linhas",
        "marca",
        "marcas",
        "marcado",
        "marcadas",
        "visivel",
        "visiveis",
        "repouso",
        "movimenta",
        "incomoda",
        "incomodo",
        "sim",
        "nao",
        "não",
        "quero",
        "pesquisando",
        "breve",
        "anos",
        "meses",
        "dente",
        "perdi",
        "implante",
        "protese",
        "prótese",
        "medo",
        "cansaco",
        "cansaço",
        "cansado",
        "cansada",
    )
    tokens = set(re.findall(r"[a-z0-9]+", _normalize(text)))
    return bool(tokens & set(description_terms))


def _explicit_scheduling_continuation(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "pode marcar",
            "pode agendar",
            "quero marcar",
            "quero agendar",
            "marca para",
            "agendar para",
            "marcar para",
        )
    )


def _previous_question_is_appointment_cta(previous_assistant_question: str) -> bool:
    previous = _normalize(previous_assistant_question)
    if not previous:
        return False
    return any(
        phrase in previous
        for phrase in (
            "quer que eu veja um horario",
            "quer agendar",
            "quer marcar",
            "horario para sua avaliacao",
            "horario para avaliacao",
            "solicitar horario",
            "encaminhe para confirmar um horario",
            "encaminhar para confirmar um horario",
        )
    )


def _estimate_discovery_question_count(inbound_texts: list[str], previous_assistant_question: str) -> int:
    count = max(len(inbound_texts) - 1, 0)
    if "?" in previous_assistant_question:
        count += 1
    return count


def _conversation_fatigue(inbound_texts: list[str], discovery_question_count: int, *, discovery_depth: int = 0) -> ConversationFatigue:
    recent = [_normalize(text) for text in inbound_texts[-3:]]
    short_recent = [text for text in recent if text and len(text.split()) <= 4]
    if discovery_depth >= 3 and discovery_question_count <= 4:
        return ConversationFatigue.MEDIUM
    if discovery_question_count >= 5 or len(short_recent) >= 3:
        return ConversationFatigue.HIGH
    if discovery_question_count >= 3 or len(short_recent) >= 2:
        return ConversationFatigue.MEDIUM
    return ConversationFatigue.LOW


def _objection_state(text: str, *, previous_assistant_question: str = "", patient_has_fear_context: bool = False) -> ObjectionState:
    previous = _normalize(previous_assistant_question)
    if any(term in text for term in ("caro", "cara", "preco alto", "valor alto")) and not _looks_like_factual_attribute_question(text):
        return ObjectionState.PRICE
    if any(term in text for term in ("medo", "receio", "artificial", "travado", "risco")) and not _looks_like_factual_attribute_question(text):
        return ObjectionState.FEAR_OR_RISK
    if text in {"os dois", "ambos", "as duas", "sim", "isso", "exatamente"} and patient_has_fear_context and _previous_question_mentions_fear(previous_assistant_question):
        return ObjectionState.FEAR_OR_RISK
    if any(term in text for term in ("confiar", "confio", "seguro", "segura")) and not _looks_like_factual_attribute_question(text):
        return ObjectionState.TRUST
    if any(term in text for term in ("depois", "mais tarde", "sem tempo", "pensar")) and not _looks_like_factual_attribute_question(text):
        return ObjectionState.TIMING
    return ObjectionState.NONE


def _previous_question_mentions_fear(previous_assistant_question: str) -> bool:
    previous = _normalize(previous_assistant_question)
    return any(term in previous for term in ("medo", "receio", "risco", "inseguranca", "insegurança", "nervoso", "nervosa", "ansioso", "ansiosa"))


def _patient_has_fear_context(text: str) -> bool:
    return any(_contains_term(text, term) for term in ("medo", "receio", "nervoso", "nervosa", "ansioso", "ansiosa", "inseguro", "insegura"))


def _contextual_short_answer_resolved(text: str, previous_assistant_question: str) -> bool:
    current = _normalize(text)
    previous = _normalize(previous_assistant_question)
    if not previous or "?" not in previous_assistant_question:
        return False
    return current in {"sim", "nao", "não", "isso", "exatamente", "os dois", "ambos", "as duas", "tudo isso"}


def _appointment_readiness(text: str, minimum_complete: bool) -> AppointmentReadiness:
    if any(term in text for term in ("marcar", "agendar", "horario")):
        return AppointmentReadiness.HIGH
    if minimum_complete:
        return AppointmentReadiness.MEDIUM
    return AppointmentReadiness.LOW


def _patient_engagement(inbound_texts: list[str]) -> PatientEngagement:
    if not inbound_texts:
        return PatientEngagement.LOW
    average_words = sum(len(_normalize(text).split()) for text in inbound_texts) / len(inbound_texts)
    if average_words >= 8:
        return PatientEngagement.HIGH
    if average_words >= 3:
        return PatientEngagement.MEDIUM
    return PatientEngagement.LOW


def _looks_like_factual_attribute_question(text: str) -> bool:
    question_terms = ("quanto", "preco", "valor", "custa", "marca", "fabricante", "laboratorio", "duracao", "dura", "agenda", "horario")
    return "?" in text or any(_contains_term(text, term) for term in question_terms)


def _first_match(text: str, options: dict[str, tuple[str, ...]]) -> str | None:
    for label, terms in options.items():
        if any(_contains_term(text, term) for term in terms):
            return label
    return None


def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(_normalize(term))}(?![a-z0-9])", text) is not None


def _normalize(value: str) -> str:
    replacements = str.maketrans({"é": "e", "É": "e", "ã": "a", "Ã": "a", "ç": "c", "Ç": "c", "á": "a", "Á": "a", "í": "i", "Í": "i", "ó": "o", "Ó": "o", "ú": "u", "Ú": "u", "ê": "e", "Ê": "e", "ô": "o", "Ô": "o"})
    return " ".join(str(value).translate(replacements).lower().split())


def _has_identity(config: OrganizationCommercialConfig) -> bool:
    return bool(config.assistant_name or config.assistant_role or config.clinic_name)


def _configured_identity(config: OrganizationCommercialConfig) -> str:
    parts = [item for item in (config.assistant_name, config.assistant_role, config.clinic_name) if item]
    return ", ".join(parts)


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
