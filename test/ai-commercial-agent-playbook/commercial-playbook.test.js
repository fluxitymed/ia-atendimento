'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { readFileSync } = require('node:fs');

function runPython(source) {
  const result = spawnSync('python3', ['-c', source], {
    cwd: process.cwd(),
    env: { ...process.env, PYTHONPATH: 'src' },
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout.trim();
}

test('@spec:AC-254 @spec:AC-255 commercial playbook is central and does not authorize organization facts', () => {
  const server = readFileSync('src/ai_agent_runtime/whatsapp/zapi_server.py', 'utf8');
  const playbook = readFileSync('src/ai_agent_runtime/commercial/playbook.py', 'utf8');
  assert.match(playbook, /class CommercialPlaybook/);
  assert.match(playbook, /O playbook comercial nao e fonte factual autorizada/);
  assert.match(server, /CommercialPlaybook|commercialState|prompt_sections/);
  assert.doesNotMatch(playbook, /Clinica Aurora|Aurora|ZApiWhatsApp|zapi/i);
});

test('@spec:AC-256 @spec:AC-257 commercial state exposes structured fields and next best action', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook

state = CommercialPlaybook().evaluate(
    [{"direction": "inbound", "text": "Quero saber mais sobre botox"}],
    current_message="Quero saber mais sobre botox",
)
print(json.dumps(state.as_dict(), sort_keys=True))
`);
  const parsed = JSON.parse(output);
  for (const key of [
    'sales_stage',
    'discovery_question_count',
    'discovery_depth',
    'minimum_discovery_complete',
    'patient_need_summary',
    'patient_engagement',
    'conversation_fatigue',
    'objection_state',
    'appointment_readiness',
    'next_best_action',
  ]) {
    assert.ok(Object.prototype.hasOwnProperty.call(parsed, key), `${key} missing`);
  }
  assert.ok([
    'ASK_DISCOVERY',
    'BUILD_VALUE',
    'PROPOSE_NEXT_STEP',
    'ANSWER_FACTUAL',
    'HANDLE_OBJECTION',
    'SCHEDULE',
    'HUMAN_HANDOFF',
    'RESPOND_ONLY',
    'WAIT_FOR_PATIENT',
    'ANSWER_CURRENT_TURN',
    'NO_COMMERCIAL_ADVANCE',
  ].includes(parsed.next_best_action));
});

test('@spec:AC-258 @spec:AC-259 @spec:AC-269 need sufficiency moves from discovery to value bridge without checklist rigidity', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook

messages = [
    {"direction": "inbound", "text": "Quero saber mais sobre botox"},
    {"direction": "inbound", "text": "Tenho marcas na testa"},
    {"direction": "inbound", "text": "Aparecem com o rosto relaxado e deixam aspecto de cansaco"},
]
state = CommercialPlaybook().evaluate(messages, current_message=messages[-1]["text"])
print(json.dumps(state.as_dict(), sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.minimum_discovery_complete, true);
  assert.equal(parsed.patient_need_summary.procedure_interest, 'Botox');
  assert.equal(parsed.patient_need_summary.region_interest, 'testa');
  assert.equal(parsed.next_best_action, 'BUILD_VALUE');
  assert.equal(parsed.sales_stage, 'VALUE_BRIDGE');
});

test('@spec:AC-260 @spec:AC-265 @spec:AC-266 repeated short answers raise fatigue and stop curiosity questions', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook, OrganizationCommercialConfig

messages = [
    {"direction": "inbound", "text": "Quero saber mais sobre botox"},
    {"direction": "inbound", "text": "testa"},
    {"direction": "inbound", "text": "repouso"},
    {"direction": "inbound", "text": "dois anos"},
    {"direction": "inbound", "text": "cansaco"},
]
state = CommercialPlaybook().evaluate(
    messages,
    current_message=messages[-1]["text"],
    organization_config=OrganizationCommercialConfig(max_discovery_depth=3),
    previous_assistant_question="Isso te incomoda ha quanto tempo?",
)
print(json.dumps(state.as_dict(), sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.conversation_fatigue, 'HIGH');
  assert.equal(parsed.minimum_discovery_complete, true);
  assert.equal(parsed.next_best_action, 'PROPOSE_NEXT_STEP');
  assert.equal(parsed.sales_stage, 'CTA');
});

test('@spec:AC-267 @spec:AC-268 objections are distinct from factual attribute questions', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook

playbook = CommercialPlaybook()
objection = playbook.evaluate([{"direction": "inbound", "text": "Achei caro"}], current_message="Achei caro").as_dict()
fear = playbook.evaluate([{"direction": "inbound", "text": "Tenho medo de ficar artificial"}], current_message="Tenho medo de ficar artificial").as_dict()
price = playbook.evaluate([{"direction": "inbound", "text": "Quanto custa o botox?"}], current_message="Quanto custa o botox?").as_dict()
print(json.dumps({"objection": objection, "fear": fear, "price": price}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.objection.objection_state, 'PRICE');
  assert.equal(parsed.objection.next_best_action, 'HANDLE_OBJECTION');
  assert.equal(parsed.fear.objection_state, 'FEAR_OR_RISK');
  assert.equal(parsed.fear.next_best_action, 'HANDLE_OBJECTION');
  assert.equal(parsed.price.next_best_action, 'ANSWER_FACTUAL');
});

test('@spec:AC-270 runtime commercial state does not authorize calendar availability outside scheduling context', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook

playbook = CommercialPlaybook()
not_active = playbook.evaluate(
    [{"direction": "inbound", "text": "Quero avaliar botox para marcas na testa e aspecto cansado"}],
    current_message="Quero avaliar botox para marcas na testa e aspecto cansado",
    scheduling_context_active=False,
).as_dict()
active = playbook.evaluate(
    [{"direction": "inbound", "text": "Quero marcar um horario"}],
    current_message="Quero marcar um horario",
    scheduling_context_active=True,
).as_dict()
print(json.dumps({"notActive": not_active, "active": active}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.notEqual(parsed.notActive.next_best_action, 'SCHEDULE');
  assert.equal(parsed.notActive.appointment_readiness, 'MEDIUM');
  assert.equal(parsed.active.next_best_action, 'SCHEDULE');
});

test('@spec:AC-256 runtime graph stores commercial state for any channel/provider caller', () => {
  const output = runPython(`
import json
from ai_agent_runtime.graph import AgentRuntimeGraph, StaticResponseGenerator
from ai_agent_runtime.state import AgentState

logs = []
graph = AgentRuntimeGraph(
    response_generator=StaticResponseGenerator("ok"),
    stage_logger=lambda stage, details=None: logs.append({"stage": stage, "details": details or {}}),
)
state = graph.run(AgentState(conversation_id="conv", organization_id="org", current_message="Quero saber mais sobre botox"))
print(json.dumps({"commercial": state.context["commercialState"], "logs": logs}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.commercial.patient_need_summary.procedure_interest, 'Botox');
  assert.ok(parsed.logs.some((entry) => entry.stage === 'commercial_state_updated'));
});

test('@spec:AC-318 @spec:AC-319 @spec:AC-320 @spec:AC-321 commercial prompt bans internal gaps, technical forcing, and artificial style', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook

playbook = CommercialPlaybook()
state = playbook.evaluate(
    [{"direction": "inbound", "text": "Quero colocar lentes"}, {"direction": "inbound", "text": "Pode marcar a avaliacao"}],
    current_message="Pode marcar a avaliacao",
)
prompt = playbook.prompt_sections(state, authorized_evidence="Tratamentos esteticos sao avaliados conforme o caso do paciente.")
print(json.dumps({"state": state.as_dict(), "prompt": prompt}))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.state.patient_need_summary.procedure_interest, 'lentes');
  assert.match(parsed.prompt, /Nunca diga frases como/);
  assert.match(parsed.prompt, /nao consigo confirmar por aqui/);
  assert.match(parsed.prompt, /Nao force o paciente a escolher subtipo tecnico/);
  assert.match(parsed.prompt, /linguagem simples de WhatsApp/);
  assert.match(parsed.prompt, /sem Markdown artificial/);
  assert.match(parsed.prompt, /sem travessao/);
});

