import pytest
import json

def test_health_endpoint(app):
    response = app.get('/api/health')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'ok'
    assert 'analytics_available' in data

def test_projects_endpoint(app):
    response = app.get('/api/projects')
    assert response.status_code in [200, 500]
    if response.status_code == 200:
        data = json.loads(response.data)
        assert 'projects' in data or 'error' in data

def test_notes_endpoint(app):
    # GET note
    response = app.get('/api/notes/test_project.xml/1')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'note' in data

    # POST note
    response = app.post('/api/notes/test_project.xml/1', json={'note': 'Test comment'})
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'ok'