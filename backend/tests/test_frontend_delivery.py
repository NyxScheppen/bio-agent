from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_frontend_entrypoints_disable_browser_cache():
    for path in ("/", "/index.html", "/analysis/session-1"):
        response = client.get(path)

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store, max-age=0"
        assert response.headers["pragma"] == "no-cache"
        assert response.headers["expires"] == "0"
        assert 'id="root"' in response.text