test('@spec:AC-322 @spec:AC-323 @spec:AC-324 @spec:AC-325 operational memory extracts known scheduling data and WhatsApp phone', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook

messages = [
    {"direction": "inbound", "text": "Quero marcar"},
    {"direction": "inbound", "text": "Prefiro Brotas"},
    {"direction": "inbound", "text": "Amanha as 17"},
]
state = CommercialPlaybook().evaluate(
    messages,
    current_message="Amanha as 17",
    channel_contact_external_id="+55 (71) 99999-0000",
)
print(json.dumps(state.as_dict(), sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.operational_memory.preferred_location, 'Brotas');
  assert.equal(parsed.operational_memory.preferred_date, 'amanha');
  assert.equal(parsed.operational_memory.preferred_time, '17:00');
  assert.equal(parsed.operational_memory.patient_phone, '5571999990000');
  assert.equal(parsed.scheduling_state, 'APPOINTMENT_INTENT');
});

test('@spec:AC-326 @spec:AC-327 registration collection groups missing fields and skips known ones', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook

playbook = CommercialPlaybook()
many_missing = playbook.evaluate(
    [{"direction": "inbound", "text": "Quero fazer o cadastro"}],
    current_message="Quero fazer o cadastro",
    channel_contact_external_id="5571999990000",
).as_dict()
few_missing = playbook.evaluate(
    [{"direction": "inbound", "text": "Meu nome e Gabriel Silva, email gabriel@example.com, CPF 12345678901, RG 1234567, CEP 40100-000, Rua Bahia 10"}],
    current_message="Rua Bahia 10",
    channel_contact_external_id="5571999990000",
).as_dict()
print(json.dumps({"many": many_missing, "few": few_missing}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.many.registration_collection_policy, 'GROUP_MISSING_FIELDS');
  assert.equal(parsed.many.operational_memory.patient_phone, '5571999990000');
  assert.equal(parsed.many.operational_memory.patient_name, undefined);
  assert.equal(parsed.few.registration_collection_policy, 'ASK_ONLY_MISSING_FIELDS');
  assert.equal(parsed.few.operational_memory.patient_name, 'Gabriel Silva');
  assert.equal(parsed.few.operational_memory.email, 'gabriel@example.com');
  assert.equal(parsed.few.operational_memory.cpf, '12345678901');
});

