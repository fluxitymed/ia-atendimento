'use strict';

const {
  DecisionResult,
  IntentType,
} = require('./constants');

const ATTRIBUTE_KEYWORDS = Object.freeze([
  'preco',
  'precos',
  'valor',
  'valores',
  'parcelamento',
  'parcelado',
  'parcela',
  'parcelas',
  'preparo',
  'recuperacao',
  'duracao',
  'tempo',
  'disponibilidade',
  'agenda',
  'horario',
  'contraindicacao',
  'contraindicacoes',
  'risco',
  'riscos',
]);

const EXISTENCE_PATTERNS = Object.freeze([
  /\bfaz(?:em)?\b/i,
  /\brealiza(?:m)?\b/i,
  /\btem\b/i,
  /\boferece(?:m)?\b/i,
  /\btrabalha(?:m)?\s+com\b/i,
  /\batende(?:m)?\b/i,
]);

function normalizeQuestion(question) {
  if (typeof question !== 'string') return '';
  return question
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('pt-BR')
    .replace(/\s+/g, ' ')
    .trim();
}

function hasAttributeKeyword(normalizedQuestion) {
  return ATTRIBUTE_KEYWORDS.some((keyword) =>
    new RegExp(`\\b${keyword}\\b`, 'i').test(normalizedQuestion)
  );
}

function hasExistencePattern(question) {
  return EXISTENCE_PATTERNS.some((pattern) => pattern.test(question));
}

function classifyProcedureQuestionIntent(question) {
  const normalizedQuestion = normalizeQuestion(question);
  if (!normalizedQuestion) return DecisionResult.INVALID_CONTEXT;

  if (hasAttributeKeyword(normalizedQuestion)) {
    return IntentType.ENTITY_ATTRIBUTE;
  }
  if (hasExistencePattern(normalizedQuestion)) {
    return IntentType.ENTITY_EXISTENCE;
  }
  return DecisionResult.INVALID_CONTEXT;
}

module.exports = {
  classifyProcedureQuestionIntent,
  normalizeQuestion,
};
