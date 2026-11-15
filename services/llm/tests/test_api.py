"""Internal LLM behavior without a backend, database, downloads or paid inference."""
import copy
import json

from fastapi.testclient import TestClient
import pytest

from services.llm.app.config import ROOT, Settings
from services.llm.app.contracts import VERSION, insufficient_answer
from services.llm.app.main import create_app
from services.llm.app.processing import Processor


def fixture(name):
    return json.loads((ROOT / 'Claimly_Three_Parts/fixtures' / name).read_text())


class TestOnlyProvider:
    __test__ = False

    def __init__(self, response=None):
        self.response = response
        self.calls = 0

    def structured(self, schema, instructions, request, *, check):
        self.calls += 1
        assert self.response is not None, 'Unexpected model inference'
        value = copy.deepcopy(self.response)
        check(value)
        return value


def client(provider=None, *, token='internal-test-token'):
    processor = Processor(provider or TestOnlyProvider(), parser=None)
    return TestClient(create_app(Settings(service_token=token), processor=processor))


AUTH = {'Authorization': 'Bearer internal-test-token'}


def test_health_starts_without_database_or_hosted_model_configuration():
    with TestClient(create_app(Settings())) as api:
        response = api.get('/health')
    assert response.status_code == 200
    assert response.json()['data'] == {
        'status': 'degraded', 'service': 'llm', 'contract_version': VERSION,
    }
    assert response.headers['X-Contract-Version'] == VERSION


@pytest.mark.parametrize('authorization', ['', 'Bearer wrong-token'])
def test_answer_requires_the_internal_token(authorization):
    provider = TestOnlyProvider()
    with client(provider) as api:
        response = api.post('/internal/v1/answer', json=fixture('llm_answer_request.json'),
                            headers={'Authorization': authorization})
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'UNAUTHORIZED'
    assert provider.calls == 0


def test_unconfigured_internal_token_fails_closed():
    with client(token='') as api:
        response = api.post('/internal/v1/answer', json=fixture('llm_answer_request.json'),
                            headers=AUTH)
    assert response.status_code == 401


def test_invalid_request_never_calls_the_provider():
    provider = TestOnlyProvider()
    with client(provider) as api:
        response = api.post('/internal/v1/answer', json={}, headers=AUTH)
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'VALIDATION_ERROR'
    assert provider.calls == 0


@pytest.mark.parametrize('source_state', ['missing', 'blank', 'needs_review'])
def test_unusable_evidence_abstains_without_inference(source_state):
    request = fixture('llm_answer_request.json')
    if source_state == 'missing':
        request['context']['documents'] = []
    else:
        page = request['context']['documents'][0]['pages'][0]
        if source_state == 'blank':
            page['text'] = '   '
        else:
            page['needs_review'] = True
    provider = TestOnlyProvider()
    with client(provider) as api:
        response = api.post('/internal/v1/answer', json=request, headers=AUTH)
    assert response.status_code == 200
    assert response.json()['data'] == insufficient_answer(source_state != 'missing')
    assert provider.calls == 0


def test_uncited_model_output_becomes_controlled_abstention():
    output = fixture('llm_answer.json')['data']
    output['answer'] = 'You are definitely entitled to an immediate refund.'
    output['evidence_refs'] = []
    provider = TestOnlyProvider(output)
    with client(provider) as api:
        response = api.post('/internal/v1/answer', json=fixture('llm_answer_request.json'),
                            headers=AUTH)
    assert response.status_code == 200
    assert response.json()['data'] == insufficient_answer(True)
    assert provider.calls == 1


def test_fabricated_quote_is_rejected():
    output = fixture('llm_answer.json')['data']
    output['evidence_refs'][0]['quote'] = 'A refund is guaranteed for every purchase.'
    with client(TestOnlyProvider(output)) as api:
        response = api.post('/internal/v1/answer', json=fixture('llm_answer_request.json'),
                            headers=AUTH)
    assert response.status_code == 502
    assert response.json()['error']['code'] == 'INVALID_LLM_OUTPUT'


def test_valid_cited_answer_preserves_the_shared_response_shape():
    request = fixture('llm_answer_request.json')
    output = fixture('llm_answer.json')['data']
    with client(TestOnlyProvider(output)) as api:
        response = api.post('/internal/v1/answer', json=request, headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {
        'data': output, 'request_id': request['request_id'], 'contract_version': VERSION,
    }
