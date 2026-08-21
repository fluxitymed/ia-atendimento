'use strict';

const DOCUMENT_CONTENT_KIND = 'DOCUMENT_CONTENT_DATA';
const DOCUMENT_CONTENT_AUTHORITY = 'FACTUAL_SOURCE_ONLY';

const agentControlBoundary = Object.freeze({
  systemPromptMutable: false,
  agentRulesMutable: false,
  toolPermissionsMutable: false,
  policiesMutable: false,
  groundingMutable: false,
  handoffMutable: false,
});

const PROMPT_INJECTION_SIGNAL_PATTERNS = Object.freeze([
  /ignore\s+(todas\s+)?as\s+instru[cç][oõ]es\s+anteriores/i,
  /ignore\s+(all\s+)?previous\s+instructions/i,
  /system\s+prompt/i,
  /permiss[oõ]es?\s+de\s+tools?/i,
  /\btool\s+permissions?\b/i,
  /\bhandoff\b/i,
]);

function containsPromptInjectionSignal(content) {
  if (typeof content !== 'string') return false;
  return PROMPT_INJECTION_SIGNAL_PATTERNS.some((pattern) => pattern.test(content));
}

function createDocumentContentData({ content, provenance }) {
  return {
    kind: DOCUMENT_CONTENT_KIND,
    authority: DOCUMENT_CONTENT_AUTHORITY,
    content: typeof content === 'string' ? content : '',
    provenance,
    containsPromptInjectionSignal: containsPromptInjectionSignal(content),
    agentControlBoundary,
  };
}

function coerceRetrievedDocumentContent(retrievedChunk) {
  return createDocumentContentData({
    content: retrievedChunk && retrievedChunk.content,
    provenance: retrievedChunk && retrievedChunk.provenance,
  });
}

function canDocumentContentModifyAgentControls(documentContentData) {
  if (!documentContentData || documentContentData.kind !== DOCUMENT_CONTENT_KIND) return false;
  return Object.values(documentContentData.agentControlBoundary || {}).some((value) => value === true);
}

module.exports = {
  DOCUMENT_CONTENT_AUTHORITY,
  DOCUMENT_CONTENT_KIND,
  agentControlBoundary,
  canDocumentContentModifyAgentControls,
  coerceRetrievedDocumentContent,
  containsPromptInjectionSignal,
  createDocumentContentData,
};
