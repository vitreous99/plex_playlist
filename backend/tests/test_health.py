import pytest

@pytest.mark.asyncio
async def test_api_diagnostics_success(client):
    response = await client.get("/api/diagnostics")
    assert response.status_code == 200
    data = response.json()
    assert "plex" in data
    assert "ollama" in data
    assert "sync" in data