test('@spec:AC-328 @spec:AC-329 correction state acknowledges current correction once and booking truth stays deterministic', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook

playbook = CommercialPlaybook()
current = playbook.evaluate(
    [{"direction": "inbound", "text": "Quem disse que sou mulher? Ser atendido."}],
    current_message="Quem disse que sou mulher? Ser atendido.",
).as_dict()
later = playbook.evaluate(
    [{"direction": "inbound", "text": "Quem disse que sou mulher? Ser atendido."}, {"direction": "inbound", "text": "Prefiro amanha as 17"}],
    current_message="Prefiro amanha as 17",
).as_dict()
booked = playbook.evaluate(
    [{"direction": "inbound", "text": "Quero marcar"}, {"direction": "inbound", "text": "amanha as 17"}],
    current_message="amanha as 17",
    scheduling_context_active=True,
    scheduling_status="BOOKED",
).as_dict()
print(json.dumps({"current": current, "later": later, "booked": booked}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.current.correction_state.treatment_preference, 'masculine');
  assert.equal(parsed.current.correction_state.acknowledge_once, true);
  assert.equal(parsed.later.correction_state.treatment_preference, 'masculine');
  assert.equal(parsed.later.correction_state.acknowledge_once, false);
  assert.equal(parsed.later.scheduling_state, 'APPOINTMENT_INTENT');
  assert.equal(parsed.booked.scheduling_state, 'BOOKED');
});

test('@spec:AC-364 @spec:AC-365 appointment intent starts only after explicit or contextual scheduling acceptance', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook

playbook = CommercialPlaybook()
question = playbook.evaluate(
    [{"direction": "inbound", "text": "Oi, quero colocar lentes. Quanto custa a avaliacao?"}],
    current_message="Oi, quero colocar lentes. Quanto custa a avaliacao?",
).as_dict()
accepted = playbook.evaluate(
    [{"direction": "inbound", "text": "Oi, quero colocar lentes. Quanto custa a avaliacao?"}, {"direction": "inbound", "text": "Quero"}],
    current_message="Quero",
    previous_assistant_question="A avaliacao e gratuita. Quer que eu veja um horario para voce?",
).as_dict()
print(json.dumps({"question": question, "accepted": accepted}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.question.operational_memory.appointment_intent, undefined);
  assert.equal(parsed.question.scheduling_state, 'NONE');
  assert.equal(parsed.accepted.operational_memory.appointment_intent, 'true');
  assert.equal(parsed.accepted.next_best_action, 'SCHEDULE');
});

