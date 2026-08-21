'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  DecisionResult,
  DomainErrorCode,
  assertPatientMessageAllowed,
  decideFactualSupport,
  findForbiddenPatientMessageTerm,
  prepareHumanHandoff,
} = require('../../src/ai-customer-service/domain');

test('@spec:AC-001 unsupported relevant factual information requires internal human handoff', () => {
  assert.equal(
    decideFactualSupport({
      isFactualRelevant: true,
      hasAuthorizedEvidence: false,
    }),
    DecisionResult.HUMAN_HANDOFF_REQUIRED
  );
  assert.equal(
    decideFactualSupport({
      isFactualRelevant: true,
      hasAuthorizedEvidence: true,
    }),
    DecisionResult.SUPPORTED
  );
  assert.equal(
    decideFactualSupport({
      isFactualRelevant: false,
      hasAuthorizedEvidence: false,
    }),
    DecisionResult.INVALID_CONTEXT
  );
});

test('@spec:AC-005 final patient messages reject internal technical language', () => {
  assert.doesNotThrow(() =>
    assertPatientMessageAllowed(
      'Vou acionar uma pessoa da equipe da clinica para continuar seu atendimento.'
    )
  );

  for (const message of [
    'O RAG nao trouxe resposta.',
    'Nao encontrei essa informacao na base.',
    'Houve falha de busca nos documentos.',
    'A evidencia insuficiente impede resposta.',
    'O score de busca foi baixo.',
  ]) {
    assert.throws(() => assertPatientMessageAllowed(message), {
      code: DomainErrorCode.INVALID_PATIENT_MESSAGE,
    });
    assert.ok(findForbiddenPatientMessageTerm(message));
  }
});

test('@spec:AC-006 human handoff preserves conversation context for human continuity', () => {
  const conversation = {
    id: 'conversation-1',
    patientId: 'patient-1',
    patientProfile: {
      name: 'Ana',
      phone: '+55 71 99999-0000',
    },
    knownFacts: {
      requestedProcedure: 'Botox',
      preferredUnit: 'Salvador',
    },
    messages: [
      { direction: 'inbound', text: 'Oi, voces fazem botox?' },
      { direction: 'inbound', text: 'Tenho preferencia por Salvador.' },
    ],
    metadata: {
      channel: 'whatsapp',
    },
  };

  const handoff = prepareHumanHandoff({
    conversation,
    transitionMessage: 'Vou acionar uma pessoa da equipe da clinica para continuar seu atendimento.',
  });

  assert.equal(handoff.decision, DecisionResult.HUMAN_HANDOFF_REQUIRED);
  assert.deepEqual(handoff.handoffContext.messages, conversation.messages);
  assert.deepEqual(handoff.handoffContext.knownFacts, conversation.knownFacts);
  assert.equal(handoff.handoffContext.patientProfile.name, 'Ana');
});

test('@spec:AC-007 handoff transition message is clinic-configured and patient-safe', () => {
  const clinicConfiguredMessage =
    'Vou acionar uma pessoa da equipe da clinica para continuar seu atendimento.';

  const handoff = prepareHumanHandoff({
    conversation: { id: 'conversation-1', messages: [] },
    transitionMessage: clinicConfiguredMessage,
  });

  assert.equal(handoff.transitionMessage, clinicConfiguredMessage);

  assert.throws(
    () =>
      prepareHumanHandoff({
        conversation: { id: 'conversation-1', messages: [] },
        transitionMessage: '',
      }),
    { code: DomainErrorCode.MISSING_HANDOFF_TRANSITION_MESSAGE }
  );
  assert.throws(
    () =>
      prepareHumanHandoff({
        conversation: { id: 'conversation-1', messages: [] },
        transitionMessage: 'Nao encontrei essa informacao nos documentos.',
      }),
    { code: DomainErrorCode.INVALID_PATIENT_MESSAGE }
  );
});
