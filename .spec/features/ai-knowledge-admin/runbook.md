# Operação controlada — conhecimento da clínica

Esta entrega não executa carga Hartmann, não publica fontes reais e não faz deploy.
O ingestor é uma CLI administrativa própria; nunca executar o smoke sandbox para
carregar conhecimento de produção.

## Preparação do operador

Na raiz do repositório:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-admin.txt
export PYTHONPATH="$PWD/src"
umask 077
```

Provisionar pelo mecanismo seguro habitual, **sem colar valores em comandos,
logs ou histórico**:

- `KNOWLEDGE_DATABASE_URL`: DSN PostgreSQL do projeto **da IA**, banco que contém as
  tabelas canônicas. Usar conexão direta ou pool em modo session, TLS em ambiente
  remoto (`sslmode=verify-full` e CA adequada). Conta administrativa autorizada a
  SELECT/INSERT/UPDATE nas quatro tabelas de conhecimento e SELECT/UPDATE na linha
  de `organizations`, e INSERT em `operational_audit_events` para rastrear retiradas. A CLI não cria organizações, grants ou schema.
- `OPENAI_API_KEY`: credencial aprovada para gerar embeddings da organização.
  `OPENAI_EMBEDDING_MODEL` opcional; padrão existente `text-embedding-3-small`.
  O esquema exige 1536 dimensões; modelo incompatível falha e reverte o lote.
- Para smoke apenas: `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` do **mesmo projeto**.
  A API key de serviço é exclusiva do operador, nunca de frontend.

A CLI não carrega `.env` automaticamente, não consulta Vault e não aceita DSN ou
chave como argumento. O UUID é escopo dos dados, não autenticação: o acesso à conta
administrativa continua sendo o controle de autorização. Conferir destino e
organização antes de cada operação. Nenhuma migration nova é necessária; o banco
precisa ter as migrations canônicas de conhecimento e status de organizações.

Primeiro ensaiar num projeto de teste isolado. A validação local desta entrega usa
PostgreSQL/pgvector real e embeddings sintéticos. Compatibilidade com o conteúdo
real será determinada pelo dry-run e revisão humana.

## Fontes

Defina o caminho real, sem alterar os sete nomes entre cargas:

```bash
export HARTMANN_KNOWLEDGE_DIR='/caminho/absoluto/para/os-7-markdowns'
export HARTMANN_REVIEWER='identificador-do-revisor'
export HARTMANN_PUBLISHER='identificador-do-publicador'
mkdir -p .secrets/knowledge-reports
```

O diretório deve conter exatamente os sete `.md` pretendidos, sem outros arquivos
Markdown (não há busca recursiva):

1. `01-clinica-hartmann-institucional.md`
2. `02-procedimentos-e-valores.md`
3. `03-profissionais.md`
4. `04-agendamento-e-fluxo-comercial.md`
5. `05-pagamentos-e-condicoes-comerciais.md`
6. `06-produtos.md`
7. `07-regras-de-seguranca-e-handoff.md`

Cada arquivo deve ser UTF-8, até 512.000 bytes, com headings ATX (`#`, `##`, etc.).
O parser recusa frontmatter, metadados de tenant, links simbólicos, arquivos vazios,
código cercado, imagens e tabelas ambíguas. Não lê organização do texto. A identidade
é `organization_id + nome do arquivo`; **renomear cria outro documento**. Arquivos
legados criados por outra ferramenta não são adotados por semelhança de título.

Cada seção mantém prosa, FAQ, lista, condições e exceções. O contexto ancestral é
herdado; tabelas viram linhas com os cabeçalhos e a prosa integral da seção. Limite
secundário de 6.000 caracteres por unidade; excesso exige subdivisão editorial,
sem truncamento automático. Não colocar exceção em heading irmão da regra; manter
regra e exceção na mesma seção ou no contexto ancestral comum. Revisar relações
entre seções, referências anafóricas, preços e profissionais. O parser não prova
correção clínica nem resolve contradições entre documentos.