test('@spec:AC-366 @spec:AC-368 @spec:AC-369 @spec:AC-370 @spec:AC-371 registration memory parses block, asks only missing fields, and avoids address inference', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook

playbook = CommercialPlaybook()
block = "Fernando Augusto, fernando@gmail.com, 07693271502, 15125843-02, 17727390, rua praia"
after_block = playbook.evaluate(
    [{"direction": "inbound", "text": "Quero agendar"}, {"direction": "inbound", "text": block}],
    current_message=block,
    previous_assistant_question="Para concluir seu cadastro, me envie nome completo, e-mail, CPF, RG, CEP e endereco.",
).as_dict()
complete = playbook.evaluate(
    [{"direction": "inbound", "text": "Quero agendar"}, {"direction": "inbound", "text": block}, {"direction": "inbound", "text": "12, Vilas, Lauro, Bahia"}],
    current_message="12, Vilas, Lauro, Bahia",
    previous_assistant_question="Para concluir seu cadastro, falta numero, bairro, cidade e estado.",
).as_dict()
print(json.dumps({"afterBlock": after_block, "complete": complete}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.afterBlock.registration_memory.patient_name, 'Fernando Augusto');
  assert.equal(parsed.afterBlock.registration_memory.email, 'fernando@gmail.com');
  assert.equal(parsed.afterBlock.registration_memory.cpf, '07693271502');
  assert.equal(parsed.afterBlock.registration_memory.rg, '15125843-02');
  assert.equal(parsed.afterBlock.registration_memory.cep, '17727390');
  assert.equal(parsed.afterBlock.registration_memory.address_street, 'Rua Praia');
  assert.deepEqual(parsed.afterBlock.missing_required_fields, ['address_number', 'address_neighborhood', 'address_city', 'address_state']);
  assert.equal(parsed.afterBlock.next_best_action, 'SCHEDULE');
  assert.equal(parsed.afterBlock.registration_complete, false);
  assert.equal(parsed.complete.registration_memory.address_number, '12');
  assert.equal(parsed.complete.registration_memory.address_neighborhood, 'Vilas');
  assert.equal(parsed.complete.registration_memory.address_city, 'Lauro');
  assert.equal(parsed.complete.registration_memory.address_state, 'Bahia');
  assert.equal(parsed.complete.registration_complete, true);
  assert.equal(parsed.complete.next_best_action, 'SCHEDULE');
  assert.doesNotMatch(JSON.stringify(parsed.complete), /Lauro de Freitas/i);
});

