'use strict';

const {
  DecisionResult,
  DomainErrorCode,
  DomainRuleError,
} = require('./constants');

const FORBIDDEN_PATIENT_MESSAGE_PATTERNS = Object.freeze([
  { label: 'RAG', pattern: /\brag\b/i },
  { label: 'base', pattern: /\bbase\b/i },
  { label: 'documentos', pattern: /\bdocumentos?\b/i },
  { label: 'retrieval', pattern: /\bretrieval\b/i },
  { label: 'evidencia insuficiente', pattern: /\bevid[eê]ncia\s+insuficiente\b/i },
  { label: 'informacao nao encontrada', pattern: /\binforma[cç][aã]o\s+n[aã]o\s+encontrada\b/i },
  { label: 'nao encontrei', pattern: /\bn[aã]o\s+encontrei\b/i },
  { label: 'score de busca', pattern: /\bscore(?:\s+de\s+busca)?\b/i },
  { label: 'falha de busca', pattern: /\bfalha\s+de\s+busca\b/i },
]);

function decideFactualSupport({ isFactualRelevant, hasAuthorizedEvidence }) {
  if (isFactualRelevant !== true) return DecisionResult.INVALID_CONTEXT;
  return hasAuthorizedEvidence === true
    ? DecisionResult.SUPPORTED
    : DecisionResult.HUMAN_HANDOFF_REQUIRED;
}

function findForbiddenPatientMessageTerm(message) {
  if (typeof message !== 'string') return null;
  const normalizedMessage = message.normalize('NFC');
  const forbidden = FORBIDDEN_PATIENT_MESSAGE_PATTERNS.find(({ pattern }) =>
    pattern.test(normalizedMessage)
  );
  return forbidden ? forbidden.label : null;
}

function assertPatientMessageAllowed(message) {
  const forbiddenTerm = findForbiddenPatientMessageTerm(message);
  if (forbiddenTerm) {
    throw new DomainRuleError(
      DomainErrorCode.INVALID_PATIENT_MESSAGE,
      'Final patient messages cannot expose internal search, evidence, or retrieval details.',
      { forbiddenTerm }
    );
  }
}

function cloneContextValue(value) {
  if (value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value));
}

function prepareHumanHandoff({
  conversation,
  reason = 'AUTHORIZED_INFORMATION_UNAVAILABLE',
  transitionMessage,
}) {
  if (typeof transitionMessage !== 'string' || transitionMessage.trim() === '') {
    throw new DomainRuleError(
      DomainErrorCode.MISSING_HANDOFF_TRANSITION_MESSAGE,
      'Human handoff requires a clinic-authorized transition message.'
    );
  }

  assertPatientMessageAllowed(transitionMessage);

  return {
    decision: DecisionResult.HUMAN_HANDOFF_REQUIRED,
    transitionMessage,
    handoffContext: {
      reason,
      conversationId: conversation && conversation.id,
      patientId: conversation && conversation.patientId,
      patientProfile: cloneContextValue(conversation && conversation.patientProfile),
      knownFacts: cloneContextValue(conversation && conversation.knownFacts),
      messages: cloneContextValue((conversation && conversation.messages) || []),
      metadata: cloneContextValue(conversation && conversation.metadata),
    },
  };
}

module.exports = {
  assertPatientMessageAllowed,
  decideFactualSupport,
  findForbiddenPatientMessageTerm,
  prepareHumanHandoff,
};
