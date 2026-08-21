'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  DecisionResult,
  DocumentStatus,
  IntentType,
  KnowledgeMode,
  validateEvidenceContext,
  validateGroundedResponse,
} = require('../../src/ai-customer-service/domain');

const now = new Date('2026-08-20T12:00:00.000Z');

function document() {
  return {
    id: 'document-1',
    organizationId: 'org-1',
    documentType: 'PRICING',
    title: 'Tabela de precos',
  };
}

function documentVersion(overrides = {}) {
  return {
    id: 'version-1',
    documentId: 'document-1',
    organizationId: 'org-1',
    versionNumber: 1,
    status: DocumentStatus.PUBLISHED,
    effectiveFrom: '2026-08-01T00:00:00.000Z',
    effectiveUntil: null,
    processingValid: true,
    approvedBy: 'reviewer-1',
    approvedAt: '2026-08-19T10:00:00.000Z',
    publishedBy: 'publisher-1',
    publishedAt: '2026-08-20T10:00:00.000Z',
    knowledgeMode: KnowledgeMode.OPEN_WORLD,
    closedWorldCompletenessApproved: false,
    ...overrides,
  };
}

function chunk(overrides = {}) {
  return {
    id: 'chunk-1',
    documentId: 'document-1',
    documentVersionId: 'version-1',
    organizationId: 'org-1',
    sectionPath: ['Precos', 'Botox'],
    content: 'Botox facial: valor R$ 900.',
    ...overrides,
  };
}

function evidence(overrides = {}) {
  return {
    claimId: 'claim-1',
    document: document(),
    documentVersion: documentVersion(),
    chunk: chunk(),
    semanticIntegrityPreserved: true,
    ruleExceptionContextPreserved: true,
    negationsQualifiersPreserved: true,
    sourceSpanApplicable: false,
    ...overrides,
  };
}

test('@spec:AC-005 grounding rejects final messages with internal retrieval language', () => {
  const result = validateGroundedResponse({
    finalMessage: 'Nao encontrei essa informacao na base.',
    claims: [],
    evidences: [],
  });

  assert.equal(result.decision, DecisionResult.HUMAN_HANDOFF_REQUIRED);
  assert.equal(result.reason, 'PATIENT_MESSAGE_EXPOSES_INTERNAL_DETAILS');
});

test('@spec:AC-002 @spec:AC-003 grounding approves negative absence only from closed procedure catalog decision', () => {
  const catalogVersion = documentVersion({
    documentType: 'PROCEDURE_CATALOG',
    knowledgeMode: KnowledgeMode.CLOSED_WORLD,
    closedWorldCompletenessApproved: true,
  });

  assert.equal(
    validateGroundedResponse({
      finalMessage: 'A clinica atualmente nao realiza transplante capilar.',
      claims: [
        {
          id: 'claim-1',
          polarity: 'NEGATIVE_ABSENCE',
          intentType: IntentType.ENTITY_EXISTENCE,
          entityType: 'PROCEDURE',
        },
      ],
      catalogVersion,
      catalogDecision: DecisionResult.NOT_OFFERED,
      activeOrganizationId: 'org-1',
      now,
    }).decision,
    DecisionResult.SUPPORTED
  );

  assert.equal(
    validateGroundedResponse({
      finalMessage: 'A clinica atualmente nao realiza transplante capilar.',
      claims: [
        {
          id: 'claim-1',
          polarity: 'NEGATIVE_ABSENCE',
          intentType: IntentType.ENTITY_ATTRIBUTE,
          entityType: 'PROCEDURE',
        },
      ],
      catalogVersion,
      catalogDecision: DecisionResult.NOT_OFFERED,
      activeOrganizationId: 'org-1',
      now,
    }).decision,
    DecisionResult.HUMAN_HANDOFF_REQUIRED
  );
});

test('@spec:AC-004 factual attribute claims without usable evidence require handoff', () => {
  const result = validateGroundedResponse({
    finalMessage: 'O Botox pode ser parcelado.',
    claims: [
      {
        id: 'claim-1',
        polarity: 'FACTUAL',
        intentType: IntentType.ENTITY_ATTRIBUTE,
        entityType: 'PROCEDURE',
      },
    ],
    evidences: [],
  });

  assert.equal(result.decision, DecisionResult.HUMAN_HANDOFF_REQUIRED);
  assert.equal(result.reason, 'MISSING_EVIDENCE');
});

test('@spec:AC-024 @spec:AC-025 @spec:AC-028 grounding rejects chunks that lost semantic modifiers', () => {
  assert.equal(validateEvidenceContext(evidence()).decision, DecisionResult.SUPPORTED);
  assert.equal(
    validateEvidenceContext(evidence({ semanticIntegrityPreserved: false })).reason,
    'SEMANTIC_INTEGRITY_LOST'
  );
  assert.equal(
    validateEvidenceContext(evidence({ ruleExceptionContextPreserved: false })).reason,
    'RULE_EXCEPTION_CONTEXT_LOST'
  );
  assert.equal(
    validateEvidenceContext(evidence({ negationsQualifiersPreserved: false })).reason,
    'NEGATION_OR_QUALIFIER_LOST'
  );
});

test('@spec:AC-031 grounding requires audit provenance and source span when applicable', () => {
  assert.equal(
    validateEvidenceContext(
      evidence({
        sourceSpanApplicable: true,
        chunk: chunk({ sourceStartOffset: 10, sourceEndOffset: 35 }),
      })
    ).decision,
    DecisionResult.SUPPORTED
  );
  assert.equal(
    validateEvidenceContext(evidence({ sourceSpanApplicable: true })).reason,
    'SOURCE_SPAN_REQUIRED'
  );
  assert.equal(
    validateEvidenceContext(evidence({ chunk: chunk({ sectionPath: '' }) })).reason,
    'INCOMPLETE_PROVENANCE'
  );
});