test('@spec:AC-391 @spec:AC-392 @spec:AC-396 @spec:AC-397 @spec:AC-398 current turn intent suppresses stale commercial carryover', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook

playbook = CommercialPlaybook()
history = [
    {"direction": "inbound", "text": "Oi, quero colocar lentes."},
    {"direction": "inbound", "text": "Quanto custa a avaliacao?"},
]
greeting = playbook.evaluate(
    [*history, {"direction": "inbound", "text": "Ola"}],
    current_message="Ola",
    previous_assistant_question="A avaliacao e gratuita. Quer que eu veja um horario para voce?",
    current_message_at="2026-09-03T20:49:00Z",
    previous_assistant_message_at="2026-09-03T19:49:00Z",
).as_dict()
identity = playbook.evaluate(
    [*history, {"direction": "inbound", "text": "Qual seu nome?"}],
    current_message="Qual seu nome?",
    previous_assistant_question="A avaliacao e gratuita. Quer que eu veja um horario para voce?",
).as_dict()
immediate_greeting = playbook.evaluate(
    [*history, {"direction": "inbound", "text": "Oi"}],
    current_message="Oi",
    previous_assistant_question="Quer agendar?",
    current_message_at="105",
    previous_assistant_message_at="100",
).as_dict()
thanks = playbook.evaluate(
    [{"direction": "inbound", "text": "Obrigado"}],
    current_message="Obrigado",
    previous_assistant_question="Funcionamos ate 19h.",
).as_dict()
side = playbook.evaluate(
    [{"direction": "inbound", "text": "Quero falar de implante"}, {"direction": "inbound", "text": "Qual seu nome?"}],
    current_message="Qual seu nome?",
).as_dict()
print(json.dumps({"greeting": greeting, "identity": identity, "immediateGreeting": immediate_greeting, "thanks": thanks, "side": side}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.greeting.current_turn_intent, 'GREETING');
  assert.equal(parsed.greeting.context_continuity, 'NEW_NEUTRAL_TURN');
  assert.equal(parsed.greeting.next_best_action, 'RESPOND_ONLY');
  assert.equal(parsed.greeting.active_topic, null);
  assert.equal(parsed.greeting.persistent_memory.procedure_interest, 'lentes');
  assert.equal(parsed.greeting.context_age_seconds, 3600);
  assert.equal(parsed.greeting.cta_policy, 'CTA_SUPPRESSED_CURRENT_TURN');
  assert.equal(parsed.identity.current_turn_intent, 'IDENTITY_QUERY');
  assert.equal(parsed.identity.context_continuity, 'SIDE_QUERY');
  assert.equal(parsed.identity.next_best_action, 'RESPOND_ONLY');
  assert.equal(parsed.identity.active_topic, null);
  assert.equal(parsed.immediateGreeting.current_turn_intent, 'GREETING');
  assert.equal(parsed.immediateGreeting.next_best_action, 'RESPOND_ONLY');
  assert.equal(parsed.immediateGreeting.operational_memory.appointment_intent, undefined);
  assert.equal(parsed.thanks.current_turn_intent, 'ACKNOWLEDGEMENT');
  assert.equal(parsed.thanks.next_best_action, 'RESPOND_ONLY');
  assert.equal(parsed.side.current_turn_intent, 'IDENTITY_QUERY');
  assert.equal(parsed.side.context_continuity, 'SIDE_QUERY');
  assert.equal(parsed.side.persistent_memory.procedure_interest, 'implante');
  assert.equal(parsed.side.active_topic, null);
});

test('@spec:AC-393 @spec:AC-394 @spec:AC-395 current semantic continuation can resume scheduling or change topic', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook

playbook = CommercialPlaybook()
strong = playbook.evaluate(
    [{"direction": "inbound", "text": "Quero colocar lentes"}, {"direction": "inbound", "text": "Quero"}],
    current_message="Quero",
    previous_assistant_question="Quer que eu veja um horario para sua avaliacao?",
    current_message_at="110",
    previous_assistant_message_at="100",
).as_dict()
late = playbook.evaluate(
    [{"direction": "inbound", "text": "Quero colocar lentes"}, {"direction": "inbound", "text": "Pode marcar para amanha"}],
    current_message="Pode marcar para amanha",
    previous_assistant_question="Quer que eu veja um horario para sua avaliacao?",
    current_message_at="7300",
    previous_assistant_message_at="100",
).as_dict()
topic_change = playbook.evaluate(
    [{"direction": "inbound", "text": "Quero colocar lentes"}, {"direction": "inbound", "text": "Voces fazem implante?"}],
    current_message="Voces fazem implante?",
).as_dict()
print(json.dumps({"strong": strong, "late": late, "topicChange": topic_change}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.strong.context_continuity, 'STRONG_CONTINUATION');
  assert.equal(parsed.strong.operational_memory.appointment_intent, 'true');
  assert.equal(parsed.strong.next_best_action, 'SCHEDULE');
  assert.equal(parsed.late.context_continuity, 'STRONG_CONTINUATION');
  assert.equal(parsed.late.context_age_seconds, 7200);
  assert.equal(parsed.late.next_best_action, 'SCHEDULE');
  assert.equal(parsed.topicChange.current_turn_intent, 'TOPIC_CHANGE');
  assert.equal(parsed.topicChange.context_continuity, 'TOPIC_CHANGE');
  assert.equal(parsed.topicChange.active_topic, 'implante');
  assert.equal(parsed.topicChange.patient_need_summary.procedure_interest, 'implante');
  assert.equal(parsed.topicChange.persistent_memory.procedure_interest, 'implante');
});