Todas as versões são `OPEN_WORLD`. A ausência de resultado não autoriza dizer
que um procedimento não existe. Aprovação de catálogo fechado é outro fluxo.

## A. Dry-run (somente leitura)

```bash
.venv/bin/python -m ai_agent_runtime.admin.ingest_knowledge \
  --organization-id 38002ccb-9edb-4dcb-aacf-76c0b6ca1692 \
  --directory "$HARTMANN_KNOWLEDGE_DIR" --dry-run
```

Não gera embedding nem escreve no banco ou em arquivo. Exibe nomes, hashes,
contagem de chunks, documento/versão atual e ações. Na primeira carga, conferir
`new_document=7`, `unchanged=0`, `new_version=0`. Organização inexistente/inativa
ou estrutura inválida falha fechada. Não seguir enquanto houver erro.

## B. Ingestão sem publicação

Após autorização operacional da carga real:

```bash
.venv/bin/python -m ai_agent_runtime.admin.ingest_knowledge \
  --organization-id 38002ccb-9edb-4dcb-aacf-76c0b6ca1692 \
  --directory "$HARTMANN_KNOWLEDGE_DIR" --ingest \
  > .secrets/knowledge-reports/hartmann-ingested.json
```

Exigir exit 0. O arquivo é um manifesto sem conteúdo ou vetores. Guardá-lo com
acesso restrito, pois contém identificadores operacionais. Não reutilizar relatório
vazio de um comando que falhou. Se a gravação de stdout falhar após commit, repetir
`--ingest` com as mesmas fontes recupera o manifesto sem duplicar versões/embeddings.

Resultado: `REVIEW_REQUIRED`, `processing_valid=false`. O runtime continua servindo
somente versões publicadas anteriores. Repetição idêntica é no-op inclusive para
embeddings. Toda a ingestão é uma transação SQL; falhas não deixam objetos parciais.
Chamadas externas já concluídas podem ter custo mesmo quando SQL faz rollback.

## C. Revisão e validação/aprovação explícita

O revisor deve examinar as fontes originais e, em ferramenta administrativa com
acesso restrito, os chunks correspondentes aos IDs do manifesto. Conferir:
procedimentos/valores, avaliação gratuita e exceção de R$ 200 da Dra. Hartmann,
política de orçamento, profissionais, horários, pagamentos, agendamento e handoff.
Não copiar conteúdo clínico para logs. Resolver dados pessoais ou contradições na
fonte antes de prosseguir. `--validate --actor` é a declaração explícita de revisão
humana e grava a aprovação; não é somente um lint automático.

```bash
.venv/bin/python -m ai_agent_runtime.admin.ingest_knowledge \
  --organization-id 38002ccb-9edb-4dcb-aacf-76c0b6ca1692 \
  --directory "$HARTMANN_KNOWLEDGE_DIR" \
  --manifest .secrets/knowledge-reports/hartmann-ingested.json \
  --validate --actor "$HARTMANN_REVIEWER" \
  > .secrets/knowledge-reports/hartmann-validated.json
```

Compara SHA-256 dos bytes, reconstrução dos chunks, tenant/documento/versão/índice,
contagens e integridade dos vetores. Exige exatamente o conjunto de fontes do
manifesto. Registra `APPROVED`, `processing_valid=true`, `approved_by/approved_at`.
Se qualquer item falha, nenhuma aprovação parcial persiste. Ainda não há publicação.

## D. Publicação explícita

```bash
.venv/bin/python -m ai_agent_runtime.admin.ingest_knowledge \
  --organization-id 38002ccb-9edb-4dcb-aacf-76c0b6ca1692 \
  --manifest .secrets/knowledge-reports/hartmann-validated.json \
  --publish --actor "$HARTMANN_PUBLISHER" \
  > .secrets/knowledge-reports/hartmann-published.json
```

