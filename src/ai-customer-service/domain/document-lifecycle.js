'use strict';

const {
  DocumentStatus,
  DomainErrorCode,
  DomainRuleError,
} = require('./constants');

const allowedTransitions = Object.freeze({
  [DocumentStatus.DRAFT]: Object.freeze([DocumentStatus.PROCESSING]),
  [DocumentStatus.PROCESSING]: Object.freeze([
    DocumentStatus.REVIEW_REQUIRED,
    DocumentStatus.PROCESSING_FAILED,
  ]),
  [DocumentStatus.PROCESSING_FAILED]: Object.freeze([DocumentStatus.PROCESSING]),
  [DocumentStatus.REVIEW_REQUIRED]: Object.freeze([DocumentStatus.APPROVED]),
  [DocumentStatus.APPROVED]: Object.freeze([
    DocumentStatus.PUBLISHED,
    DocumentStatus.INACTIVE,
  ]),
  [DocumentStatus.PUBLISHED]: Object.freeze([
    DocumentStatus.SUPERSEDED,
    DocumentStatus.INACTIVE,
  ]),
  [DocumentStatus.SUPERSEDED]: Object.freeze([]),
  [DocumentStatus.INACTIVE]: Object.freeze([]),
});

function assertValidDocumentStatus(status) {
  if (!Object.values(DocumentStatus).includes(status)) {
    throw new DomainRuleError(
      DomainErrorCode.INVALID_DOCUMENT_STATUS,
      `Invalid document status: ${status}`,
      { status }
    );
  }
}

function canTransitionDocumentStatus(fromStatus, toStatus) {
  assertValidDocumentStatus(fromStatus);
  assertValidDocumentStatus(toStatus);
  return allowedTransitions[fromStatus].includes(toStatus);
}

function assertValidDocumentTransition(fromStatus, toStatus) {
  if (!canTransitionDocumentStatus(fromStatus, toStatus)) {
    throw new DomainRuleError(
      DomainErrorCode.INVALID_DOCUMENT_TRANSITION,
      `Invalid document transition: ${fromStatus} -> ${toStatus}`,
      { fromStatus, toStatus }
    );
  }
}

function hasProcessingFailure(documentVersion) {
  if (!documentVersion) return true;
  if (documentVersion.status === DocumentStatus.PROCESSING_FAILED) return true;
  if (documentVersion.processingValid !== true) return true;

  const validationFlags = [
    documentVersion.extractionValid,
    documentVersion.normalizationValid,
    documentVersion.validationValid,
    documentVersion.chunkingValid,
    documentVersion.requiredFieldsValid,
  ];
  if (validationFlags.some((flag) => flag === false)) return true;

  const failureCollections = [
    documentVersion.processingErrors,
    documentVersion.requiredFieldErrors,
    documentVersion.missingRequiredFields,
  ];
  return failureCollections.some((collection) => Array.isArray(collection) && collection.length > 0);
}

function assertDocumentPublicationAllowed(documentVersion) {
  const status = documentVersion && documentVersion.status;
  assertValidDocumentTransition(status, DocumentStatus.PUBLISHED);

  if (hasProcessingFailure(documentVersion)) {
    throw new DomainRuleError(
      DomainErrorCode.PUBLICATION_BLOCKED_BY_PROCESSING_FAILURE,
      'Document version cannot be published while processing, validation, chunking, or required fields failed.',
      {
        documentVersionId: documentVersion && documentVersion.id,
        status,
      }
    );
  }
}

function publishDocumentVersion(documentVersion, { publishedBy, publishedAt }) {
  assertDocumentPublicationAllowed(documentVersion);

  return {
    ...documentVersion,
    status: DocumentStatus.PUBLISHED,
    publishedBy,
    publishedAt,
  };
}

module.exports = {
  allowedTransitions,
  assertDocumentPublicationAllowed,
  assertValidDocumentStatus,
  assertValidDocumentTransition,
  canTransitionDocumentStatus,
  hasProcessingFailure,
  publishDocumentVersion,
};
