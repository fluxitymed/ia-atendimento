'use strict';

const {
  DomainErrorCode,
  DomainRuleError,
} = require('./constants');

const PATIENT_MEMORY_FIELDS = Object.freeze([
  'patientId',
  'patientProfile',
  'patientMemory',
  'conversationId',
  'conversationHistory',
  'messages',
  'lastPatientMessage',
]);

function findPatientMemoryFields(payload) {
  if (!payload || typeof payload !== 'object') return [];
  return PATIENT_MEMORY_FIELDS.filter((field) => Object.hasOwn(payload, field));
}

function assertDocumentKnowledgePayloadAllowed(payload) {
  const patientMemoryFields = findPatientMemoryFields(payload);
  if (patientMemoryFields.length > 0) {
    throw new DomainRuleError(
      DomainErrorCode.PATIENT_MEMORY_NOT_ALLOWED_IN_DOCUMENT_KNOWLEDGE,
      'Document knowledge stores clinic-authorized knowledge, not individual patient memory.',
      { patientMemoryFields }
    );
  }
}

function createDocumentKnowledgePayload(payload) {
  assertDocumentKnowledgePayloadAllowed(payload);
  return {
    knowledgeScope: 'CLINIC_AUTHORIZED_KNOWLEDGE',
    ...payload,
  };
}

module.exports = {
  PATIENT_MEMORY_FIELDS,
  assertDocumentKnowledgePayloadAllowed,
  createDocumentKnowledgePayload,
  findPatientMemoryFields,
};
