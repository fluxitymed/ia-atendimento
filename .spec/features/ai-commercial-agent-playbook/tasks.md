# Tasks: AI Commercial Agent Playbook

> feature: ai-commercial-agent-playbook

## T-056 — Especificar playbook comercial central [concluida]

- Refs: US-074, US-075, US-076, US-077, US-078, US-079, US-080, US-081, AC-254, AC-255, AC-256, AC-257, AC-258, AC-259, AC-260, AC-261, AC-262, AC-263, AC-264, AC-265, AC-266, AC-267, AC-268, AC-269, AC-270, AC-271, AC-272
- Arquivos: .spec/features/ai-commercial-agent-playbook/spec.md, .spec/features/ai-commercial-agent-playbook/tasks.md
- Notas: Registrar separacao entre metodo comercial global e fatos autorizados da organizacao.

## T-057 — Implementar estado e politica comercial reutilizavel [concluida]
- Refs: US-074, US-075, US-076, US-078, US-079, US-080, AC-254, AC-255, AC-256, AC-257, AC-258, AC-259, AC-260, AC-264, AC-265, AC-266, AC-267, AC-268, AC-269, AC-270
- Arquivos: src/ai_agent_runtime/commercial/__init__.py, src/ai_agent_runtime/commercial/playbook.py, src/ai_agent_runtime/graph.py, src/ai_agent_runtime/state.py, test/ai-commercial-agent-playbook/commercial-playbook.test.js
- Notas: Criar estado estruturado, regra de minimum discovery, controle de perguntas, fadiga, objecoes e next best action sem hardcode por clinica.

## T-058 — Compor prompt comercial central com configuracao da organizacao [concluida]
- Refs: US-077, US-081, AC-261, AC-262, AC-263, AC-271, AC-272
- Arquivos: .env.example, src/ai_agent_runtime/commercial/playbook.py, src/ai_agent_runtime/whatsapp/zapi_server.py, test/ai-commercial-agent-playbook/commercial-prompt.test.js, test/ai-whatsapp-zapi-provider/zapi-runtime.test.js
- Notas: Remover prompt comercial monolitico do Z-API e usar composicao central com safety, playbook, organization config, evidence e conversation state.

## T-059 — Atualizar avaliacao comercial multiturno [concluida]

- Refs: US-076, US-078, US-079, US-080, AC-258, AC-260, AC-264, AC-265, AC-266, AC-267, AC-269, AC-270
- Arquivos: .spec/features/ai-agent-evaluation/spec.md, .spec/features/ai-agent-evaluation/tasks.md, src/ai_agent_runtime/evaluation/cases.py, src/ai_agent_runtime/evaluation/dataset.py, src/ai_agent_runtime/evaluation/metrics.py, src/ai_agent_runtime/evaluation/runner.py, test/ai-agent-evaluation/evaluation.test.js
- Notas: Adicionar metricas e cenarios live-like para introducao, eficiencia de descoberta, fadiga, objecoes, CTA, excesso de perguntas e recapitulação.

## T-060 — Verificar feature, regressao Z-API e audit ONP [concluida]

- Refs: US-074, US-081, AC-254, AC-272
- Arquivos: .spec/verification/ai-commercial-agent-playbook.json, .spec/verification/ai-whatsapp-zapi-provider.json, .spec/verification/ai-agent-evaluation.json
- Notas: Rodar suite completa, py_compile, verify das features alteradas e audit ONP final limpo.

## T-061 — Adicionar regras globais de lacuna, memoria operacional e naturalidade [concluida]

- Refs: US-089, AC-318, AC-319, AC-320, AC-321, AC-322, AC-323, AC-324, AC-325, AC-326, AC-327, AC-328, AC-329
- Arquivos: .spec/features/ai-commercial-agent-playbook/spec.md, .spec/features/ai-commercial-agent-playbook/tasks.md, src/ai_agent_runtime/commercial/playbook.py, src/ai_agent_runtime/graph.py, src/ai_agent_runtime/whatsapp/adapter.py, test/ai-commercial-agent-playbook/commercial-playbook.test.js
- Notas: Centralizar politica global sem hardcode de clinica: nao expor lacunas internas, nao forcar decisao tecnica, preservar memoria operacional e impedir confirmacao prematura de agendamento.
