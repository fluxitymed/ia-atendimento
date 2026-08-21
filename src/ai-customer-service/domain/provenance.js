'use strict';

const {
  DomainErrorCode,
  DomainRuleError,
} = require('./constants');
const {
  assertChunkVersionRelationship,
  assertDocumentVersionOrganization,
} = require('./organization-guards');

function isPresent(value) {
  return value !== null && value !== undefined && value !== '';
}

function missingFields(record, fields, prefix) {
  return fields
    .filter((field) => !isPresent(record && record[field]))
    .map((field) => `${prefix}.${field}`);
}

function assertRetrievalProvenanceComplete({ chunk, documentVersion, document }) {
  assertDocumentVersionOrganization(document, documentVersion);
  assertChunkVersionRelationship(chunk, documentVersion);

  const missing = [
    ...missingFields(document, ['id', 'organizationId', 'title', 'documentType'], 'document'),
    ...missingFields(
      documentVersion,
      [
        'id',
        'documentId',
        'organizationId',
        'versionNumber',
        'status',
        'approvedBy',
        'approvedAt',
        'publishedBy',
        'publishedAt',
      ],
      'documentVersion'
    ),
    ...missingFields(
      chunk,
      ['id', 'documentId', 'documentVersionId', 'organizationId', 'sectionPath'],
      'chunk'
    ),
  ];

  if (missing.length > 0) {
    throw new DomainRuleError(
      DomainErrorCode.INCOMPLETE_RETRIEVAL_PROVENANCE,
      'Retrieval chunk does not have complete provenance for production use.',
      { missing }
    );
  }
}

function buildRetrievalProvenance(input) {
  const { chunk, documentVersion, document } = input;
  assertRetrievalProvenanceComplete(input);

  return {
    chunkId: chunk.id,
    documentId: document.id,
    documentVersionId: documentVersion.id,
    organizationId: document.organizationId,
    documentType: document.documentType,
    title: document.title,
    versionNumber: documentVersion.versionNumber,
    status: documentVersion.status,
    effectiveFrom: documentVersion.effectiveFrom || null,
    effectiveUntil: documentVersion.effectiveUntil || null,
    approvedBy: documentVersion.approvedBy,
    approvedAt: documentVersion.approvedAt,
    publishedBy: documentVersion.publishedBy,
    publishedAt: documentVersion.publishedAt,
    sectionPath: chunk.sectionPath,
  };
}

function hasCompleteRetrievalProvenance(input) {
  try {
    assertRetrievalProvenanceComplete(input);
    return true;
  } catch (error) {
    if (error instanceof DomainRuleError) return false;
    throw error;
  }
}

module.exports = {
  assertRetrievalProvenanceComplete,
  buildRetrievalProvenance,
  hasCompleteRetrievalProvenance,
};
