'use strict';

const { DocumentStatus } = require('./constants');

function toDate(value) {
  if (value === null || value === undefined) return null;
  return value instanceof Date ? value : new Date(value);
}

function isValidDate(value) {
  return value instanceof Date && !Number.isNaN(value.getTime());
}

function isRetrievalEligible(documentVersion, activeOrganizationId, now) {
  if (!documentVersion || !activeOrganizationId) return false;
  const currentTime = toDate(now);
  if (!isValidDate(currentTime)) return false;

  if (documentVersion.status !== DocumentStatus.PUBLISHED) return false;
  if (documentVersion.organizationId !== activeOrganizationId) return false;
  if (documentVersion.processingValid !== true) return false;

  const effectiveFrom = toDate(documentVersion.effectiveFrom);
  if (effectiveFrom && (!isValidDate(effectiveFrom) || effectiveFrom > currentTime)) {
    return false;
  }

  const effectiveUntil = toDate(documentVersion.effectiveUntil);
  if (effectiveUntil && (!isValidDate(effectiveUntil) || effectiveUntil < currentTime)) {
    return false;
  }

  return true;
}

function isChunkRetrievalEligible(chunk, documentVersion, activeOrganizationId, now) {
  if (!chunk || !documentVersion) return false;
  if (chunk.organizationId !== activeOrganizationId) return false;
  if (chunk.organizationId !== documentVersion.organizationId) return false;
  if (chunk.documentVersionId !== documentVersion.id) return false;
  if (chunk.documentId !== documentVersion.documentId) return false;
  return isRetrievalEligible(documentVersion, activeOrganizationId, now);
}

module.exports = {
  isChunkRetrievalEligible,
  isRetrievalEligible,
};
