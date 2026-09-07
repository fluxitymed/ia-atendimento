# Spec: ai-organization-runtime-config

> feature: ai-organization-runtime-config
> status: em-implementacao

## Contexto

O projeto IA - ATENDIMENTO precisa evoluir de um MVP configurado por variaveis globais para uma arquitetura multi-tenant real. Cada cliente deve operar como uma organizacao independente, com configuracao comercial, credenciais, integracoes e uso/custo isolados por `organizationId`.

O caminho atual do Carvalho MVP em producao deve continuar funcionando. Quando ainda nao houver configuracao ou credencial especifica da organizacao, o runtime pode usar fallback legado controlado, com log seguro, sem aceitar `organizationId` vindo de conteudo do paciente e sem alterar regras comerciais, RAG, grounding, batching, audio, handoff ou scheduling.

Fluxo alvo:

```text
WhatsApp inbound
-> provider/account mapping seguro
-> organizationId
-> OrganizationRuntimeConfig
-> OrganizationCredentialProvider
-> knowledge da organizacao
-> playbook comercial global com configuracao local
-> OpenAI/Providers da organizacao
-> usage/cost por organizacao
```

## Histórias

### US-101 — Configuracao de runtime por organizacao

Como operador multi-tenant, quero carregar a configuracao comercial da IA por `organizationId`, para que cada cliente tenha identidade e objetivo comercial proprios sem duplicar o playbook global.

#### AC-421 — Configuracao ativa e carregada por organizacao

- **Dado** uma organizacao ativa com `OrganizationRuntimeConfig`
- **Quando** o runtime recebe um evento resolvido para esse `organizationId`
- **Então** a IA usa `assistant_name`, `assistant_role`, `clinic_name`, `doctor_name`, `sales_goal`, `primary_conversion_action`, `max_discovery_depth`, `cta_style`, `appointment_flow`, `business_hours`, `locations` e `status` dessa organizacao, registrando `organization_config_loaded`

#### AC-422 — Configuracoes de organizacoes diferentes nao vazam

- **Dado** duas organizacoes ativas com configuracoes diferentes
- **Quando** cada uma executa uma conversa propria
- **Então** cada conversa usa apenas a configuracao do seu `organizationId`, sem reutilizar nome, medico, clinica, localizacao ou objetivo comercial da outra organizacao

#### AC-423 — Fallback legado compativel

- **Dado** uma organizacao sem configuracao especifica cadastrada
- **Quando** o runtime precisa iniciar a conversa
- **Então** ele usa temporariamente a configuracao global atual e registra `organization_config_legacy_fallback`, sem alterar o comportamento do Carvalho MVP

### US-102 — Credenciais por organizacao

Como mantenedor da plataforma, quero resolver credenciais por organizacao e provider, para que uma organizacao nunca use chave, instancia ou conta externa de outra.

#### AC-424 — Credencial resolvida por organizationId e provider

- **Dado** credenciais registradas por `organizationId`, `provider` e `credential_ref`
- **Quando** o runtime pede uma credencial para `OPENAI` ou `ZAPI`
- **Então** o `OrganizationCredentialProvider` retorna apenas a credencial daquela organizacao e registra `organization_credential_resolved` sem logar secrets

#### AC-425 — OpenAI usa credencial da organizacao

- **Dado** uma organizacao com credencial OpenAI propria
- **Quando** o runtime chama o modelo
- **Então** o provider OpenAI e instanciado com a chave da organizacao, nao com uma chave global compartilhada

#### AC-426 — Z-API resolve organizacao por instancia segura

- **Dado** uma instancia/conta Z-API vinculada deterministicamente a uma organizacao
- **Quando** chega um webhook Z-API
- **Então** o `organizationId` vem apenas do mapeamento seguro providerAccountId/instanceId -> organizacao, ignorando qualquer `organizationId` presente no payload do paciente

#### AC-427 — Secrets nao vazam

- **Dado** chaves OpenAI, tokens Z-API ou referencias de credenciais
- **Quando** ha logs, traces, estado de conversa ou erros
- **Então** nenhum secret e persistido ou exibido; apenas nomes de variaveis, providers, referencias seguras e eventos sanitizados podem aparecer

### US-103 — Persistencia multi-tenant

Como operador da plataforma, quero tabelas para organizacoes, configuracoes, integracoes, credenciais e uso, para manter rastreabilidade e permitir novos clientes sem alterar codigo.

#### AC-428 — Migration idempotente cria contratos multi-tenant

