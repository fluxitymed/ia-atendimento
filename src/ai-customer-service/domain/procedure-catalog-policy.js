'use strict';

const {
  DecisionResult,
  IntentType,
  KnowledgeMode,
} = require('./constants');
const { isRetrievalEligible } = require('./retrieval-eligibility');

function normalizeProcedureText(value) {
  if (typeof value !== 'string') return '';
  return value.trim().toLocaleLowerCase('pt-BR').replace(/\s+/g, ' ');
}

function isClosedWorldAuthoritative(documentVersion, activeOrganizationId, now) {
  return (
    documentVersion &&
    documentVersion.knowledgeMode === KnowledgeMode.CLOSED_WORLD &&
    documentVersion.closedWorldCompletenessApproved === true &&
    isRetrievalEligible(documentVersion, activeOrganizationId, now)
  );
}

function isProcedureCatalogClosedWorldAuthoritative(documentVersion, activeOrganizationId, now) {
  return (
    documentVersion &&
    documentVersion.documentType === 'PROCEDURE_CATALOG' &&
    isClosedWorldAuthoritative(documentVersion, activeOrganizationId, now)
  );
}

function isActiveCatalogItem(item) {
  return item && (item.active === true || item.status === 'ACTIVE');
}

function isStructuredCatalogItem(item) {
  return (
    isActiveCatalogItem(item) &&
    typeof item.procedureId === 'string' &&
    item.procedureId.trim() !== '' &&
    typeof item.procedureName === 'string' &&
    item.procedureName.trim() !== ''
  );
}

function itemMatchesRequestedProcedure(item, requestedProcedure) {
  if (!isStructuredCatalogItem(item) || !requestedProcedure) return false;

  if (requestedProcedure.procedureId) {
    return item.procedureId === requestedProcedure.procedureId;
  }

  const requestedName = normalizeProcedureText(requestedProcedure.name || requestedProcedure);
  if (!requestedName) return false;

  const candidates = [
    item.procedureName,
    item.name,
    item.procedureKey,
    ...(Array.isArray(item.aliases) ? item.aliases : []),
  ].map(normalizeProcedureText);

  return candidates.includes(requestedName);
}

function findCatalogMatches(catalogItems, requestedProcedure) {
  return (Array.isArray(catalogItems) ? catalogItems : []).filter((item) =>
    itemMatchesRequestedProcedure(item, requestedProcedure)
  );
}

function decideProcedureExistence({
  catalogVersion,
  catalogItems,
  requestedProcedure,
  activeOrganizationId,
  now,
}) {
  if (!isProcedureCatalogClosedWorldAuthoritative(catalogVersion, activeOrganizationId, now)) {
    return DecisionResult.HUMAN_HANDOFF_REQUIRED;
  }

  const matches = findCatalogMatches(catalogItems, requestedProcedure);
  if (matches.length === 1) return DecisionResult.OFFERED;
  if (matches.length > 1) return DecisionResult.HUMAN_HANDOFF_REQUIRED;
  return DecisionResult.NOT_OFFERED;
}

function decideProcedureInquiry(input) {
  if (input.intentType === IntentType.ENTITY_EXISTENCE) {
    return decideProcedureExistence(input);
  }
  if (input.intentType === IntentType.ENTITY_ATTRIBUTE) {
    return input.hasAuthorizedEvidence === true
      ? DecisionResult.SUPPORTED
      : DecisionResult.HUMAN_HANDOFF_REQUIRED;
  }
  return DecisionResult.INVALID_CONTEXT;
}

module.exports = {
  decideProcedureExistence,
  decideProcedureInquiry,
  findCatalogMatches,
  isClosedWorldAuthoritative,
  isProcedureCatalogClosedWorldAuthoritative,
  isStructuredCatalogItem,
  normalizeProcedureText,
};