test('@spec:AC-401 @spec:AC-404 OTHER neutral turn suppresses stale context and keeps context age in seconds', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook

playbook = CommercialPlaybook()
history = [
    {"direction": "inbound", "text": "Oi, quero colocar lentes."},
    {"direction": "inbound", "text": "Quanto custa a avaliacao?"},
]
neutral = playbook.evaluate(
    [*history, {"direction": "inbound", "text": "TESTE123"}],
    current_message="TESTE123",
    previous_assistant_question="A avaliacao e gratuita. Quer que eu veja um horario para voce?",
    answered_facts={"evaluation_price": {"value": "free", "knowledgeVersion": "v2"}},
    current_message_at="2026-09-03T20:49:00Z",
    previous_assistant_message_at="2026-09-03T19:49:00Z",
).as_dict()
ten_seconds = playbook.evaluate(history, current_message="TESTE123", current_message_at="110", previous_assistant_message_at="100").as_dict()
five_minutes = playbook.evaluate(history, current_message="TESTE123", current_message_at="400000", previous_assistant_message_at="100000").as_dict()
one_hour = playbook.evaluate(history, current_message="TESTE123", current_message_at="4600000", previous_assistant_message_at="1000000").as_dict()
two_hours = playbook.evaluate(history, current_message="TESTE123", current_message_at="8200000", previous_assistant_message_at="1000000").as_dict()
epoch_millis = playbook.evaluate(history, current_message="TESTE123", current_message_at="1786695752889", previous_assistant_message_at="1786695742889").as_dict()
print(json.dumps({
  "neutral": neutral,
  "ages": [
    ten_seconds["context_age_seconds"],
    five_minutes["context_age_seconds"],
    one_hour["context_age_seconds"],
    two_hours["context_age_seconds"],
    epoch_millis["context_age_seconds"],
  ],
}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.neutral.current_turn_intent, 'OTHER');
  assert.equal(parsed.neutral.context_continuity, 'NEW_NEUTRAL_TURN');
  assert.equal(parsed.neutral.next_best_action, 'RESPOND_ONLY');
  assert.equal(parsed.neutral.active_topic, null);
  assert.equal(parsed.neutral.active_context.context_is_stale, true);
  assert.equal(parsed.neutral.persistent_memory.procedure_interest, 'lentes');
  assert.equal(parsed.neutral.answered_facts.evaluation_price.value, 'free');
  assert.deepEqual(parsed.ages, [10, 300, 3600, 7200, 10]);
});

test('@spec:AC-446 @spec:AC-447 @spec:AC-448 @spec:AC-449 @spec:AC-450 patient name requires strong semantic evidence and never consumes dental need text', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook

p = CommercialPlaybook()
need_then_registration = p.evaluate(
    [
        {"direction": "inbound", "text": "Quero saber sobre implante"},
        {"direction": "inbound", "text": "Dois dentes de cima"},
        {"direction": "inbound", "text": "fernando@example.com"},
    ],
    current_message="fernando@example.com",
    previous_assistant_question="Qual seu e-mail?",
).as_dict()
asked_name = p.evaluate(
    [{"direction": "inbound", "text": "Fernando Andrade"}],
    current_message="Fernando Andrade",
    previous_assistant_question="Qual seu nome completo?",
).as_dict()
explicit = p.evaluate(
    [{"direction": "inbound", "text": "Meu nome e Fernando Andrade e quero saber sobre implante"}],
    current_message="Meu nome e Fernando Andrade e quero saber sobre implante",
).as_dict()
short_explicit = [
    p.evaluate([{"direction": "inbound", "text": text}], current_message=text).as_dict()
    for text in ("Sou Fernando", "Pode colocar Fernando")
]
preserved = p.evaluate(
    [
        {"direction": "inbound", "text": "Meu nome e Fernando Andrade"},
        {"direction": "inbound", "text": "Dois dentes de cima"},
    ],
    current_message="Dois dentes de cima",
    previous_assistant_question="O que voce gostaria de resolver?",
).as_dict()
blocked = [
    p.evaluate([{"direction": "inbound", "text": text}], current_message=text).as_dict()
    for text in ("os dois da frente", "implante dentario", "dente de baixo", "lado esquerdo", "quero colocar dois implantes", "terca de manha", "Pituba")
]
print(json.dumps({
    "need": need_then_registration,
    "asked": asked_name,
    "explicit": explicit,
    "short": short_explicit,
    "preserved": preserved,
    "blocked": blocked,
}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.need.operational_memory.patient_name, undefined);
  assert.equal(parsed.asked.operational_memory.patient_name, 'Fernando Andrade');
  assert.equal(parsed.asked.patient_name_resolution.source, 'ACTIVE_NAME_QUESTION');
  assert.equal(parsed.explicit.operational_memory.patient_name, 'Fernando Andrade');
  assert.equal(parsed.explicit.operational_memory.procedure_interest, 'implante');
  assert.equal(parsed.explicit.patient_name_resolution.source, 'CURRENT_TURN_EXPLICIT');
  assert.deepEqual(parsed.short.map((state) => state.operational_memory.patient_name), ['Fernando', 'Fernando']);
  assert.equal(parsed.preserved.operational_memory.patient_name, 'Fernando Andrade');
  assert.equal(parsed.preserved.patient_name_resolution.source, 'HISTORICAL_EXPLICIT');
  for (const state of parsed.blocked) assert.equal(state.operational_memory.patient_name, undefined);
  assert.equal(parsed.need.patient_name_resolution.status, 'REJECTED');
});

