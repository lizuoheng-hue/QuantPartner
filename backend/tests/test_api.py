import os
import time
import uuid

os.environ["DATABASE_URL"] = "sqlite:///./test_quantpartner.db"

from fastapi.testclient import TestClient

from app.main import app


def auth_headers(client: TestClient, prefix: str = "user") -> dict[str, str]:
    response = client.post("/api/v1/auth/register", json={
        "email": f"{prefix}-{uuid.uuid4().hex[:10]}@example.com",
        "password": "safe-password-123",
        "display_name": "测试用户",
        "workspace_name": "测试工作区",
    })
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_health_and_templates():
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        templates = client.get("/api/v1/templates").json()
        assert len(templates) == 3


def test_parse_endpoint_blocks_compliance_redline():
    with TestClient(app) as client:
        response = client.post("/api/v1/strategy/parse", json={"text": "推荐下个月能翻倍的股票"})
        assert response.status_code == 200
        assert response.json()["compliance_status"] == "blocked"


def test_full_strategy_backtest_version_and_idempotency_flow():
    with TestClient(app) as client:
        headers = auth_headers(client)
        template = client.get("/api/v1/templates").json()[0]
        strategy = client.post(
            "/api/v1/strategies",
            json={"name": template["name"], "spec": template["spec"]},
            headers=headers,
        )
        assert strategy.status_code == 201
        strategy_id = strategy.json()["id"]
        idempotency_key = str(uuid.uuid4())
        request = {"strategy_id": strategy_id, "spec": template["spec"], "idempotency_key": idempotency_key}
        first = client.post("/api/v1/backtests", json=request, headers=headers)
        second = client.post("/api/v1/backtests", json=request, headers=headers)
        assert first.status_code == 202
        assert second.json()["id"] == first.json()["id"]

        task = client.get(f"/api/v1/backtests/{first.json()['id']}", headers=headers).json()
        assert task["status"] == "completed"
        assert task["result"]["disclaimer"]
        versions = client.get(f"/api/v1/strategies/{strategy_id}/versions", headers=headers).json()
        assert len(versions) == 2
        assert versions[0]["note"] == "回测完成自动保存"


def test_workspace_isolation_and_paper_order_audit():
    with TestClient(app) as client:
        first_headers = auth_headers(client, "first")
        second_headers = auth_headers(client, "second")
        template = client.get("/api/v1/templates").json()[0]
        strategy = client.post("/api/v1/strategies", json={"name": template["name"], "spec": template["spec"]}, headers=first_headers).json()
        assert client.get(f"/api/v1/strategies/{strategy['id']}/versions", headers=second_headers).status_code == 404

        order = client.post("/api/v1/paper/orders", headers=first_headers, json={
            "market": "US", "symbol": "AAPL.US", "side": "buy", "order_type": "limit",
            "quantity": 10, "limit_price": 200, "client_order_id": str(uuid.uuid4()),
        })
        assert order.status_code == 201
        assert order.json()["status"] == "accepted"
        assert client.get("/api/v1/paper/orders", headers=second_headers).json() == []
        events = client.get("/api/v1/audit-events", headers=first_headers).json()
        assert any(item["action"] == "paper_order.create" for item in events)


def test_product_console_notifications_and_agent_gateway_are_paper_only():
    with TestClient(app) as client:
        headers = auth_headers(client, "agent")
        manifest = client.get("/api/agent/v1/manifest", headers=headers)
        assert manifest.status_code == 200
        manifest_json = manifest.json()
        assert manifest_json["mode"] == "paper_only"
        assert manifest_json["live_trading_enabled"] is False
        assert any(tool["name"] == "live_order.create" and tool["status"] == "blocked" for tool in manifest_json["tools"])

        notifications = client.get("/api/v1/product/notifications", headers=headers)
        assert notifications.status_code == 200
        assert any(item["id"] == "webhook" for item in notifications.json())

        live_order = client.post("/api/agent/v1/live/orders", headers=headers, json={
            "market": "US",
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 1,
            "reason": "agent safety regression test",
        })
        assert live_order.status_code == 403

        events = client.get("/api/v1/audit-events", headers=headers).json()
        assert any(item["action"] == "agent.live_order.blocked" for item in events)
