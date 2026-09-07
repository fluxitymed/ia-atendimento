from __future__ import annotations

from dataclasses import dataclass

from ai_agent_runtime.sandbox_ids import BOREAL_ORG_ID, DATASET_VERSION, LEONARDO_ORG_ID


BRIEFING_DR_LEONARDO_SOURCE_PATH = "/Users/FernandoAndrade/Desktop/IA - TESTES/Briefing_Assistente_Comercial_Dr_Leonardo_Carvalho.pdf"
BRIEFING_DR_LEONARDO_SOURCE_LABEL = "Briefing_Assistente_Comercial_Dr_Leonardo_Carvalho.pdf"


@dataclass(frozen=True)
class SandboxDocument:
    id: str
    organization_id: str
    title: str
    content: str
    document_type: str = "DOCUMENT"
    knowledge_mode: str = "OPEN_WORLD"
    closed_world_completeness_approved: bool = False
    status: str = "PUBLISHED"
    environment: str = "sandbox"
    source_uri: str | None = None
    source_label: str | None = None


@dataclass(frozen=True)
class SandboxOrganization:
    id: str
    name: str
    environment: str = "sandbox"


@dataclass(frozen=True)
class SandboxDataset:
    version: str
    organizations: tuple[SandboxOrganization, ...]
    documents: tuple[SandboxDocument, ...]
    fictitious: bool = False
    source_limitations: tuple[str, ...] = ()


