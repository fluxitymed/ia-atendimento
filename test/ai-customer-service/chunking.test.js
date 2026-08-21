'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  chunkStructuredDocument,
} = require('../../src/ai-customer-service/domain');

function version() {
  return {
    id: 'version-1',
    documentId: 'document-1',
    organizationId: 'org-1',
  };
}

test('@spec:AC-024 semantic chunks keep entity and attributes together', () => {
  const [chunk] = chunkStructuredDocument({
    documentVersion: version(),
    blocks: [
      {
        type: 'SEMANTIC_UNIT',
        sectionPath: ['Precos', 'Botox'],
        entity: 'Botox facial',
        attributes: {
          valor: 'R$ 900',
          modalidade: 'procedimento estetico',
          unidade: 'Salvador',
        },
      },
    ],
  });

  assert.match(chunk.content, /Entidade: Botox facial/);
  assert.match(chunk.content, /valor: R\$ 900/);
  assert.match(chunk.content, /unidade: Salvador/);
  assert.equal(chunk.semanticIntegrityPreserved, true);
});

test('@spec:AC-026 FAQ chunks preserve question and answer together', () => {
  const [chunk] = chunkStructuredDocument({
    documentVersion: version(),
    blocks: [
      {
        type: 'FAQ',
        sectionPath: ['FAQ', 'Agendamento'],
        question: 'Preciso de encaminhamento?',
        answer: 'Nao, a consulta pode ser agendada diretamente.',
      },
    ],
  });

  assert.equal(chunk.semanticType, 'FAQ');
  assert.match(chunk.content, /Pergunta: Preciso de encaminhamento\?/);
  assert.match(chunk.content, /Resposta: Nao, a consulta pode ser agendada diretamente\./);
});

test('@spec:AC-027 table row chunks inherit headers required to interpret values', () => {
  const [chunk] = chunkStructuredDocument({
    documentVersion: version(),
    blocks: [
      {
        type: 'TABLE_ROW',
        sectionPath: ['Tabela de precos'],
        headers: ['Procedimento', 'Unidade', 'Valor PIX', 'Valor cartao'],
        row: {
          Procedimento: 'Consulta dermatologica',
          Unidade: 'Salvador',
          'Valor PIX': 'R$ 500',
          'Valor cartao': 'R$ 550',
        },
        sourceTable: 'precos-2026',
        sourceRow: 2,
      },
    ],
  });

  assert.equal(chunk.semanticType, 'TABLE_ROW');
  assert.match(chunk.content, /Procedimento: Consulta dermatologica/);
  assert.match(chunk.content, /Valor PIX: R\$ 500/);
  assert.match(chunk.content, /Valor cartao: R\$ 550/);
  assert.deepEqual(chunk.metadata.tableHeaders, [
    'Procedimento',
    'Unidade',
    'Valor PIX',
    'Valor cartao',
  ]);
});

test('@spec:AC-029 inherited context comes only from explicit document structure', () => {
  const [withContext, withoutContext] = chunkStructuredDocument({
    documentVersion: version(),
    blocks: [
      {
        type: 'SEMANTIC_UNIT',
        sectionPath: ['Profissionais', 'Dra. Ana', 'Consulta'],
        inheritedContext: [
          { label: 'Profissional', value: 'Dra. Ana' },
          { label: 'Servico', value: 'Consulta presencial' },
        ],
        attributes: {
          valor: 'R$ 500',
        },
      },
      {
        type: 'SEMANTIC_UNIT',
        sectionPath: ['Valores'],
        attributes: {
          valor: 'R$ 300',
        },
      },
    ],
  });

  assert.match(withContext.content, /Profissional: Dra\. Ana/);
  assert.match(withContext.content, /Servico: Consulta presencial/);
  assert.doesNotMatch(withoutContext.content, /Profissional:/);
  assert.doesNotMatch(withoutContext.content, /Servico:/);
});

test('@spec:AC-025 @spec:AC-028 chunking preserves linked rules, exceptions, negations, and qualifiers', () => {
  const [chunk] = chunkStructuredDocument({
    documentVersion: version(),
    blocks: [
      {
        type: 'SEMANTIC_UNIT',
        sectionPath: ['Orientacoes', 'Botox'],
        entity: 'Botox',
        rules: ['Evitar atividade fisica por 24 horas.'],
        exceptions: ['Exceto quando liberado pela equipe clinica.'],
        qualifiers: ['Somente para pacientes ja avaliados.'],
        attributes: {
          contraindicado: 'Nao realizar em gestantes sem avaliacao medica.',
        },
      },
    ],
  });

  assert.match(chunk.content, /Regra: Evitar atividade fisica por 24 horas\./);
  assert.match(chunk.content, /Excecao: Exceto quando liberado pela equipe clinica\./);
  assert.match(chunk.content, /Qualifier: Somente para pacientes ja avaliados\./);
  assert.match(chunk.content, /contraindicado: Nao realizar em gestantes sem avaliacao medica\./);
  assert.equal(chunk.ruleExceptionContextPreserved, true);
  assert.equal(chunk.negationsQualifiersPreserved, true);
});

test('@spec:AC-031 @spec:AC-032 chunking metadata changes do not create a new document version', () => {
  const documentVersion = version();
  const [firstChunk] = chunkStructuredDocument({
    documentVersion,
    blocks: [
      {
        id: 'chunk-child-1',
        type: 'SEMANTIC_UNIT',
        sectionPath: ['Guia', 'Cuidados'],
        parentChunkId: 'chunk-parent-1',
        sourceStartOffset: 120,
        sourceEndOffset: 188,
        chunkingStrategy: 'semantic-structured',
        chunkingVersion: '1',
        entity: 'Botox',
        attributes: {
          cuidado: 'Evitar atividade fisica por 24 horas.',
        },
      },
    ],
  });
  const [rechunked] = chunkStructuredDocument({
    documentVersion,
    blocks: [
      {
        id: 'chunk-child-1-v2',
        type: 'SEMANTIC_UNIT',
        sectionPath: ['Guia', 'Cuidados'],
        parentChunkId: 'chunk-parent-1-v2',
        sourceStartOffset: 120,
        sourceEndOffset: 188,
        chunkingStrategy: 'semantic-structured',
        chunkingVersion: '2',
        entity: 'Botox',
        attributes: {
          cuidado: 'Evitar atividade fisica por 24 horas.',
        },
      },
    ],
  });

  assert.equal(firstChunk.documentVersionId, 'version-1');
  assert.equal(rechunked.documentVersionId, 'version-1');
  assert.equal(firstChunk.parentChunkId, 'chunk-parent-1');
  assert.equal(rechunked.parentChunkId, 'chunk-parent-1-v2');
  assert.equal(rechunked.sourceStartOffset, 120);
  assert.equal(rechunked.sourceEndOffset, 188);
  assert.equal(rechunked.chunkingVersion, '2');
});
