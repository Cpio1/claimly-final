"""Validate the existing shared schemas and source references, without changing the contracts."""
import copy
import json
import re
from jsonschema import Draft202012Validator, FormatChecker
from .config import ROOT

VERSION = '2.0.0'
SPEC = json.loads((ROOT / 'Claimly_Three_Parts/contracts/llm.openapi.json').read_text())
SCHEMAS = SPEC['components']['schemas']

class Failure(Exception):
    def __init__(self, code, message, status=422, retryable=False):
        self.code, self.message, self.status, self.retryable = code, message, status, retryable
        super().__init__(message)
    def dto(self):
        return {'code': self.code, 'message': self.message, 'retryable': self.retryable}

def validate(name, value, *, output=False):
    schema = {'$ref': '#/components/schemas/' + name, 'components': SPEC['components']}
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        # Never include model/user contents, token values or validation reprs in errors.
        raise Failure('INVALID_LLM_OUTPUT' if output else 'VALIDATION_ERROR',
                      f'{name} does not match the shared contract.', 502 if output else 422)
    return value

def model_schema(name):
    definitions = {}
    def visit(value):
        if isinstance(value, dict):
            if '$ref' in value:
                key = value['$ref'].rsplit('/', 1)[1]
                if key not in definitions:
                    definitions[key] = {}
                    definitions[key] = visit(copy.deepcopy(SCHEMAS[key]))
                return {'$ref': '#/$defs/' + key}
            return {k: visit(v) for k, v in value.items()}
        if isinstance(value, list):
            return [visit(v) for v in value]
        return value
    result = visit(copy.deepcopy(SCHEMAS[name]))
    if definitions:
        result['$defs'] = definitions
    return result

def normalized(text):
    return re.sub(r'\s+', ' ', text).strip()

def evidence_check(value, documents):
    pages = {(d['document_id'], d['document_version'], p['page']): p['text']
             for d in documents for p in d['pages']}
    def visit(obj):
        if isinstance(obj, dict):
            if set(obj) == {'document_id', 'document_version', 'page', 'quote'}:
                key = (obj['document_id'], obj['document_version'], obj['page'])
                if key not in pages or not normalized(obj['quote']) or normalized(obj['quote']) not in normalized(pages[key]):
                    raise Failure('INVALID_LLM_OUTPUT', 'A citation does not resolve to supplied source text.', 502)
            for v in obj.values(): visit(v)
        elif isinstance(obj, list):
            for v in obj: visit(v)
    visit(value)

def extraction_check(value, document):
    validate('ExtractionOutput', value, output=True)
    evidence_check(value, [document])
    for fact in value['facts'].values():
        if fact['origin'] != 'document' or (fact['value'] is not None and not fact['evidence_refs']):
            raise Failure('INVALID_LLM_OUTPUT', 'Extracted facts require document evidence.', 502)
    keys = [b['candidate_key'] for b in value['benefits']]
    if len(keys) != len(set(keys)) or any(not b['evidence_refs'] for b in value['benefits']):
        raise Failure('INVALID_LLM_OUTPUT', 'Benefit candidates require unique keys and source evidence.', 502)

def insufficient_answer(has_documents):
    """Controlled abstention: no generated facts, benefit matches or actions without evidence."""
    return {
        'answer': ('The supplied passages do not provide enough evidence to answer this question.'
                   if has_documents else 'There is no approved document evidence available for this question.'),
        'evidence_refs': [], 'matched_benefit_ids': [], 'next_actions': [],
        'questions': (['Could you provide the relevant document or clarify the detail you want checked?']
                      if has_documents else ['Please upload a supported document and complete its source review.']),
    }

def guard_answer(value, context):
    """Constrain unsupported output; quote validation is not semantic entailment verification."""
    validate('LlmAnswer', value, output=True)
    if not value['evidence_refs']:
        value.clear()
        value.update(insufficient_answer(bool(context['documents'])))
    answer_check(value, context)

def answer_check(value, context):
    validate('LlmAnswer', value, output=True)
    evidence_check(value, context['documents'])
    benefits = {b['id'] for b in context['benefits']}
    if not set(value['matched_benefit_ids']) <= benefits:
        raise Failure('INVALID_LLM_OUTPUT', 'The answer references an unavailable benefit.', 502)
    for action in value['next_actions']:
        target = action['target_id']
        allowed = benefits if action['type'] == 'open_benefit' else ({context['case']['id']} if context['case'] else set())
        if target is not None and target not in allowed:
            raise Failure('INVALID_LLM_OUTPUT', 'The answer action references an unavailable object.', 502)
    if not value['evidence_refs'] and value != insufficient_answer(bool(context['documents'])):
        raise Failure('INVALID_LLM_OUTPUT', 'Uncited output must be a controlled insufficient-evidence response.', 502)
