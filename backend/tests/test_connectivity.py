import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_api_client_error_handling():
    # 1. Test 415 error on invalid content-type
    res = client.post('/inspect', files={'image': ('bad.txt', b'hello', 'text/plain')})
    assert res.status_code == 415
    assert 'Upload an image file' in res.json()['detail']

    # 2. Test 400 error on empty image file
    res = client.post('/inspect', files={'image': ('empty.png', b'', 'image/png')})
    assert res.status_code == 400
    assert 'empty' in res.json()['detail'].lower()

    # 3. Test 413 error on oversized upload (> 10 MB)
    oversized_data = b'A' * (10 * 1024 * 1024 + 16)
    res = client.post('/inspect', files={'image': ('huge.png', oversized_data, 'image/png')})
    assert res.status_code == 413
    assert '10 MB' in res.json()['detail']

    # 4. Test 422 error on unprocessable/corrupted image data
    corrupted_data = b'THIS_IS_NOT_A_REAL_IMAGE_FORMAT' * 10
    res = client.post('/inspect', files={'image': ('corrupt.png', corrupted_data, 'image/png')})
    assert res.status_code == 422
    assert 'decoded' in res.json()['detail'].lower()

    # 5. Test 404 error on non-existent inspection
    res = client.get('/inspection/999999')
    assert res.status_code == 404
    assert 'not found' in res.json()['detail'].lower()

def test_cors_headers_with_frontend_origin():
    # Test POST /inspect preflight with Origin http://localhost:3000
    res = client.options(
        '/inspect',
        headers={
            'Origin': 'http://localhost:3000',
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'Content-Type',
        }
    )
    assert res.status_code == 200
    assert res.headers['access-control-allow-origin'] == 'http://localhost:3000'
    assert res.headers.get('access-control-allow-credentials') is None or res.headers.get('access-control-allow-credentials') == 'false'

    # Test GET /history with Origin http://localhost:3000
    res = client.get('/history', headers={'Origin': 'http://localhost:3000'})
    assert res.status_code == 200
    assert res.headers['access-control-allow-origin'] == 'http://localhost:3000'