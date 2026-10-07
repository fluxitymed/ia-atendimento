# Verificação — dispatch CRM no listener de Production

O entrypoint `python3 -m ai_agent_runtime.whatsapp.zapi_server` atende
`POST /internal/crm/whatsapp-dispatch` no mesmo listener de `/health`, Knowledge
e webhook Z-API. O handler `handle_crm_dispatch` permanece a implementação
única de validação e execução; o listener apenas lê a requisição, exige o
Bearer existente e transmite status/JSON sem cache.

O teste `@spec:AC-532` sobe o entrypoint real e comprova 401 para ausência ou
erro de token, 400 `INVALID_REQUEST` para `{}` autenticado, 404 para path
desconhecido e 401 para Knowledge sem seu token. O teste com HTTP local prova
`SEND_MESSAGE`, `HANDOFF`, `NO_ACTION`, token não configurado, isolamento de
`organizationId` e `correlationId`, além de preservar o webhook Z-API.

Nenhuma credencial real, serviço remoto, Production ou deploy foi usado. O
Start Command permanece `PYTHONPATH=src python3 -m ai_agent_runtime.whatsapp.zapi_server`.