def build_sandbox_dataset() -> SandboxDataset:
    return SandboxDataset(
        version=DATASET_VERSION,
        organizations=(
            SandboxOrganization(id=LEONARDO_ORG_ID, name="Clinica Carvalho e Tavares Odontologia Integrada"),
            SandboxOrganization(id=BOREAL_ORG_ID, name="Clinica Boreal Sandbox"),
        ),
        documents=(
            SandboxDocument(
                id="dr-leonardo-service-catalog",
                organization_id=LEONARDO_ORG_ID,
                title="Catalogo de servicos Dr. Leonardo Carvalho",
                document_type="PROCEDURE_CATALOG",
                knowledge_mode="OPEN_WORLD",
                closed_world_completeness_approved=False,
                source_uri=BRIEFING_DR_LEONARDO_SOURCE_PATH,
                source_label=BRIEFING_DR_LEONARDO_SOURCE_LABEL,
                content=(
                    f"Fonte: {BRIEFING_DR_LEONARDO_SOURCE_LABEL}.\n"
                    "Profissional: Dr. Leonardo Carvalho.\n"
                    "Servicos/procedimentos informados: implantes; proteses; endodontia; ortodontia; periodontia; "
                    "cirurgia bucomaxilofacial; estetica dental; dentistica; lentes de contato dental; clareamento; "
                    "harmonizacao facial; radiografia panoramica; tomografia Cone Beam; odontologia digital.\n"
                    "Observacao de autoridade: o briefing lista servicos, mas nao comprova explicitamente completude de catalogo fechado."
                ),
            ),
            SandboxDocument(
                id="dr-leonardo-commercial-briefing",
                organization_id=LEONARDO_ORG_ID,
                title="Briefing comercial Dr. Leonardo Carvalho",
                source_uri=BRIEFING_DR_LEONARDO_SOURCE_PATH,
                source_label=BRIEFING_DR_LEONARDO_SOURCE_LABEL,
                content=(
                    f"Fonte: {BRIEFING_DR_LEONARDO_SOURCE_LABEL}.\n"
                    "Organizacao: Clinica Carvalho e Tavares Odontologia Integrada.\n"
                    "Assistente comercial: Bruna.\n"
                    "Local 1: Clinica Carvalho, Rua Doutor Otaviano Pimenta, 41, Matatu, Salvador/BA.\n"
                    "Local 2: Clinica Tavares, Av. Prof. Magalhaes Neto, 1541, 4 andar, sala 4022, Bloco A, Pituba, Salvador/BA.\n"
                    "Horario de atendimento: segunda a sexta, 8h as 19h; sabado, 8h as 12h.\n"
                    "Software operacional: Clinicorp.\n"
                    "Agenda: Bruna nao consulta, reserva ou confirma horario especifico. Handoff para agenda deve ocorrer quando for necessario verificar ou confirmar horario especifico no Clinicorp.\n"
                    "Para agendar, coletar nome completo, WhatsApp, e-mail, CPF, RG, CEP e endereco.\n"
                    "Lembretes por WhatsApp com 1 e 3 dias de antecedencia.\n"
                    "Pagamento: PIX, cartao de credito, cartao de debito e boleto. Parcela minima de R$ 500. "
                    "Nao ha deposito antecipado.\n"
                    "Valores dos procedimentos sao informados apos avaliacao.\n"
                    "Avaliacao gratuita: para casos de busca por procedimento, incluindo implante, lentes e outros procedimentos, "
                    "a avaliacao e gratuita. Consulta de avaliacao nesse contexto tambem e gratuita. "
                    "O valor dos procedimentos e informado apos avaliacao, conforme o planejamento de cada caso."
                ),
            ),
            SandboxDocument(
                id="dr-leonardo-differentials",
                organization_id=LEONARDO_ORG_ID,
                title="Diferenciais Dr. Leonardo Carvalho",
                source_uri=BRIEFING_DR_LEONARDO_SOURCE_PATH,
                source_label=BRIEFING_DR_LEONARDO_SOURCE_LABEL,
                content=(
                    f"Fonte: {BRIEFING_DR_LEONARDO_SOURCE_LABEL}.\n"
                    "Diferenciais informados: Implantodontia, Protese, Periodontia, Odontologia digital, Scanner Virtuo, "
                    "reproducao digital de dentes e gengivas, visualizacao 3D, radiografia panoramica, tomografia Cone Beam "
                    "e tratamentos personalizados de reabilitacao oral.\n"
                    "Esses diferenciais podem fundamentar ponte de valor quando relevantes a necessidade do paciente, "
                    "sem prometer resultado, diagnosticar, sugerir tratamento ou despejar todos os diferenciais de uma vez."
                ),
            ),
            SandboxDocument(
                id="dr-leonardo-handoff-policy",
                organization_id=LEONARDO_ORG_ID,
                title="Politica de limites clinicos e handoff Dr. Leonardo Carvalho",
                source_uri=BRIEFING_DR_LEONARDO_SOURCE_PATH,
                source_label=BRIEFING_DR_LEONARDO_SOURCE_LABEL,
                content=(
                    f"Fonte: {BRIEFING_DR_LEONARDO_SOURCE_LABEL}.\n"
                    "A assistente nao diagnostica, nao interpreta sintomas ou exames, nao sugere tratamento e nao antecipa resultado.\n"
                    "Handoff clinico automatico especifico da Clinica Carvalho e Tavares: sangramento apos procedimento ou atendimento recente.\n"
                    "Handoff de agenda: somente quando for necessario verificar ou confirmar horario especifico no Clinicorp.\n"
                    "Nao geram handoff automatico por si so: preco, pagamento, medo, localizacao, comparacao, duvidas rotineiras, pedido generico para falar com dentista ou Dr. Leonardo, e duvidas sobre convenio.\n"
                    "Contato pessoal do Dr. Leonardo, se existir no briefing, e dado operacional de handoff e nao deve ser exposto automaticamente."
                ),
            ),
            SandboxDocument(
                id="dr-leonardo-objections",
                organization_id=LEONARDO_ORG_ID,
                title="Objecoes frequentes Dr. Leonardo Carvalho",
                source_uri=BRIEFING_DR_LEONARDO_SOURCE_PATH,
                source_label=BRIEFING_DR_LEONARDO_SOURCE_LABEL,
                content=(
                    f"Fonte: {BRIEFING_DR_LEONARDO_SOURCE_LABEL}.\n"
                    "Objecoes frequentes registradas: medo, preco, localizacao, estacionamento, convenio, falta de tempo "
                    "e comparacao com concorrentes.\n"
                    "Objecoes devem ser tratadas comercialmente sem inventar fatos e sem orientacao clinica. "
                    "O briefing registra convenio como objecao frequente, mas nao autoriza afirmar aceite ou recusa de convenio."
                ),
            ),
            SandboxDocument(
                id="boreal-prices",
                organization_id=BOREAL_ORG_ID,
                title="Informacoes comerciais Boreal",
                content="Consulta com Dra. Helena Costa: R$ 900.",
            ),
        ),
        source_limitations=(
            "O PDF fisico foi localizado fora do repositorio em /Users/FernandoAndrade/Desktop/IA - TESTES/Briefing_Assistente_Comercial_Dr_Leonardo_Carvalho.pdf.",
            "O ambiente local nao possui extrator textual PDF instalado; os fatos estruturados vieram do bloco de dados confirmados fornecido junto ao pedido de publicacao.",
            "A lista de servicos do briefing nao foi tratada como catalogo CLOSED_WORLD por falta de prova explicita de completude.",
            "Avaliacao gratuita e fato autorizado para casos de busca por procedimento na versao 2026-09-07 do briefing.",
            "A sala Pituba authoritative desta versao e 4022; versoes anteriores com sala 4020 devem ficar superseded/non-current.",
            "Handoff clinico automatico Carvalho fica restrito a sangramento apos procedimento ou atendimento recente.",
        ),
    )


def ingestion_pipeline_gap_report() -> dict[str, str]:
    return {
        "document": "IMPLEMENTED",
        "normalization": "IMPLEMENTED_CONCEPTUAL",
        "chunking": "IMPLEMENTED_DOMAIN",
        "embedding": "IMPLEMENTED_PROVIDER",
        "pgvector": "IMPLEMENTED_MIGRATION",
        "remote_supabase_write": "READY_FOR_LIVE_EXECUTION",
        "live_retrieval": "READY_FOR_LIVE_EXECUTION",
    }
