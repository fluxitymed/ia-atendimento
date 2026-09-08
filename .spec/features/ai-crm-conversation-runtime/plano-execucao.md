# Plano de execução — ai-crm-conversation-runtime

> gerado por `onp-spec plano` em 2026-09-08 01:02 — NÃO edite à mão;
> mudou tasks.md ou a config? Regenere: `onp-spec plano ai-crm-conversation-runtime --sequencial --modelo gpt-5.6-terra --esforco high`

## Resumo — o que vai acontecer

- **modo SEQUENCIAL (escolha do usuário)**: 5 tarefa(s) pendente(s), UMA APÓS A OUTRA, na árvore principal
- sem worktrees e sem paralelismo — cada tarefa roda numa janela de contexto limpa, na ordem do tasks.md
- **custo travado pelo usuário**: modelo `gpt-5.6-terra` · esforço `high` em TODAS as tarefas (vence tasks.md e config)
- tudo acontece na branch de trabalho `spec/ai-crm-conversation-runtime`; levar para a main é decisão sua

### Avisos

- ⚠ T-075 está [em-andamento] — entrou no plano; se já houver trabalho local, commite antes de executar

## Ordem de execução (uma tarefa após a outra)

| tarefa | título | modelo | esforço |
|---|---|---|---|
| T-075 | Especificar contrato CRM e arquitetura | `gpt-5.6-terra` | high |
| T-076 | Criar testes do repositorio CRM | `gpt-5.6-terra` | high |
| T-077 | Implementar repositorio e monitor CRM | `gpt-5.6-terra` | high |
| T-078 | Integrar gate e lifecycle ao adapter Z-API | `gpt-5.6-terra` | high |
| T-079 | Verificar regressoes e fechar gate | `gpt-5.6-terra` | high |

## Gestão de branches e commits

1. branch de trabalho `spec/ai-crm-conversation-runtime` criada do ponto atual (se ainda não existir)
2. as tarefas rodam nela mesma, na ordem — **1 tarefa = 1 commit** (`T-xxx feature: título`), marcada `[concluida]` só com trabalho feito
3. gate final na branch de trabalho: `onp-spec verify ai-crm-conversation-runtime` + `onp-spec audit --ci` — **exit 0 ou não está pronto**

## Como executar

### ▶ Execução — Codex headless (codex exec)

```bash
bash .spec/features/ai-crm-conversation-runtime/executar-tarefas.sh
```

Cada tarefa roda `codex exec` com **janela de contexto limpa**, na árvore principal,
uma após a outra, com `--model` e `model_reasoning_effort` já definidos por tarefa e sandbox `workspace-write`.
Os prompts exatos estão embutidos no script.
Logs: `../onp-worktrees/IA - ATENDIMENTO-ai-crm-conversation-runtime-logs/`.

**Confirmação de custos — antes de executar**: os modelos e esforços por
tarefa estão nas tabelas acima; o agente CONFIRMA com o usuário se estão
dentro da licença/cota dele (modelo forte + esforço alto torra tokens).
Para gastar menos: `onp-spec plano ai-crm-conversation-runtime --modelo gpt-5.6-luna --esforco baixo`
(tudo) ou por tarefa `onp-spec tarefa ai-crm-conversation-runtime T-xxx --modelo <m> --esforco <nível>` — e regenere o plano.

### 📣 Acompanhamento — tabela + resumo no chat (a cada 1 min)

O script roda em **background**: o agente AVISA o usuário antes de iniciar e,
enquanto roda, posta no chat a cada ~1 minuto a **tabela de andamento** (qual
tarefa está rodando, qual não está, o que concluiu/falhou) junto com o
**resumo geral de andamento** (escrito por IA; sem IA, o motor resume). Ao
final, o usuário recebe o resumo completo da execução. A qualquer momento:

```bash
onp-spec resumo ai-crm-conversation-runtime --tabela   # a tabela de andamento
onp-spec resumo ai-crm-conversation-runtime            # o resumo em texto
```

