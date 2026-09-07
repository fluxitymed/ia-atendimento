'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

function runPython(source) {
  const result = spawnSync('python3', ['-c', source], {
    cwd: process.cwd(),
    env: { ...process.env, PYTHONPATH: 'src' },
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout.trim();
}

test('@spec:AC-261 @spec:AC-262 @spec:AC-263 organization identity is used only when configured and only on first contact', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook, OrganizationCommercialConfig

playbook = CommercialPlaybook()
configured = OrganizationCommercialConfig(assistant_name="Bruna", assistant_role="da equipe comercial", clinic_name="Clinica Aurora")
first = playbook.evaluate([{"direction": "inbound", "text": "Oi"}], current_message="Oi", organization_config=configured)
first_prompt = playbook.prompt_sections(first, organization_config=configured)
second = playbook.evaluate(
    [{"direction": "inbound", "text": "Oi"}, {"direction": "inbound", "text": "Quero botox"}],
    current_message="Quero botox",
    organization_config=configured,
)
second_prompt = playbook.prompt_sections(second, organization_config=configured)
blank = playbook.evaluate([{"direction": "inbound", "text": "Oi"}], current_message="Oi")
blank_prompt = playbook.prompt_sections(blank)
print(json.dumps({
  "firstPrompt": first_prompt,
  "secondPrompt": second_prompt,
  "blankPrompt": blank_prompt,
  "firstIntroduce": first.should_introduce,
  "secondIntroduce": second.should_introduce,
}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.firstIntroduce, true);
  assert.match(parsed.firstPrompt, /Bruna, da equipe comercial, Clinica Aurora/);
  assert.equal(parsed.secondIntroduce, false);
  assert.match(parsed.secondPrompt, /Nao repita apresentacao inicial/);
  assert.doesNotMatch(parsed.secondPrompt, /Primeiro contato: apresente-se/);
  assert.match(parsed.blankPrompt, /sem inventar nome, papel ou clinica/);
});

test('@spec:AC-264 @spec:AC-271 prompt composition separates safety, playbook, organization, evidence, and state', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook, OrganizationCommercialConfig

playbook = CommercialPlaybook()
state = playbook.evaluate(
    [
        {"direction": "inbound", "text": "Quero saber mais sobre botox"},
        {"direction": "inbound", "text": "testa"},
        {"direction": "inbound", "text": "marcas em repouso"},
    ],
    current_message="marcas em repouso",
    organization_config=OrganizationCommercialConfig(clinic_name="Clinica Aurora"),
)
prompt = playbook.prompt_sections(state, organization_config=OrganizationCommercialConfig(clinic_name="Clinica Aurora"), authorized_evidence="- Botox")
print(json.dumps({"prompt": prompt, "state": state.as_dict()}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  for (const section of ['BASE SAFETY', 'COMMERCIAL PLAYBOOK', 'ORGANIZATION CONFIGURATION', 'AUTHORIZED EVIDENCE', 'CONVERSATION STATE']) {
    assert.match(parsed.prompt, new RegExp(section));
  }
  assert.match(parsed.prompt, /nao recapitule todo o historico/i);
  assert.match(parsed.prompt, /sales_stage:/);
  assert.match(parsed.prompt, /next_best_action:/);
  assert.equal(parsed.state.should_avoid_recap, true);
});

test('@spec:AC-272 Z-API live prompt uses the same central commercial playbook', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph
from ai_agent_runtime.integrations.config import IntegrationConfig
from ai_agent_runtime.integrations.openai_provider import OpenAIResponsesProvider
from ai_agent_runtime.whatsapp import FakeWhatsAppProvider, InMemoryWhatsAppStore, OrganizationResolver, WhatsAppChannelAdapter, ZApiWhatsAppConfig
from ai_agent_runtime.whatsapp.zapi_server import OpenAIWhatsAppResponseGenerator
from ai_agent_runtime.whatsapp.zapi_webhook import handle_zapi_webhook_post

class BotoxRetrieval:
    def search(self, organization_id, query):
        return [{"id": "chunk-botox", "organization_id": organization_id, "document_version_id": "ver-1", "content": "Botox"}]
    def closed_world_procedure_decision(self, organization_id, query):
        return {"decision": "OFFERED", "procedure": "Botox"}

class CapturingTransport:
    def __init__(self):
        self.payloads = []
    def post_json(self, url, *, headers, payload):
        self.payloads.append(payload)
        return {"id": "resp-1", "status": "completed", "output_text": "Claro. O que mais te incomoda hoje?"}

transport = CapturingTransport()
logs = []
provider = FakeWhatsAppProvider()
adapter = WhatsAppChannelAdapter(
    provider=provider,
    store=InMemoryWhatsAppStore(),
    organization_resolver=OrganizationResolver({"clinic-a": "org-a"}),
    runtime_graph=AgentRuntimeGraph(
        response_generator=OpenAIWhatsAppResponseGenerator(OpenAIResponsesProvider(IntegrationConfig(openai_api_key="test-key"), transport), retrieval=BotoxRetrieval()),
        stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
    ),
    allow_placeholder_ack=False,
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
payload = {"type": "ReceivedCallback", "instanceId": "clinic-a", "messageId": "central-1", "phone": "5571", "momment": "100", "text": {"message": "Quero saber mais sobre botox"}}
response, records = handle_zapi_webhook_post(raw_body=json.dumps(payload).encode(), headers={}, config=ZApiWhatsAppConfig(), adapter=adapter)
prompt = transport.payloads[0]["input"][0]["content"]
commercial_events = [entry["details"] for entry in logs if entry["stage"] == "commercial_state_updated"]
print(json.dumps({"status": response.status_code, "prompt": prompt, "events": commercial_events, "decision": records[0].decision.value}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.status, 200);
  assert.equal(parsed.decision, 'PROCESSED');
  assert.match(parsed.prompt, /COMMERCIAL PLAYBOOK/);
  assert.match(parsed.prompt, /ORGANIZATION CONFIGURATION/);
  assert.match(parsed.prompt, /AUTHORIZED EVIDENCE/);
  assert.match(parsed.prompt, /CONVERSATION STATE/);
  assert.ok(parsed.events.some((event) => event.next_best_action === 'ASK_DISCOVERY'));
});
