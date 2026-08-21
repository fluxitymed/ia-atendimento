'use strict';

const {
  DomainErrorCode,
  DomainRuleError,
} = require('./constants');

function failCrossOrg(message, details) {
  throw new DomainRuleError(DomainErrorCode.INVALID_CROSS_ORG_RELATIONSHIP, message, details);
}

function assertDocumentVersionOrganization(document, documentVersion) {
  if (!document || !documentVersion || document.organizationId !== documentVersion.organizationId) {
    failCrossOrg('Document version must belong to the same organization as document', {
      documentOrganizationId: document && document.organizationId,
      versionOrganizationId: documentVersion && documentVersion.organizationId,
    });
  }
  if (documentVersion.documentId !== document.id) {
    throw new DomainRuleError(
      DomainErrorCode.INVALID_SUPERSEDES_RELATIONSHIP,
      'Document version must point to its logical document',
      { documentId: document.id, versionDocumentId: documentVersion.documentId }
    );
  }
}

function assertChunkVersionRelationship(chunk, documentVersion) {
  if (!chunk || !documentVersion || chunk.organizationId !== documentVersion.organizationId) {
    failCrossOrg('Chunk must belong to the same organization as document version', {
      chunkOrganizationId: chunk && chunk.organizationId,
      versionOrganizationId: documentVersion && documentVersion.organizationId,
    });
  }
  if (chunk.documentVersionId !== documentVersion.id || chunk.documentId !== documentVersion.documentId) {
    throw new DomainRuleError(
      DomainErrorCode.INVALID_SUPERSEDES_RELATIONSHIP,
      'Chunk must point to the same document and version',
      {
        chunkDocumentId: chunk.documentId,
        chunkDocumentVersionId: chunk.documentVersionId,
        versionId: documentVersion.id,
        versionDocumentId: documentVersion.documentId,
      }
    );
  }
}

function assertIndexEntryChunkRelationship(indexEntry, chunk) {
  if (!indexEntry || !chunk || indexEntry.organizationId !== chunk.organizationId) {
    failCrossOrg('Index entry must belong to the same organization as chunk', {
      indexEntryOrganizationId: indexEntry && indexEntry.organizationId,
      chunkOrganizationId: chunk && chunk.organizationId,
    });
  }
  if (indexEntry.chunkId !== chunk.id) {
    throw new DomainRuleError(
      DomainErrorCode.INVALID_SUPERSEDES_RELATIONSHIP,
      'Index entry must point to its chunk',
      { indexEntryChunkId: indexEntry.chunkId, chunkId: chunk.id }
    );
  }
}

function assertEvidenceChunkRelationship(evidence, chunk) {
  if (!evidence || !chunk || evidence.organizationId !== chunk.organizationId) {
    failCrossOrg('Evidence must belong to the same organization as chunk', {
      evidenceOrganizationId: evidence && evidence.organizationId,
      chunkOrganizationId: chunk && chunk.organizationId,
    });
  }
  if (evidence.chunkId !== chunk.id) {
    throw new DomainRuleError(
      DomainErrorCode.INVALID_SUPERSEDES_RELATIONSHIP,
      'Evidence must point to its source chunk',
      { evidenceChunkId: evidence.chunkId, chunkId: chunk.id }
    );
  }
  if (
    evidence.documentVersionId !== chunk.documentVersionId ||
    evidence.documentId !== chunk.documentId
  ) {
    throw new DomainRuleError(
      DomainErrorCode.INVALID_SUPERSEDES_RELATIONSHIP,
      'Evidence must preserve chunk document provenance',
      {
        evidenceDocumentId: evidence.documentId,
        evidenceDocumentVersionId: evidence.documentVersionId,
        chunkDocumentId: chunk.documentId,
        chunkDocumentVersionId: chunk.documentVersionId,
      }
    );
  }
}

function assertSupersedesRelationship(documentVersion, supersededVersion) {
  if (!documentVersion || !supersededVersion) {
    throw new DomainRuleError(
      DomainErrorCode.INVALID_SUPERSEDES_RELATIONSHIP,
      'Supersedes relationship requires both versions'
    );
  }
  if (documentVersion.id === supersededVersion.id) {
    throw new DomainRuleError(
      DomainErrorCode.INVALID_SUPERSEDES_RELATIONSHIP,
      'A document version cannot supersede itself',
      { versionId: documentVersion.id }
    );
  }
  if (documentVersion.organizationId !== supersededVersion.organizationId) {
    failCrossOrg('Superseded version must belong to the same organization', {
      versionOrganizationId: documentVersion.organizationId,
      supersededOrganizationId: supersededVersion.organizationId,
    });
  }
  if (documentVersion.documentId !== supersededVersion.documentId) {
    throw new DomainRuleError(
      DomainErrorCode.INVALID_SUPERSEDES_RELATIONSHIP,
      'A version cannot supersede a different logical document',
      {
        versionDocumentId: documentVersion.documentId,
        supersededDocumentId: supersededVersion.documentId,
      }
    );
  }
}

module.exports = {
  assertChunkVersionRelationship,
  assertDocumentVersionOrganization,
  assertEvidenceChunkRelationship,
  assertIndexEntryChunkRelationship,
  assertSupersedesRelationship,
};