test('@spec:AC-451 @spec:AC-452 @spec:AC-453 @spec:AC-454 @spec:AC-455 appointment intent follows current turn then compatible active context then persistent memory', () => {
  const output = runPython(`
import json
from ai_agent_runtime.commercial import CommercialPlaybook

p = CommercialPlaybook()
history = [{"direction": "inbound", "text": "Quero marcar uma avaliacao"}]
def state(text, previous=""):
    return p.evaluate(
        [*history, {"direction": "inbound", "text": text}],
        current_message=text,
        previous_assistant_question=previous,
        current_message_at="400",
        previous_assistant_message_at="100",
    ).as_dict()

neutral = state("TESTE123")
greeting = state("oi")
thanks = state("obrigado")
explicit = p.evaluate([{"direction": "inbound", "text": "quero marcar uma avaliacao"}], current_message="quero marcar uma avaliacao").as_dict()
availability = p.evaluate([{"direction": "inbound", "text": "qual horario voces tem?"}], current_message="qual horario voces tem?").as_dict()
cta_yes = p.evaluate(
    [{"direction": "inbound", "text": "sim"}],
    current_message="sim",
    previous_assistant_question="Quer que eu encaminhe para confirmar um horario?",
).as_dict()
plain_yes = p.evaluate([{"direction": "inbound", "text": "sim"}], current_message="sim").as_dict()
topic_change = state("Tenho outra duvida: voces aceitam boleto?")
compatible_date = state("terca de manha", "Qual dia e periodo voce prefere?")
print(json.dumps({
    "neutral": neutral,
    "greeting": greeting,
    "thanks": thanks,
    "explicit": explicit,
    "availability": availability,
    "ctaYes": cta_yes,
    "plainYes": plain_yes,
    "topicChange": topic_change,
    "compatibleDate": compatible_date,
}, sort_keys=True))
`);
  const parsed = JSON.parse(output);
  assert.equal(parsed.neutral.current_turn_intent, 'OTHER');
  assert.equal(parsed.neutral.context_continuity, 'NEW_NEUTRAL_TURN');
  assert.equal(parsed.neutral.operational_memory.appointment_intent, undefined);
  assert.equal(parsed.neutral.scheduling_state, 'NONE');
  assert.equal(parsed.neutral.next_best_action, 'RESPOND_ONLY');
  for (const state of [parsed.greeting, parsed.thanks, parsed.plainYes, parsed.topicChange]) {
    assert.equal(state.operational_memory.appointment_intent, undefined);
    assert.notEqual(state.next_best_action, 'SCHEDULE');
  }
  assert.equal(parsed.explicit.operational_memory.appointment_intent, 'true');
  assert.equal(parsed.explicit.next_best_action, 'SCHEDULE');
  assert.equal(parsed.explicit.appointment_intent_resolution.source, 'CURRENT_TURN_EXPLICIT');
  assert.equal(parsed.availability.operational_memory.appointment_intent, 'true');
  assert.equal(parsed.ctaYes.operational_memory.appointment_intent, 'true');
  assert.equal(parsed.ctaYes.appointment_intent_resolution.source, 'ACTIVE_APPOINTMENT_CTA');
  assert.equal(parsed.plainYes.appointment_intent_resolution.source, 'NONE_CURRENT_TURN');
  assert.equal(parsed.compatibleDate.operational_memory.appointment_intent, 'true');
  assert.equal(parsed.compatibleDate.appointment_intent_resolution.source, 'ACTIVE_SCHEDULING_CONTEXT');
});
