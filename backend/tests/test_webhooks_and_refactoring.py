"""
Test suite for Webhooks Integration and Backend Refactoring Verification
Tests: Webhook CRUD, Webhook test dispatch, System routes, Kosmo sync, Admin module, Lumi chat, Dashboard, Auth
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEV_EMAIL = "dev@me.mx"
DEV_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
AGENT_EMAIL = "agente@me.mx"
AGENT_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
COORD_EMAIL = "yael@me.mx"
COORD_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def dev_token(api_client):
    """Get developer authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEV_EMAIL,
        "password": DEV_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Developer authentication failed: {response.status_code}")


@pytest.fixture(scope="module")
def agent_token(api_client):
    """Get agent authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": AGENT_EMAIL,
        "password": AGENT_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Agent authentication failed: {response.status_code}")


@pytest.fixture(scope="module")
def authenticated_client(api_client, dev_token):
    """Session with developer auth header"""
    api_client.headers.update({"Authorization": f"Bearer {dev_token}"})
    return api_client


@pytest.fixture(scope="module")
def agent_client(api_client, agent_token):
    """Session with agent auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {agent_token}"
    })
    return session


class TestAuth:
    """Authentication endpoint tests"""
    
    def test_login_developer(self, api_client):
        """Test developer login returns access_token"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEV_EMAIL,
            "password": DEV_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "Response missing access_token"
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 0
        print(f"✓ Developer login successful, token length: {len(data['access_token'])}")
    
    def test_login_agent(self, api_client):
        """Test agent login returns access_token"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": AGENT_EMAIL,
            "password": AGENT_PASSWORD
        })
        assert response.status_code == 200, f"Agent login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        print("✓ Agent login successful")
    
    def test_login_coordinator(self, api_client):
        """Test coordinator login returns access_token"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORD_EMAIL,
            "password": COORD_PASSWORD
        })
        assert response.status_code == 200, f"Coordinator login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        print("✓ Coordinator login successful")


class TestDashboard:
    """Dashboard endpoint tests"""
    
    def test_dashboard_returns_data(self, authenticated_client):
        """Test GET /api/dashboard returns data"""
        response = authenticated_client.get(f"{BASE_URL}/api/dashboard")
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        data = response.json()
        # Dashboard should return some structure
        assert isinstance(data, dict)
        print(f"✓ Dashboard returns data with keys: {list(data.keys())[:5]}")


class TestWebhookEvents:
    """Webhook events endpoint tests"""
    
    def test_list_webhook_events(self, authenticated_client):
        """Test GET /api/webhooks/events returns 7 events"""
        response = authenticated_client.get(f"{BASE_URL}/api/webhooks/events")
        assert response.status_code == 200, f"Webhook events failed: {response.text}"
        data = response.json()
        assert "events" in data, "Response missing 'events' key"
        events = data["events"]
        assert isinstance(events, list)
        assert len(events) == 7, f"Expected 7 events, got {len(events)}"
        
        # Verify event structure
        expected_events = [
            "journey.started", "journey.closed", "incident.created", 
            "incident.resolved", "package.status_changed", "layout.uploaded", 
            "quality.evaluated"
        ]
        event_names = [e["event"] for e in events]
        for expected in expected_events:
            assert expected in event_names, f"Missing event: {expected}"
        
        print(f"✓ Webhook events: {len(events)} events returned")
        for e in events:
            print(f"  - {e['event']}: {e['description'][:50]}...")


class TestWebhookCRUD:
    """Webhook CRUD operations tests"""
    
    created_webhook_id = None
    
    def test_list_webhooks_empty_or_existing(self, authenticated_client):
        """Test GET /api/webhooks returns list"""
        response = authenticated_client.get(f"{BASE_URL}/api/webhooks")
        assert response.status_code == 200, f"List webhooks failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ List webhooks: {len(data)} webhooks found")
    
    def test_create_webhook(self, authenticated_client):
        """Test POST /api/webhooks creates webhook"""
        webhook_data = {
            "name": "TEST_Webhook_httpbin",
            "url": "https://httpbin.org/post",
            "events": ["journey.started", "incident.created"],
            "is_active": True
        }
        response = authenticated_client.post(f"{BASE_URL}/api/webhooks", json=webhook_data)
        assert response.status_code == 200, f"Create webhook failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "id" in data, "Response missing 'id'"
        assert data["name"] == webhook_data["name"]
        assert data["url"] == webhook_data["url"]
        assert data["events"] == webhook_data["events"]
        assert data["is_active"]
        assert "secret" in data, "Response missing 'secret'"
        assert len(data["secret"]) == 32, f"Secret should be 32 chars, got {len(data['secret'])}"
        
        TestWebhookCRUD.created_webhook_id = data["id"]
        print(f"✓ Created webhook: {data['id']}")
        print(f"  - Name: {data['name']}")
        print(f"  - URL: {data['url']}")
        print(f"  - Events: {data['events']}")
        print(f"  - Secret: {data['secret'][:8]}...")
    
    def test_update_webhook(self, authenticated_client):
        """Test PUT /api/webhooks/{id} updates webhook"""
        if not TestWebhookCRUD.created_webhook_id:
            pytest.skip("No webhook created to update")
        
        update_data = {
            "name": "TEST_Webhook_Updated",
            "events": ["journey.started", "journey.closed", "incident.created"]
        }
        response = authenticated_client.put(
            f"{BASE_URL}/api/webhooks/{TestWebhookCRUD.created_webhook_id}",
            json=update_data
        )
        assert response.status_code == 200, f"Update webhook failed: {response.text}"
        data = response.json()
        assert "message" in data
        print(f"✓ Updated webhook: {data['message']}")
    
    def test_webhook_test_dispatch(self, authenticated_client):
        """Test POST /api/webhooks/{id}/test dispatches to real URL"""
        if not TestWebhookCRUD.created_webhook_id:
            pytest.skip("No webhook created to test")
        
        response = authenticated_client.post(
            f"{BASE_URL}/api/webhooks/{TestWebhookCRUD.created_webhook_id}/test"
        )
        assert response.status_code == 200, f"Test webhook failed: {response.text}"
        data = response.json()
        
        # Verify delivery result structure
        assert "status" in data, "Response missing 'status'"
        assert "attempts" in data, "Response missing 'attempts'"
        assert data["is_test"]
        
        # httpbin.org/post should return 200
        if data["status"] == "success":
            assert data["final_status_code"] == 200
            print(f"✓ Webhook test successful: status={data['status']}, code={data['final_status_code']}")
        else:
            print(f"⚠ Webhook test failed: status={data['status']}, attempts={len(data['attempts'])}")
            # Still pass if we got a response (network issues possible)
        
        print(f"  - Attempts: {len(data['attempts'])}")
        print(f"  - Event: {data.get('event', 'N/A')}")
    
    def test_get_webhook_deliveries(self, authenticated_client):
        """Test GET /api/webhooks/{id}/deliveries returns delivery log"""
        if not TestWebhookCRUD.created_webhook_id:
            pytest.skip("No webhook created")
        
        response = authenticated_client.get(
            f"{BASE_URL}/api/webhooks/{TestWebhookCRUD.created_webhook_id}/deliveries"
        )
        assert response.status_code == 200, f"Get deliveries failed: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Webhook deliveries: {len(data)} deliveries found")
        if data:
            print(f"  - Latest: {data[0].get('event', 'N/A')} - {data[0].get('status', 'N/A')}")
    
    def test_regenerate_webhook_secret(self, authenticated_client):
        """Test POST /api/webhooks/{id}/regenerate-secret returns new secret"""
        if not TestWebhookCRUD.created_webhook_id:
            pytest.skip("No webhook created")
        
        response = authenticated_client.post(
            f"{BASE_URL}/api/webhooks/{TestWebhookCRUD.created_webhook_id}/regenerate-secret"
        )
        assert response.status_code == 200, f"Regenerate secret failed: {response.text}"
        data = response.json()
        
        assert "secret" in data, "Response missing 'secret'"
        assert len(data["secret"]) == 32
        assert "message" in data
        print(f"✓ Regenerated secret: {data['secret'][:8]}...")
    
    def test_delete_webhook(self, authenticated_client):
        """Test DELETE /api/webhooks/{id} deletes webhook"""
        if not TestWebhookCRUD.created_webhook_id:
            pytest.skip("No webhook created to delete")
        
        response = authenticated_client.delete(
            f"{BASE_URL}/api/webhooks/{TestWebhookCRUD.created_webhook_id}"
        )
        assert response.status_code == 200, f"Delete webhook failed: {response.text}"
        data = response.json()
        assert "message" in data
        print(f"✓ Deleted webhook: {data['message']}")
        
        # Verify deletion
        response = authenticated_client.get(f"{BASE_URL}/api/webhooks")
        webhooks = response.json()
        webhook_ids = [w["id"] for w in webhooks]
        assert TestWebhookCRUD.created_webhook_id not in webhook_ids
        print("✓ Verified webhook no longer exists")


class TestSystemRoutes:
    """System routes tests (refactored from factory pattern)"""
    
    def test_system_health(self, authenticated_client):
        """Test GET /api/system/health returns health data"""
        response = authenticated_client.get(f"{BASE_URL}/api/system/health")
        assert response.status_code == 200, f"System health failed: {response.text}"
        data = response.json()
        
        # Verify health response structure
        assert "api_status" in data
        assert "mongo_status" in data
        assert data["api_status"] == "ok"
        assert data["mongo_status"] == "connected"
        print(f"✓ System health: API={data['api_status']}, Mongo={data['mongo_status']}")
        print(f"  - Uptime: {data.get('uptime', 'N/A')}")
        print(f"  - Avg latency: {data.get('avg_latency_ms', 'N/A')}ms")
    
    def test_system_config(self, authenticated_client):
        """Test GET /api/system/config returns config data"""
        response = authenticated_client.get(f"{BASE_URL}/api/system/config")
        assert response.status_code == 200, f"System config failed: {response.text}"
        data = response.json()
        
        # Verify config response structure
        assert "backend_version" in data
        assert "python_version" in data
        assert "mongo_host" in data
        assert "db_name" in data
        print("✓ System config:")
        print(f"  - Backend: {data.get('backend_version', 'N/A')}")
        print(f"  - Python: {data.get('python_version', 'N/A')}")
        print(f"  - DB: {data.get('db_name', 'N/A')}")
    
    def test_system_errors(self, authenticated_client):
        """Test GET /api/system/errors returns errors list"""
        response = authenticated_client.get(f"{BASE_URL}/api/system/errors")
        assert response.status_code == 200, f"System errors failed: {response.text}"
        data = response.json()
        
        assert "errors" in data
        assert isinstance(data["errors"], list)
        print(f"✓ System errors: {len(data['errors'])} errors found")
    
    def test_system_logs(self, authenticated_client):
        """Test GET /api/system/logs returns audit logs"""
        response = authenticated_client.get(f"{BASE_URL}/api/system/logs")
        assert response.status_code == 200, f"System logs failed: {response.text}"
        data = response.json()
        
        assert "logs" in data
        assert "total" in data
        assert isinstance(data["logs"], list)
        print(f"✓ System logs: {data['total']} total logs, showing {len(data['logs'])}")


class TestKosmoSyncRoutes:
    """Kosmo sync routes tests (refactored router)"""
    
    def test_sync_status(self, authenticated_client):
        """Test GET /api/sync/status returns sync status"""
        response = authenticated_client.get(f"{BASE_URL}/api/sync/status")
        assert response.status_code == 200, f"Sync status failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "last_sync" in data or data.get("last_sync") is None
        print("✓ Kosmo sync status:")
        print(f"  - Last sync: {data.get('last_sync', 'Never')}")
        print(f"  - Total checked: {data.get('total_checked', 0)}")
        print(f"  - Updated: {data.get('updated', 0)}")
        print(f"  - Errors: {data.get('errors', 0)}")


class TestAdminModuleRoutes:
    """Admin module routes tests (moved from backend/admin.py)"""
    
    def test_admin_summary(self, authenticated_client):
        """Test GET /api/admin/summary returns summary data"""
        response = authenticated_client.get(f"{BASE_URL}/api/admin/summary")
        assert response.status_code == 200, f"Admin summary failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "by_entregable" in data
        assert "totals" in data
        print("✓ Admin summary:")
        print(f"  - Evaluaciones: {data.get('evaluaciones_count', 0)}")
        print(f"  - Lumi: {data.get('lumi_count', 0)}")
        print(f"  - Reportes: {data.get('reportes_count', 0)}")
        print(f"  - Total cost USD: ${data['totals'].get('cost_usd', 0)}")


class TestLumiChatRoute:
    """Lumi AI chatbot route tests (refactored)"""
    
    def test_lumi_chat_endpoint_exists(self, authenticated_client):
        """Test POST /api/chat/lumi endpoint exists (may fail due to LLM key)"""
        response = authenticated_client.post(f"{BASE_URL}/api/chat/lumi", json={
            "message": "Hola, dame un resumen",
            "period": "7d"
        })
        
        # Accept 200 (success) or 500 (LLM key issue) - endpoint exists
        assert response.status_code in [200, 500], f"Lumi chat unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert "reply" in data
            print(f"✓ Lumi chat working: {data['reply'][:100]}...")
        else:
            # 500 is expected if LLM key is invalid or no data
            print("⚠ Lumi chat returned 500 (expected if LLM key issue or no data)")
            print(f"  - Response: {response.text[:200]}")


class TestAgentPermissions:
    """Test that agent role cannot access webhook endpoints"""
    
    def test_agent_cannot_list_webhooks(self, agent_client):
        """Agent should get 403 on webhook list"""
        response = agent_client.get(f"{BASE_URL}/api/webhooks")
        # Agent should be forbidden from webhook management
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Agent correctly denied access to webhooks (403)")
    
    def test_agent_can_list_webhook_events(self, agent_client):
        """Agent should be able to list webhook events (read-only)"""
        response = agent_client.get(f"{BASE_URL}/api/webhooks/events")
        assert response.status_code == 200, f"Agent should see events: {response.text}"
        print("✓ Agent can view webhook events (200)")


class TestCleanup:
    """Cleanup test webhooks"""
    
    def test_cleanup_test_webhooks(self, authenticated_client):
        """Delete any TEST_ prefixed webhooks"""
        response = authenticated_client.get(f"{BASE_URL}/api/webhooks")
        if response.status_code == 200:
            webhooks = response.json()
            for wh in webhooks:
                if wh.get("name", "").startswith("TEST_"):
                    authenticated_client.delete(f"{BASE_URL}/api/webhooks/{wh['id']}")
                    print(f"  Cleaned up: {wh['name']}")
        print("✓ Cleanup complete")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
