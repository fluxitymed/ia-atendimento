# Contrato HTTP exato — CRM Backend → IA Knowledge Admin API

Base: **mesmo listener privado** do dispatch de IA (`crm_dispatch.py`, porta 8083
por padrão). Prefixo `/internal/knowledge`. Requisições são feitas **somente pelo
backend CRM**, após autenticar o usuário e exigir membership na organização e papel
administrativo autorizado a gerir conhecimento. Nunca chamar do browser.

## Autenticação e escopo

Header obrigatório em **todas** as rotas:

```http
Authorization: Bearer <CRM_KNOWLEDGE_SERVICE_TOKEN>
```

O segredo tem no mínimo 32 caracteres, é dedicado a knowledge e difere de
`CRM_DISPATCH_SERVICE_TOKEN`. A IA compara em tempo constante. O token de dispatch
não autoriza knowledge. Transportar somente por rede privada com TLS entre CRM e IA;
o listener local permanece em `127.0.0.1` por padrão. O CRM deve guardar o token em
segredo de backend; nunca em frontend, log ou query. Não há CORS liberado.

Todo POST inclui `organizationId` e `correlationId` como UUIDs minúsculos canônicos
no JSON. Todo GET inclui exatamente esses dois na query autenticada. O CRM define
o tenant após verificar a membership; headers de tenant são ignorados. A IA verifica
organização existente/ativa no PostgreSQL e escopa cada leitura/escrita. UUID de
recurso estrangeiro ou inexistente responde 404 indistinguível.

`actor` nas mutações de revisão/publicação/retirada é o UUID canônico do usuário
já autenticado pelo CRM; a IA registra esse identificador, mas o token de serviço
não autentica o usuário individual. A escolha de quem pode aprovar/publicar é do
backend CRM. `correlationId` é novo por tentativa operacional e acompanha logs;
não é chave de idempotência.

## Formato de documento

Um documento por requisição. POST `Content-Type: application/json` UTF-8. O CRM
pode ler um arquivo Markdown UTF-8 e enviar seu texto no campo `content`; a IA não
precisa montar ou ler o filesystem do CRM. Não há multipart nesta versão.

```json
{
  "organizationId": "38002ccb-9edb-4dcb-aacf-76c0b6ca1692",
  "correlationId": "11111111-1111-4111-8111-111111111111",
  "logicalName": "02-procedimentos-e-valores",
  "filename": "02-procedimentos-e-valores.md",
  "content": "# Procedimentos e valores\n...",
  "actor": "22222222-2222-4222-8222-222222222222"
}
```

`actor` é opcional somente em dry-run/ingest. `logicalName` é estável, sem `.md`:
a identidade canônica do documento é o tenant + `logicalName + ".md"`. Para
coincidir com uma carga CLI, usar o stem exato do filename CLI. Alterar logicalName
cria outro documento. `filename` é metadata original e **nunca** determina tenant
ou identidade. Frontmatter e `organization_id` no Markdown são rejeitados; não
influenciam o escopo.

Limites: **1 documento/requisição**, Markdown original **≤512.000 bytes**,
body HTTP **≤1.100.000 bytes**, nome lógico **≤156 caracteres**, filename
**≤163 caracteres** com `.md`, uma unidade semântica **≤6.000 caracteres**.
Esses limites reaproveitam o parser existente; o body maior acomoda escaping JSON.
O parser rejeita arquivo vazio, UTF-8 inválido, symlink não aplicável ao upload,
frontmatter, estruturas ambíguas e unidade gigante. O orçamento de operação é
120s, conferido entre etapas; SQL tem timeout de statement 60s e OpenAI 30s por
embedding. Gateway CRM deve permitir **≥150s** para ingest.

## Endpoints

Todos os sucessos abaixo respondem 200 e `Cache-Control: no-store`.

