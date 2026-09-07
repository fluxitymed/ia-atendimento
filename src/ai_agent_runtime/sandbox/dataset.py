from __future__ import annotations

from dataclasses import dataclass

from ai_agent_runtime.sandbox_ids import BOREAL_ORG_ID, DATASET_VERSION, LEONARDO_ORG_ID


BRIEFING_IARA_SOURCE_PATH = "/Users/FernandoAndrade/Desktop/IA - TESTES/BRIEFING_IARA_PREENCHIDO_CARVALHO_E_TAVARES.pdf"


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
                source_uri=BRIEFING_IARA_SOURCE_PATH,
                source_label="BRIEFING_IARA_PREENCHIDO_CARVALHO_E_TAVARES.pdf",
                content=(
                    "Fonte: BRIEFING_IARA_PREENCHIDO_CARVALHO_E_TAVARES.pdf.\n"
                    "Profissional: Dr. Leonardo Carvalho, CRO-BA 4123.\n"
                    "Atuacao: implantodontista, protesista e periodontista, com mais de 34 anos de atuacao.\n"
                    "Formacao: mestre em Reabilitacao Oral e especialista em Implantodontia pela Sao Leopoldo Mandic.\n"
                    "Servicos/procedimentos informados: implantes; proteses; endodontia; ortodontia; periodontia; "
                    "cirurgia bucomaxilofacial; estetica dental; dentistica; harmonizacao facial; radiografia panoramica; "
                    "tomografia Cone Beam; odontologia digital.\n"
                    "Observacao de autoridade: o briefing lista servicos, mas nao comprova explicitamente completude de catalogo fechado."
                ),
            ),
            SandboxDocument(
                id="dr-leonardo-commercial-briefing",
                organization_id=LEONARDO_ORG_ID,
                title="Briefing comercial Dr. Leonardo Carvalho",
                source_uri=BRIEFING_IARA_SOURCE_PATH,
                source_label="BRIEFING_IARA_PREENCHIDO_CARVALHO_E_TAVARES.pdf",
                content=(
                    "Fonte: BRIEFING_IARA_PREENCHIDO_CARVALHO_E_TAVARES.pdf.\n"
                    "Organizacao: Clinica Carvalho e Tavares Odontologia Integrada.\n"
                    "Local 1: Clinica Carvalho, Rua Dr. Otaviano Pimenta, 41, Matatu/Brotas, Salvador/BA, CEP 40255-380.\n"
                    "Local 2: Clinica Tavares, Hospital da Bahia, Bloco A, 4 andar, sala 4020, "
                    "Av. Prof. Magalhaes Neto, 1541, Pituba, Salvador/BA, CEP 41810-011.\n"
                    "Horario de atendimento: segunda a sexta, 8h as 19h; sabado, 8h as 12h.\n"
                    "Software operacional: Clinicorp.\n"
                    "Atendimento: presencial, com avaliacao inicial.\n"
                    "Tempo medio informado: 30 a 46 minutos.\n"
                    "Agenda: ha horarios reservados para novos pacientes; encaixes apenas mediante autorizacao do Dr. Leonardo.\n"
                    "Para agendar, coletar nome completo, WhatsApp, e-mail, CPF, RG, CEP e endereco.\n"
                    "Cancelamento permitido a qualquer momento. Recomenda-se 2 dias de antecedencia para remarcacao. "
                    "Nao ha cobranca por falta. Tolerancia de atraso: 30 minutos. Excecoes sao decididas pelo Dr. Leonardo.\n"
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
                source_uri=BRIEFING_IARA_SOURCE_PATH,
                source_label="BRIEFING_IARA_PREENCHIDO_CARVALHO_E_TAVARES.pdf",
                content=(
                    "Fonte: BRIEFING_IARA_PREENCHIDO_CARVALHO_E_TAVARES.pdf.\n"
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
                source_uri=BRIEFING_IARA_SOURCE_PATH,
                source_label="BRIEFING_IARA_PREENCHIDO_CARVALHO_E_TAVARES.pdf",
                content=(
                    "Fonte: BRIEFING_IARA_PREENCHIDO_CARVALHO_E_TAVARES.pdf.\n"
                    "A assistente nao diagnostica, nao interpreta sintomas ou exames, nao sugere tratamento e nao antecipa resultado.\n"
                    "Assuntos para handoff: dor intensa, sangramento, inchaco, trauma, dente quebrado, intercorrencia pos-procedimento, "
                    "medicacao, reclamacoes, desconto especial, excecao de agenda, orcamento complexo, solicitacao direta do dentista "
                    "e duvidas clinicas sensiveis de implante ou protese.\n"
                    "Urgencia deve ser encaminhada imediatamente ao Dr. Leonardo sem orientacao clinica pela IA.\n"
                    "Contato pessoal do Dr. Leonardo no briefing e dado operacional de handoff e nao deve ser exposto automaticamente."
                ),
            ),
            SandboxDocument(
                id="dr-leonardo-objections",
                organization_id=LEONARDO_ORG_ID,
                title="Objecoes frequentes Dr. Leonardo Carvalho",
                source_uri=BRIEFING_IARA_SOURCE_PATH,
                source_label="BRIEFING_IARA_PREENCHIDO_CARVALHO_E_TAVARES.pdf",
                content=(
                    "Fonte: BRIEFING_IARA_PREENCHIDO_CARVALHO_E_TAVARES.pdf.\n"
                    "Objecoes frequentes registradas: medo, preco, localizacao, estacionamento, convenio, falta de tempo "
                    "e comparacao com concorrentes.\n"
                    "Objecoes devem ser tratadas comercialmente sem inventar fatos e sem orientacao clinica."
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
            "O PDF fisico foi localizado fora do repositorio em /Users/FernandoAndrade/Desktop/IA - TESTES/BRIEFING_IARA_PREENCHIDO_CARVALHO_E_TAVARES.pdf.",
            "O ambiente local nao possui extrator textual PDF instalado; os fatos estruturados vieram do bloco de dados confirmados fornecido junto ao pedido.",
            "A lista de servicos do briefing nao foi tratada como catalogo CLOSED_WORLD por falta de prova explicita de completude.",
            "Avaliacao gratuita e fato autorizado para casos de busca por procedimento na versao 2026-09-02 do briefing.",
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