O lote inteiro muda em um commit. Conferência de integridade ocorre novamente,
aprovação é exigida no banco e versões obsoletas são recusadas. Nova versão vira
`PUBLISHED` com publicador e vigência; anterior fica `SUPERSEDED` com fim de vigência
e ligação por `supersedes_version_id`. Retry da mesma publicação mantém datas.
Não editar tabelas por scripts paralelos: o lock de organização coordena escritores
desta CLI, não escritores externos que ignorem o protocolo.

## E. Retrieval smoke (somente leitura)

```bash
.venv/bin/python -m ai_agent_runtime.admin.ingest_knowledge \
  --organization-id 38002ccb-9edb-4dcb-aacf-76c0b6ca1692 \
  --manifest .secrets/knowledge-reports/hartmann-published.json \
  --smoke --query 'avaliação' --query 'pagamentos' --query 'agendamento'
```

Usa `ZApiRuntimeRetrieval` e a API REST real, sem chamar LLM ou enviar mensagem.
Exige ao menos uma evidência para cada consulta; cada resultado deve pertencer ao
tenant e a uma versão exata do manifesto. Verifica no SQL a integridade/estado das
sete versões. O relatório distingue `versions_checked` de `versions_retrieved`:
não afirma ter exercitado todos os chunks nem a qualidade clínica das respostas.
Se a fonte usa outros termos, ajustar as consultas ao conteúdo revisado. O caminho
ativo é lexical; este smoke não mede similaridade vetorial. Consultas acentuadas
agora preservam também a grafia UTF-8; consultas sem acento não garantem encontrar
todas as palavras acentuadas, pois o banco não usa unaccent neste caminho.

## F. Rollback lógico

Para retirar o lote explicitado do runtime, preservando histórico:

```bash
.venv/bin/python -m ai_agent_runtime.admin.ingest_knowledge \
  --organization-id 38002ccb-9edb-4dcb-aacf-76c0b6ca1692 \
  --manifest .secrets/knowledge-reports/hartmann-published.json \
  --deactivate --actor "$HARTMANN_PUBLISHER" \
  > .secrets/knowledge-reports/hartmann-deactivated.json
```

Muda as versões atuais para `INACTIVE` em transação única. Não reativa automaticamente
versões `SUPERSEDED` (estado terminal do domínio). Para restaurar uma edição antiga,
recuperar os arquivos aprovados daquela edição e repetir dry-run → ingest → validate
→ publish. A fonte restaurada recebe nova versão. Durante a retirada, o runtime
pode fazer handoff por ausência de evidência. Usar um manifesto de um documento
para retirar apenas aquele documento; não reaproveitar um lote de sete por engano.

## Atualização futura de somente procedimentos e valores

Preservar o nome da fonte. Trocar `--directory` por:

```bash
--file "$HARTMANN_KNOWLEDGE_DIR/02-procedimentos-e-valores.md"
```

Executar os mesmos modos A–E, usando relatórios novos (`hartmann-pricing-ingested.json`,
`hartmann-pricing-validated.json`, `hartmann-pricing-published.json`) e `--file`
também no validate. No smoke desse manifesto de um documento, consultar somente
termos da fonte, por exemplo `--query 'avaliação'`; resultados de outras fontes
causam falha conservadora. Os outros seis documentos permanecem intactos. Se for
usado o diretório completo, o relatório deve mostrar `new_version=1, unchanged=6`.

## Verificação de desenvolvimento

Instalar PostgreSQL com pgvector; `initdb` e `pg_ctl` no PATH (ou `TEST_PG_BIN`).
Os testes criam clusters descartáveis em diretório privado, sem TCP e sem utilizar
qualquer DATABASE_URL remoto. Em ambiente que executa testes como root, usar conta
local sem privilégios para o initdb. Não há fallback que pula testes de banco.

```bash
export ADMIN_TEST_PYTHON="$PWD/.venv/bin/python"
node --test test/ai-knowledge-admin/admin.test.js
node --test --test-reporter=tap
node .agents/skills/onp-spec-driven/scripts/onp-spec.mjs verify ai-knowledge-admin
node .agents/skills/onp-spec-driven/scripts/onp-spec.mjs audit --ci
git diff --check
```
