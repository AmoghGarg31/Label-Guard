from fastapi.testclient import TestClient
from app import app, _parse_cors_origins

def test_cors_origins_parsing(monkeypatch):
    monkeypatch.setenv('CORS_ORIGINS', 'http://localhost:3000, https://labelguard.example.com')
    origins = _parse_cors_origins()
    assert origins == ['http://localhost:3000', 'https://labelguard.example.com']

def test_cors_preflight_allowed_origin():
    client = TestClient(app)
    response = client.options(
        '/inspect',
        headers={
            'Origin': 'http://localhost:3000',
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'Content-Type',
        }
    )
    assert response.status_code == 200
    assert response.headers.get('access-control-allow-origin') == 'http://localhost:3000'
    assert 'POST' in response.headers.get('access-control-allow-methods', '')
    assert 'Content-Type' in response.headers.get('access-control-allow-headers', '')
    assert response.headers.get('access-control-allow-credentials') is None or response.headers.get('access-control-allow-credentials') == 'false'

def test_cors_disallows_unauthorized_origin():
    client = TestClient(app)
    response = client.options(
        '/inspect',
        headers={
            'Origin': 'http://unauthorized-origin.com',
            'Access-Control-Request-Method': 'POST',
        }
    )
    assert response.headers.get('access-control-allow-origin') != 'http://unauthorized-origin.com'
    assert response.headers.get('access-control-allow-origin') != '*'