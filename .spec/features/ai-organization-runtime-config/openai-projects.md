# OpenAI Projects por organizacao

Esta feature nao cria projetos externos automaticamente.

Para cada cliente:

1. Crie um OpenAI Project separado para o cliente e ambiente correto.
2. Crie uma service account/API key dedicada dentro desse Project.
3. Salve o valor do secret apenas no ambiente seguro do deploy, por exemplo Render.
4. Registre no banco apenas o `credential_ref`, que e o nome da env var onde o secret esta guardado.
5. Use nomes diferentes para prod e sandbox/dev.

Exemplo sem secret:

```text
organization_id=dfdcdff0-6d5f-58cc-9a83-2829820b7f8e
provider=OPENAI
credential_ref=OPENAI_API_KEY_CARVALHO
```

Variaveis novas previstas:

```text
ORGANIZATION_RUNTIME_CONFIG_JSON=
ORGANIZATION_CREDENTIALS_JSON=
ZAPI_INSTANCE_ORGANIZATION_MAP_JSON=
OPENAI_API_KEY_CARVALHO=
ZAPI_INSTANCE_TOKEN_CARVALHO=
```

O fallback legado `OPENAI_API_KEY` continua aceito temporariamente para compatibilidade, com log `organization_credential_legacy_fallback`.

O conhecimento do Carvalho continua vinculado ao mesmo `organizationId`; este cadastro nao duplica documentos, chunks ou dados clinicos.
