'use strict';

const {
  DocumentStatus,
  DomainErrorCode,
  DomainRuleError,
} = require('./constants');
const { assertSupersedesRelationship } = require('./organization-guards');

function applySupersession(newVersion, supersededVersion) {
  assertSupersedesRelationship(newVersion, supersededVersion);

  if (newVersion.status !== DocumentStatus.PUBLISHED) {
    throw new DomainRuleError(
      DomainErrorCode.INVALID_DOCUMENT_TRANSITION,
      'Only a published version can supersede the current version',
      { status: newVersion.status }
    );
  }

  return {
    newVersion: {
      ...newVersion,
      supersedesVersionId: supersededVersion.id,
    },
    supersededVersion: {
      ...supersededVersion,
      status: DocumentStatus.SUPERSEDED,
    },
  };
}

module.exports = {
  applySupersession,
};
