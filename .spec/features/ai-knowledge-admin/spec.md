# Ingestor administrativo de conhecimento

> feature: ai-knowledge-admin
> status: auditada

## Contexto

Ferramenta administrativa Python para o pipeline existente, sem carga Hartmann, deploy ou escrita remota nesta entrega.

## Histórias

### US-117 — Gerir conhecimento com revisão e isolamento

Como administrador, quero ingerir, validar e publicar fontes de uma clínica, para manter conhecimento rastreável e isolado.

#### AC-500 — Ingestão controlada de sete fontes

- **Dado** sete documentos Markdown UTF-8 de uma organização ativa
- **Quando** o administrador ingere o diretório
- **Então** sete documentos e versões REVIEW_REQUIRED são persistidos com chunks e índices coerentes, sem publicar.

#### AC-501 — Idempotência e concorrência

- **Dado** fontes já ingeridas
- **Quando** a ingestão idêntica roda novamente ou concorrentemente
- **Então** não surgem documentos, versões, chunks ou embeddings duplicados, nem novas chamadas de embedding para fontes inalteradas.

#### AC-502 — Atualização individual

- **Dado** sete fontes ingeridas e publicadas
- **Quando** somente uma fonte muda
- **Então** somente ela ganha versão não publicada e a anterior continua elegível.

#### AC-503 — Isolamento de tenants

- **Dado** organizações A e B
- **Quando** ingestão, validação, publicação ou retrieval recebe objetos de outro tenant
- **Então** o acesso falha fechado e B não recupera conteúdo de A.

#### AC-504 — Organização obrigatória e ativa

- **Dado** UUID ausente, inválido, inexistente ou organização inativa
- **Quando** qualquer modo é chamado
- **Então** falha antes de embeddings ou mutações.

#### AC-505 — Ciclo de vida e substituição

- **Dado** versão ingerida ainda não aprovada
- **Quando** o administrador valida e publica explicitamente
- **Então** somente após aprovação e publicação a nova versão entra no runtime e a anterior fica SUPERSEDED na mesma transação.

#### AC-506 — Atomicidade de lote

- **Dado** lote de documentos ou publicações
- **Quando** falha ocorre no meio da operação
- **Então** rollback preserva integralmente o estado anterior no PostgreSQL.

#### AC-507 — Chunking fiel e determinístico

- **Dado** headings, tabelas, preços, acentos, regras e exceções
- **Quando** a mesma fonte é processada duas vezes
- **Então** hashes e chunks são iguais, contextos ancestrais e cabeçalhos são preservados sem separar regras de exceções.

#### AC-508 — Relatório seguro

- **Dado** conteúdo clínico e exceção contendo credenciais
- **Quando** o comando produz relatório ou erro
- **Então** não imprime conteúdo, vetores, chave, credencial Vault, DSN ou mensagem bruta de exceção.

#### AC-509 — Entrada inválida

- **Dado** arquivo vazio, UTF-8 inválido, frontmatter, link simbólico ou unidade excessiva
- **Quando** o comando lê as fontes
- **Então** rejeita de forma controlada sem escrever e nunca usa organização vinda do documento.

#### AC-510 — Dry-run somente leitura

- **Dado** organização ativa com documentos novos, iguais e alterados
- **Quando** dry-run recebe diretório
- **Então** informa organização, fontes, hashes, contagens e ações sem escritas, arquivos de saída ou embeddings.

#### AC-511 — Validação íntegra e revisão explícita

- **Dado** manifesto de ingestão e fontes originais revisadas
- **Quando** validação é solicitada com aprovador
- **Então** compara fontes, chunks, IDs e embeddings, recusa adulteração e registra aprovação vinculada à versão.

#### AC-512 — Smoke e rollback lógico

- **Dado** versões publicadas e manifesto
- **Quando** smoke lê o runtime ou rollback lógico desativa a publicação
- **Então** smoke comprova versões esperadas sem imprimir conteúdo e rollback desativa somente as versões explicitadas, sem apagar histórico.

## Fora de escopo

Carga real, deploy, alterações de schema remoto, catálogo CLOSED_WORLD e aprovação clínica automática.

## Suposições

Nenhuma pendente. Decisões técnicas documentadas no design: identidade pelo nome estável do arquivo, acesso SQL administrativo explícito, OPEN_WORLD, revisão humana obrigatória. Fontes reais não foram fornecidas e sua compatibilidade será verificada pelo dry-run.

## Perguntas em aberto

Nenhuma para implementação. Diretório real, aprovador e credencial administrativa serão fornecidos pelo operador na execução futura, como parâmetros obrigatórios.
