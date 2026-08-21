'use strict';

const {
  DecisionResult,
  DomainErrorCode,
  DomainRuleError,
  IntentType,
} = require('./constants');
const { assertPatientMessageAllowed } = require('./handoff-policy');
const { assertRetrievalProvenanceComplete } = require('./provenance');
const { isProcedureCatalogClosedWorldAuthoritative } = require('./procedure-catalog-policy');

function reject(reason, details = {}) {
  return {
    decision: DecisionResult.HUMAN_HANDOFF_REQUIRED,
    reason,
    details,
  };
}

function pass(details = {}) {
  return {
    decision: DecisionResult.SUPPORTED,
    ...details,
  };
}

function evidenceHasUsableSourceSpan(evidence) {
  if (evidence.sourceSpanApplicable === false) return true;
  if (evidence.sourceSpanApplicable === true) {
    return (
      evidence.chunk &&
      Number.isInteger(evidence.chunk.sourceStartOffset) &&
      Number.isInteger(evidence.chunk.sourceEndOffset) &&
      evidence.chunk.sourceEndOffset >= evidence.chunk.sourceStartOffset
    );
  }
  return true;
}

function validateEvidenceContext(evidence) {
  if (!evidence) return reject('MISSING_EVIDENCE');
  if (evidence.retrievalScoreOnly === true) return reject('RETRIEVAL_SCORE_IS_NOT_AUTHORITY');
  if (evidence.semanticIntegrityPreserved !== true) return reject('SEMANTIC_INTEGRITY_LOST');
  if (evidence.ruleExceptionContextPreserved === false) return reject('RULE_EXCEPTION_CONTEXT_LOST');
  if (evidence.negationsQualifiersPreserved === false) return reject('NEGATION_OR_QUALIFIER_LOST');
  if (!evidenceHasUsableSourceSpan(evidence)) return reject('SOURCE_SPAN_REQUIRED');

  try {
    assertRetrievalProvenanceComplete({
      chunk: evidence.chunk,
      documentVersion: evidence.documentVersion,
      document: evidence.document,
    });
  } catch (error) {
    if (error instanceof DomainRuleError) {
      return reject('INCOMPLETE_PROVENANCE', { code: error.code, details: error.details });
    }
    throw error;
  }

  return pass();
}

function validateNegativeAbsenceClaim({ claim, catalogVersion, catalogDecision, activeOrganizationId, now }) {
  if (!claim || claim.polarity !== 'NEGATIVE_ABSENCE') return pass();
  if (claim.intentType !== IntentType.ENTITY_EXISTENCE || claim.entityType !== 'PROCEDURE') {
    return reject('NEGATIVE_ABSENCE_REQUIRES_ENTITY_EXISTENCE_PROCEDURE');
  }
  if (!isProcedureCatalogClosedWorldAuthoritative(catalogVersion, activeOrganizationId, now)) {
    return reject('NEGATIVE_ABSENCE_REQUIRES_CLOSED_WORLD_PROCEDURE_CATALOG');
  }
  if (catalogDecision !== DecisionResult.NOT_OFFERED) {
    return reject('NEGATIVE_ABSENCE_REQUIRES_DETERMINISTIC_CATALOG_DECISION');
  }
  return pass();
}

function validateGroundedResponse({
  finalMessage,
  claims,
  evidences,
  catalogVersion,
  catalogDecision,
  activeOrganizationId,
  now,
}) {
  try {
    assertPatientMessageAllowed(finalMessage || '');
  } catch (error) {
    if (error instanceof DomainRuleError) {
      return reject('PATIENT_MESSAGE_EXPOSES_INTERNAL_DETAILS', {
        code: DomainErrorCode.GROUNDING_REJECTED,
        originalCode: error.code,
      });
    }
    throw error;
  }

  const claimList = Array.isArray(claims) ? claims : [];
  const evidenceList = Array.isArray(evidences) ? evidences : [];

  for (const claim of claimList) {
    const negativeValidation = validateNegativeAbsenceClaim({
      claim,
      catalogVersion,
      catalogDecision,
      activeOrganizationId,
      now,
    });
    if (negativeValidation.decision !== DecisionResult.SUPPORTED) return negativeValidation;

    if (claim.polarity !== 'NEGATIVE_ABSENCE') {
      const claimEvidence = evidenceList.find((evidence) => evidence.claimId === claim.id);
      const evidenceValidation = validateEvidenceContext(claimEvidence);
      if (evidenceValidation.decision !== DecisionResult.SUPPORTED) return evidenceValidation;
    }
  }

  return pass({ validatedClaims: claimList.length });
}

module.exports = {
  validateEvidenceContext,
  validateGroundedResponse,
  validateNegativeAbsenceClaim,
};
