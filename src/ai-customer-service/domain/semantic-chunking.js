'use strict';

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function pathToText(sectionPath) {
  return asArray(sectionPath).filter(Boolean).join(' > ');
}

function contextToLines(inheritedContext) {
  return asArray(inheritedContext).map((item) => {
    if (typeof item === 'string') return item;
    return `${item.label}: ${item.value}`;
  });
}

function createBaseChunk({ documentVersion, block, semanticType, content, inheritedContext }) {
  return {
    id: block.id || `${documentVersion.id}:${block.chunkIndex || 0}`,
    documentId: documentVersion.documentId,
    documentVersionId: documentVersion.id,
    organizationId: documentVersion.organizationId,
    semanticType,
    sectionPath: asArray(block.sectionPath),
    inheritedContext,
    content,
    parentChunkId: block.parentChunkId,
    sourceStartOffset: block.sourceStartOffset,
    sourceEndOffset: block.sourceEndOffset,
    chunkingStrategy: block.chunkingStrategy || 'semantic-structured',
    chunkingVersion: block.chunkingVersion || '1',
    semanticIntegrityPreserved: true,
    ruleExceptionContextPreserved: block.ruleExceptionContextPreserved !== false,
    negationsQualifiersPreserved: block.negationsQualifiersPreserved !== false,
  };
}

function chunkSemanticUnit({ documentVersion, block }) {
  const inheritedContext = contextToLines(block.inheritedContext);
  const lines = [
    pathToText(block.sectionPath),
    ...inheritedContext,
    block.entity ? `Entidade: ${block.entity}` : null,
    ...Object.entries(block.attributes || {}).map(([key, value]) => `${key}: ${value}`),
    ...asArray(block.rules).map((rule) => `Regra: ${rule}`),
    ...asArray(block.exceptions).map((exception) => `Excecao: ${exception}`),
    ...asArray(block.qualifiers).map((qualifier) => `Qualifier: ${qualifier}`),
  ].filter(Boolean);

  return createBaseChunk({
    documentVersion,
    block,
    semanticType: block.semanticType || 'SEMANTIC_ATOMIC_UNIT',
    inheritedContext,
    content: lines.join('\n'),
  });
}

function chunkFaq({ documentVersion, block }) {
  const inheritedContext = contextToLines(block.inheritedContext);
  const lines = [
    pathToText(block.sectionPath),
    ...inheritedContext,
    `Pergunta: ${block.question}`,
    `Resposta: ${block.answer}`,
  ].filter(Boolean);

  return createBaseChunk({
    documentVersion,
    block,
    semanticType: 'FAQ',
    inheritedContext,
    content: lines.join('\n'),
  });
}

function chunkTableRow({ documentVersion, block }) {
  const inheritedContext = contextToLines(block.inheritedContext);
  const row = block.row || {};
  const headers = asArray(block.headers);
  const lines = [
    pathToText(block.sectionPath),
    ...inheritedContext,
    ...headers.map((header) => `${header}: ${row[header]}`),
  ].filter(Boolean);

  return {
    ...createBaseChunk({
      documentVersion,
      block,
      semanticType: 'TABLE_ROW',
      inheritedContext,
      content: lines.join('\n'),
    }),
    metadata: {
      tableHeaders: headers,
      sourceTable: block.sourceTable,
      sourceRow: block.sourceRow,
    },
  };
}

function chunkStructuredDocument({ documentVersion, blocks }) {
  return asArray(blocks).map((block, index) => {
    const blockWithIndex = { ...block, chunkIndex: index };
    if (block.type === 'FAQ') return chunkFaq({ documentVersion, block: blockWithIndex });
    if (block.type === 'TABLE_ROW') return chunkTableRow({ documentVersion, block: blockWithIndex });
    return chunkSemanticUnit({ documentVersion, block: blockWithIndex });
  });
}

module.exports = {
  chunkFaq,
  chunkSemanticUnit,
  chunkStructuredDocument,
  chunkTableRow,
};