- **Dado** um banco Supabase/Postgres com as migrations atuais
- **Quando** a migration desta feature e aplicada uma ou mais vezes
- **Então** existem `organizations`, `organization_ai_configs`, `organization_integrations`, `organization_credentials` e `ai_usage_events` com campos necessarios, sem armazenar API keys em texto claro

#### AC-429 — Carvalho e registrado como organizacao existente

- **Dado** o `organizationId` `dfdcdff0-6d5f-58cc-9a83-2829820b7f8e`
- **Quando** o seed/documentacao operacional desta feature e usado
- **Então** a Clinica Carvalho e Tavares Odontologia Integrada, Dr. Leonardo Carvalho e a assistente Bruna ficam associados a esse mesmo `organizationId`, sem duplicar conhecimento ou criar novos documentos clinicos

### US-104 — Uso e custo por organizacao

Como gestor da plataforma, quero registrar uso de IA por organizacao, para acompanhar custo e auditoria sem afetar a resposta ao paciente.

#### AC-430 — Uso real da OpenAI e registrado por organizacao

- **Dado** uma chamada real ou simulada do provider OpenAI que retorna `usage`
- **Quando** a resposta e recebida com sucesso
- **Então** um evento `ai_usage_events` e registrado com `organization_id`, `conversation_id`, `model`, tokens disponiveis, `provider_request_id` quando existir e `estimated_cost_usd` nulo quando nao calculado

#### AC-431 — Registro de uso e idempotente

- **Dado** dois registros de uso com mesmo provider e `provider_request_id`
- **Quando** ambos sao processados
- **Então** apenas um evento efetivo e gravado para evitar duplicacao de custo

#### AC-432 — Falha ao registrar uso nao duplica resposta

- **Dado** uma resposta OpenAI gerada com sucesso
- **Quando** o registro de uso falha
- **Então** o runtime registra `ai_usage_record_failed`, nao refaz a chamada ao modelo e nao transforma sucesso funcional em nova resposta duplicada

### US-105 — Seguranca e compatibilidade operacional

Como responsavel pelo MVP em producao, quero ativar multi-tenancy sem regredir o canal atual, para manter o Carvalho operando enquanto novos clientes sao preparados.

#### AC-433 — Organizacao desconhecida ou inativa falha de forma segura

- **Dado** um `organizationId` desconhecido ou com status inativo
- **Quando** o runtime tenta carregar configuracao/credenciais
- **Então** a execucao automatica nao usa configuracao de outra organizacao e a falha e controlada sem vazamento de secrets

#### AC-434 — Regras aprovadas continuam intactas

- **Dado** as features existentes de RAG, grounding, WhatsApp, batching, audio, handoff e scheduling
- **Quando** a configuracao multi-tenant e adicionada
- **Então** as regras aprovadas continuam passando sem alterar playbook comercial, regras factuais, politica medica, agenda ou CRM

#### AC-435 — Operacao de OpenAI Project por cliente documentada

- **Dado** um novo cliente a ser cadastrado
- **Quando** a operacao cria o OpenAI Project e service account/API key fora do codigo
- **Então** o projeto registra apenas `credential_ref` e variaveis de ambiente seguras, mantendo prod separado de sandbox/dev e sem automatizar criacao de projetos externos

## Fora de escopo

- Criar ou automatizar OpenAI Projects no painel da OpenAI.
- Implementar CRM.
- Alterar RAG, grounding, politica medica, calendar, batching, audio ou handoff alem da injecao minima de configuracao/credencial.
- Migrar secrets para um vault externo definitivo.
- Calcular preco real de tokens por modelo nesta etapa.
- Duplicar documentos ou conhecimento da organizacao Carvalho.

## Suposições

| ID | Suposição | Status | Resolução |
|---|---|---|---|
| ASM-040 | O Render continuara recebendo secrets por variaveis de ambiente no curto prazo. | confirmada | A feature usa `credential_ref` para apontar para nomes de env vars, sem persistir valor dos secrets. |
| ASM-041 | O MVP Carvalho deve continuar usando fallback global ate o cadastro completo estar disponivel. | confirmada | Backward compatibility e requisito explicito desta feature. |
| ASM-042 | `estimated_cost_usd` pode ser nulo ate haver tabela de precos oficial por modelo. | confirmada | A feature registra tokens reais quando retornados e nao inventa custo. |

## Perguntas em aberto

| ID | Pergunta | Status | Resposta |
|---|---|---|---|
| Q-008 | Qual vault externo definitivo sera usado para secrets em producao multi-cliente? | respondida | Fora do escopo desta etapa; por ora secrets ficam em env vars seguras por `credential_ref`. |
