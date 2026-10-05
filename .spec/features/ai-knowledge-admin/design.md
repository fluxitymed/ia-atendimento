# Design — administração de conhecimento

## Contratos inspecionados

`semantic-chunking.js`, `chunking-contract.md`, lifecycle e supersession do domínio;
as migrations canônicas; `IntegrationConfig`, `OpenAIResponsesProvider` e
`ZApiRuntimeRetrieval`. O runtime ativo é lexical; os vetores de 1536 dimensões
continuam sendo produzidos para o índice canônico. Nenhuma tabela alternativa.

## Componentes e escolhas

- CLI própria, sem importar escritores sandbox. Conexão PostgreSQL explícita via
  KNOWLEDGE_DATABASE_URL (conexão direta ou pool em modo session), psycopg parametrizado.
- Nenhuma migration necessária: proveniência/hash original nos metadados existentes
  de chunks e índice; UUID de documento derivado de tenant + nome estável do arquivo.
  Renomear fonte é criar outro documento; não adotar documentos legados por título.
- Todas as fontes são lidas e validadas antes de conectar. Identidade independente
  do diretório absoluto; diretório plano, arquivos .md, ordenação estável.
- SHA-256 dos bytes originais; parser UTF-8 estrito. Headings ATX com contexto
  ancestral; corpo da seção é unidade semântica, preservando listas/FAQ/negações.
  Tabelas viram linhas com cabeçalhos e prosa da seção herdada. Blocos excessivos
  falham pedindo subdivisão editorial; nunca truncar ou cortar por caracteres.
  Frontmatter e estruturas ambíguas não suportadas são recusadas explicitamente.
- Dry-run usa transação READ ONLY e não gera embeddings nem grava relatório local.
- Escritas serializadas por lock da linha da organização (ordem única), conferindo
  status ativo no banco, sem fallback de configuração. Organização inativa falha.
  Lote inteiro em uma transação, inclusive chunks e índice. Embeddings em transação
  priorizam simplicidade/segurança em bases pequenas; falha externa reverte SQL,
  mas custo de chamadas externas já feitas não é reversível.
- Ingestão nova percorre DRAFT → PROCESSING → REVIEW_REQUIRED. processing_valid
  só vira true após reconstrução e revisão explícita no comando validate.
- Manifesto JSON sem conteúdo/vetores permite recuperar/repetir a operação por IDs
  exatos. Validate exige as mesmas fontes e --actor, confere fingerprint do conjunto
  e integridade do índice antes de APPROVED. Publicação exige o manifesto validado,
  revalida o banco e exige a versão mais recente do documento; não publica versões
  obsoletas. A anterior permanece servindo até o commit de publicação do lote.
- Publish grava aprovador/publicador, vigência e supersedes_version_id; anterior
  passa a SUPERSEDED. Retry da mesma publicação é idempotente. Não há endpoint web.
- Rollback lógico explícito desativa o lote atual; não ressuscita SUPERSEDED, que é
  terminal no domínio. Para restaurar conteúdo antigo, ingere-se a fonte antiga
  como nova versão, revisa-se e publica-se pelo mesmo fluxo.
- Rollback registra operador e versões em operational_audit_events na mesma transação.
- Busca lexical preserva variantes UTF-8 originais além das normalizadas: ILIKE
  não remove acentos. O runtime mantém os filtros canônicos de elegibilidade.
- Smoke consulta ZApiRuntimeRetrieval real somente por leitura e exige resultados
  das versões do manifesto, sem revelar trechos. Testes usam o mesmo runtime com
  transporte SQL local sobre dados reais do PostgreSQL, não um banco em memória.
- Credenciais apenas no ambiente. Erros públicos são códigos constantes, jamais
  exceções de fornecedores. Relatórios limitados a UUIDs, nomes de fontes, hashes,
  estados e contagens. Conta SQL é administrativa e não deve ser exposta a clientes;
  seu controle de acesso é requisito operacional, não autenticação via UUID.

## Execução

Sequencial e manual nesta sessão, configuração atual preservada, conforme pedido
expresso de continuar autonomamente. Nenhum executor headless ou agente adicional.
Alterações agrupadas por tarefa, com provas e diff disponíveis para revisão.

## Documentação consultada

[Conexões PostgreSQL Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres)
e [changelog](https://supabase.com/changelog), consultados em 2026-10-05.
