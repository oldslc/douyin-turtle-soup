"""集成测试 — 服务器启动、健康检查、Admin API 认证、WebSocket"""


def test_health_check(client):
    """公开的健康检查端点应返回 200"""
    resp = client.get("/health")
    assert resp.status_code == 200


def test_public_api_no_auth_needed(client):
    """公开 API 不应被认证拦截"""
    resp = client.get("/api/game/current")
    # 公开 API 应返回 200 或 4xx（非 401），取决于游戏状态
    assert resp.status_code != 401


def test_websocket_connect(client):
    """WebSocket 连接应成功建立"""
    with client.websocket_connect("/ws") as ws:
        data = ws.receive_json()
        assert "type" in data


def test_license_status(client):
    """授权 API 端点应正常响应"""
    resp = client.get("/api/license/status")
    assert resp.status_code == 200
    assert "status" in resp.json()

    resp2 = client.get("/api/license/trial/start")
    assert resp2.status_code == 200
    assert "ok" in resp2.json() or "remaining_seconds" in resp2.json()
