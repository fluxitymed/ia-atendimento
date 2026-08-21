'use strict';

const { DomainErrorCode, DomainRuleError } = require('./constants');
const { assertDocumentVersionOrganization } = require('./organization-guards');

function createDocument({ id, organizationId, documentType, title, createdAt, updatedAt }) {
  return {
    entityType: 'DOCUMENT',
    id,
    organizationId,
    documentType,
    title,
    createdAt,
    updatedAt,
  };
}

function createDocumentVersion({ document, version }) {
  const documentVersion = {
    entityType: 'DOCUMENT_VERSION',
    ...version,
    documentId: document.id,
    organizationId: document.organizationId,
  };
  assertDocumentAndVersionAreDistinct(document, documentVersion);
  assertDocumentVersionOrganization(document, documentVersion);
  return documentVersion;
}

function assertDocumentAndVersionAreDistinct(document, documentVersion) {
  if (!document || !documentVersion || document.entityType === documentVersion.entityType) {
    throw new DomainRuleError(
      DomainErrorCode.INVALID_SUPERSEDES_RELATIONSHIP,
      'Document and document version must be represented as distinct entities.'
    );
  }
  if (document.id === documentVersion.id) {
    throw new DomainRuleError(
      DomainErrorCode.INVALID_SUPERSEDES_RELATIONSHIP,
      'A document version cannot replace the logical document identity.',
      { id: document.id }
    );
  }
  if (documentVersion.documentId !== document.id) {
    throw new DomainRuleError(
      DomainErrorCode.INVALID_SUPERSEDES_RELATIONSHIP,
      'Document version must point to the durable document identity.',
      { documentId: document.id, versionDocumentId: documentVersion.documentId }
    );
  }
}

function createReindexOperation({ documentVersion, indexId, indexVersion, embeddingModel, createdAt }) {
  return {
    entityType: 'DOCUMENT_INDEX',
    id: indexId,
    documentId: documentVersion.documentId,
    documentVersionId: documentVersion.id,
    organizationId: documentVersion.organizationId,
    indexVersion,
    embeddingModel,
    createdAt,
  };
}

function reindexDocumentVersion({ documentVersion, indexId, indexVersion, embeddingModel, createdAt }) {
  return {
    documentVersion,
    index: createReindexOperation({
      documentVersion,
      indexId,
      indexVersion,
      embeddingModel,
      createdAt,
    }),
  };
}

module.exports = {
  assertDocumentAndVersionAreDistinct,
  createDocument,
  createDocumentVersion,
  createReindexOperation,
  reindexDocumentVersion,
};