| Método e caminho | JSON/body ou query | Resposta relevante |
|---|---|---|
| `GET /internal/knowledge/documents` | `?organizationId=<uuid>&correlationId=<uuid>` | `documents[]`: `documentId`, `logicalName`, `title`, `status`, `publishedVersion`, `publishedVersionId`, `pendingVersion`, `pendingVersionId`, `pendingStatus`, `updatedAt`, `lastPublishedAt` |
| `GET /internal/knowledge/documents/{documentId}` | Mesma query | `document` com campos da lista; 404 se estrangeiro/inexistente |
| `GET /internal/knowledge/documents/{documentId}/versions` | Mesma query | `versions[]`: `versionId`, `versionNumber`, `status`, `processingValid`, `filename`, `contentHash`, `chunkCount`, `createdAt`, `approvedAt`, `publishedAt`, `supersedesVersionId` |
| `GET /internal/knowledge/documents/{documentId}/versions/{versionId}/review` | Mesma query | `chunks[]`: `chunkIndex`, `content`, `sectionPath`, `semanticType` daquele tenant/documento/versão. Esta é a única rota que retorna texto para revisão humana. Nunca retorna embeddings. |
| `POST /internal/knowledge/dry-run` | JSON de documento acima | `organizationId`, `correlationId`, `documents[0]` e `summary`; nenhuma escrita ou embedding |
| `POST /internal/knowledge/ingest` | JSON de documento acima | Mesmo formato; `documentId`, `versionId`, `versionNumber`, `chunkCount`, `contentHash`. Nova versão retorna `status=REVIEW_REQUIRED`; fonte inalterada retorna o status já existente (inclusive APPROVED/PUBLISHED). |
| `POST /internal/knowledge/validate` | `organizationId`, `correlationId`, `versionId`, `actor` | `documentId`, `versionId`, `status=APPROVED`; não publica |
| `POST /internal/knowledge/publish` | Mesmos quatro campos | `documentId`, `versionId`, `status=PUBLISHED`; versão anterior SUPERSEDED no mesmo commit |
| `POST /internal/knowledge/smoke` | `organizationId`, `correlationId`, `versionId`, `queries` (1–8 strings de até 120 caracteres) | `passed`, `queriesChecked`, `versionsRetrieved`; sem conteúdo dos hits |
| `POST /internal/knowledge/deactivate` | `organizationId`, `correlationId`, `versionId`, `actor` | `documentId`, `versionId`, `status=INACTIVE`; rollback lógico |

Exemplo de dry-run (campos completos de um documento):

```json
{
  "organizationId": "38002ccb-9edb-4dcb-aacf-76c0b6ca1692",
  "correlationId": "11111111-1111-4111-8111-111111111111",
  "documents": [{
    "filename": "02-procedimentos-e-valores.md",
    "logicalName": "02-procedimentos-e-valores",
    "status": "PUBLISHED",
    "currentVersion": 4,
    "proposedVersion": 5,
    "changed": true,
    "contentHash": "<sha256-hex>",
    "estimatedChunks": 3,
    "documentId": "<uuid>",
    "versionId": "<current-version-uuid>"
  }],
  "summary": {"new_document": 0, "unchanged": 0, "new_version": 1}
}
```

Listagem pode mostrar “Procedimentos e valores · Publicado v4 · Nova v5 em
revisão” usando `publishedVersion=4`, `pendingVersion=5` e
`pendingStatus=REVIEW_REQUIRED`. Timestamps são ISO-8601. Campos de versão
inexistente vêm como `null`. A API não devolve vetor ou segredo.

## Estados, retry e concorrência

`dry-run` mostra impacto mas não reserva versão. `ingest` repetido com mesmo tenant,
logicalName e bytes retorna os mesmos IDs, sem embedding novo. `validate` declara
revisão humana, verifica chunks e índice pelo manifesto gravado na ingestão e
registra aprovação. Versões CLI legadas sem manifesto persistido podem ser
reingestidas via API com os mesmos bytes (sem versão/embedding novos) antes de
validar por HTTP, ou validadas pela própria CLI.

`publish` só aceita a versão mais recente e aprovada; lock na linha da organização
serializa publicadores. Repetir a mesma publicação antes de criar uma versão mais
recente retorna o estado publicado sem mudar a data. Se outra versão for ingerida durante a revisão, validate/publish da
antiga retornam 409 (`STALE_VERSION`). **Não enviar `Idempotency-Key` nesta versão**:
a idempotência é por tenant + logicalName + SHA-256 para ingest, e versionId
para validate/publish. O CRM pode repetir a mesma requisição após timeout e usar
GET versions para reconciliar a resposta. A auditoria registra cada tentativa
bem-sucedida, ainda que idempotente.

`deactivate` desativa a versão atual sem apagar histórico. Uma versão SUPERSEDED
não é ressuscitada; restauração antiga exige nova versão e revisão.

## Erros

JSON de erro é `{ "error": "CODIGO_CONSTANTE", "correlationId": "<uuid-ou-null>" }`.
401 não inclui correlationId. A API não propaga exceções SQL/OpenAI, DSN, payload,
Authorization, token ou conteúdo.

| HTTP | Motivo |
|---|---|
| 400 | JSON/campos/UUID/Markdown inválidos, fonte vazia, ator ausente, estrutura não suportada |
| 401 | Bearer ausente, inválido ou token knowledge não configurado |
| 404 | Organização inexistente/inativa; documento/versão inexistente ou de outro tenant; rota desconhecida |
| 409 | Versão obsoleta, não aprovada ou estado incompatível com publicação/retirada |
| 413 | Body ou Markdown acima do limite |
| 503 | Banco/embedding/retrieval indisponível ou falha inesperada; erro interno ocultado |
| 504 | Orçamento total de 120s excedido entre etapas; transação faz rollback |

Um token autenticado autoriza o serviço CRM a indicar tenants; a IA não recebe a
sessão do usuário. O backend CRM **deve** verificar membership e permissão para
cada operação antes de encaminhar. Sem essa verificação no CRM, o token de serviço
teria alcance global sobre organizações ativas.
