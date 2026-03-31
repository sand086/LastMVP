"""
Iteration 24 - Code Quality Fixes Regression Tests
Tests for:
1. Backend health - All core API endpoints respond correctly
2. XSS fix verification - DOMPurify sanitization (frontend tests via Playwright)
3. Settings page tabs visibility
4. System Health page metrics
5. System Logs page and filters
6. API Documentation page
7. Dashboard page
8. Journeys list page
9. Quality criteria page
10. Refactored modules: evidence_scoring.py, middleware.py, system_routes.py
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEV_EMAIL = "dev@me.mx"
DEV_PASSWORD = "LastMile2026"
AGENT_EMAIL = "agente@me.mx"
AGENT_PASSWORD = "LastMile2026"


class TestAuthentication:
    """Test authentication endpoints"""
    
    def test_login_developer(self):
        """Test developer login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEV_EMAIL,
            "password": DEV_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "Missing access_token in response"
        assert "user" in data, "Missing user in response"
        assert data["user"]["role"] == "developer", f"Expected developer role, got {data['user']['role']}"
    
    def test_login_agent(self):
        """Test agent login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": AGENT_EMAIL,
            "password": AGENT_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "agent"


@pytest.fixture(scope="module")
def dev_token():
    """Get developer auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEV_EMAIL,
        "password": DEV_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Developer authentication failed")


@pytest.fixture(scope="module")
def agent_token():
    """Get agent auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": AGENT_EMAIL,
        "password": AGENT_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Agent authentication failed")


class TestSystemHealth:
    """Test system health endpoints - verifies system_routes.py refactoring"""
    
    def test_system_health_endpoint(self, dev_token):
        """GET /api/system/health - Returns health metrics"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/system/health", headers=headers)
        assert response.status_code == 200, f"Health check failed: {response.text}"
        data = response.json()
        
        # Verify expected fields
        assert "api_status" in data, "Missing api_status"
        assert "mongo_status" in data, "Missing mongo_status"
        assert "mongo_latency_ms" in data, "Missing mongo_latency_ms"
        assert "avg_latency_ms" in data, "Missing avg_latency_ms"
        assert "errors_4xx_24h" in data, "Missing errors_4xx_24h"
        assert "errors_5xx_24h" in data, "Missing errors_5xx_24h"
        assert "uptime" in data, "Missing uptime"
        assert "timestamp" in data, "Missing timestamp"
        
        # Verify values
        assert data["api_status"] == "ok", f"API status not ok: {data['api_status']}"
        assert data["mongo_status"] == "connected", f"MongoDB not connected: {data['mongo_status']}"
    
    def test_system_performance_endpoint(self, dev_token):
        """GET /api/system/performance - Returns performance metrics"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/system/performance", headers=headers)
        assert response.status_code == 200, f"Performance check failed: {response.text}"
        data = response.json()
        
        # Verify expected fields
        assert "requests_per_hour" in data, "Missing requests_per_hour"
        assert "slowest_endpoints" in data, "Missing slowest_endpoints"
        assert "active_users" in data, "Missing active_users"
    
    def test_system_config_endpoint(self, dev_token):
        """GET /api/system/config - Returns system configuration"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/system/config", headers=headers)
        assert response.status_code == 200, f"Config check failed: {response.text}"
        data = response.json()
        
        # Verify expected fields
        assert "backend_version" in data, "Missing backend_version"
        assert "python_version" in data, "Missing python_version"
        assert "mongo_host" in data, "Missing mongo_host"
        assert "uptime" in data, "Missing uptime"


class TestSystemLogs:
    """Test system logs endpoints - verifies middleware.py refactoring"""
    
    def test_audit_logs_endpoint(self, dev_token):
        """GET /api/system/logs - Returns audit logs with pagination"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/system/logs", headers=headers, params={
            "page": 1,
            "page_size": 10
        })
        assert response.status_code == 200, f"Logs fetch failed: {response.text}"
        data = response.json()
        
        # Verify pagination structure
        assert "logs" in data, "Missing logs array"
        assert "total" in data, "Missing total count"
        assert "page" in data, "Missing page number"
        assert "page_size" in data, "Missing page_size"
        assert "total_pages" in data, "Missing total_pages"
    
    def test_audit_logs_filter_by_action(self, dev_token):
        """GET /api/system/logs with action filter"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/system/logs", headers=headers, params={
            "action": "login_attempt",
            "page_size": 5
        })
        assert response.status_code == 200, f"Logs filter failed: {response.text}"
        data = response.json()
        assert "logs" in data
    
    def test_log_action_types(self, dev_token):
        """GET /api/system/logs/actions - Returns available action types"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/system/logs/actions", headers=headers)
        assert response.status_code == 200, f"Action types fetch failed: {response.text}"
        data = response.json()
        assert "actions" in data, "Missing actions list"
        assert isinstance(data["actions"], list), "Actions should be a list"


class TestSystemErrors:
    """Test system errors endpoints"""
    
    def test_system_errors_endpoint(self, dev_token):
        """GET /api/system/errors - Returns system errors"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/system/errors", headers=headers)
        assert response.status_code == 200, f"Errors fetch failed: {response.text}"
        data = response.json()
        assert "errors" in data, "Missing errors array"
    
    def test_unreviewed_error_count(self, dev_token):
        """GET /api/system/errors/count - Returns unreviewed error count"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/system/errors/count", headers=headers)
        assert response.status_code == 200, f"Error count failed: {response.text}"
        data = response.json()
        assert "count" in data, "Missing count field"
        assert isinstance(data["count"], int), "Count should be integer"


class TestDashboard:
    """Test dashboard endpoints"""
    
    def test_dashboard_stats(self, dev_token):
        """GET /api/dashboard/stats - Returns dashboard statistics"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=headers)
        assert response.status_code == 200, f"Dashboard stats failed: {response.text}"
        data = response.json()
        
        # Verify expected fields
        assert "total_journeys" in data or "journeys_today" in data, "Missing journey stats"


class TestWebhooks:
    """Test webhooks endpoints"""
    
    def test_webhook_events(self, dev_token):
        """GET /api/webhooks/events - Returns available webhook events"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/webhooks/events", headers=headers)
        assert response.status_code == 200, f"Webhook events failed: {response.text}"
        data = response.json()
        assert "events" in data, "Missing events array"
        assert len(data["events"]) >= 7, f"Expected at least 7 events, got {len(data['events'])}"
    
    def test_webhooks_list(self, dev_token):
        """GET /api/webhooks - Returns webhooks list"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/webhooks", headers=headers)
        assert response.status_code == 200, f"Webhooks list failed: {response.text}"
        data = response.json()
        # Response is a list directly or wrapped in 'webhooks'
        assert isinstance(data, list) or "webhooks" in data, "Invalid webhooks response"


class TestJourneys:
    """Test journeys endpoints"""
    
    def test_journeys_list(self, dev_token):
        """GET /api/journeys - Returns journeys list"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/journeys", headers=headers)
        assert response.status_code == 200, f"Journeys list failed: {response.text}"
        data = response.json()
        # Response has 'data' array with pagination
        assert "data" in data or "journeys" in data, "Missing journeys data"
        if "data" in data:
            assert "pagination" in data, "Missing pagination"


class TestQualityCriteria:
    """Test quality criteria endpoints"""
    
    def test_quality_criteria(self, dev_token):
        """GET /api/quality/criteria - Returns quality criteria"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/quality/criteria", headers=headers)
        assert response.status_code == 200, f"Quality criteria failed: {response.text}"
        data = response.json()
        # Should return criteria data
        assert data is not None, "Quality criteria response is empty"
    
    def test_quality_settings(self, dev_token):
        """GET /api/config/quality-settings - Returns quality settings"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/config/quality-settings", headers=headers)
        assert response.status_code == 200, f"Quality settings failed: {response.text}"


class TestReports:
    """Test reports endpoints"""
    
    def test_quality_report(self, dev_token):
        """GET /api/reports/quality - Returns quality report"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/reports/quality", headers=headers)
        assert response.status_code == 200, f"Quality report failed: {response.text}"
    
    def test_reports_journeys(self, dev_token):
        """GET /api/reports/journeys - Returns journeys report"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/reports/journeys", headers=headers)
        assert response.status_code == 200, f"Journeys report failed: {response.text}"
    
    def test_reports_kpis(self, dev_token):
        """GET /api/reports/kpis - Returns KPIs report"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/reports/kpis", headers=headers, params={
            "group_by": "day"
        })
        assert response.status_code == 200, f"KPIs report failed: {response.text}"


class TestSyncStatus:
    """Test sync status endpoints"""
    
    def test_sync_status(self, dev_token):
        """GET /api/sync/status - Returns sync status"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/sync/status", headers=headers)
        assert response.status_code == 200, f"Sync status failed: {response.text}"
        data = response.json()
        # Verify expected fields
        assert "last_sync" in data or "status" in data, "Missing sync status fields"


class TestAdminModule:
    """Test admin module endpoints"""
    
    def test_admin_summary(self, dev_token):
        """GET /api/admin/summary - Returns admin summary"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/summary", headers=headers)
        assert response.status_code == 200, f"Admin summary failed: {response.text}"


class TestLumiChat:
    """Test Lumi chat endpoint"""
    
    def test_lumi_chat_endpoint_exists(self, dev_token):
        """POST /api/chat/lumi - Endpoint exists and responds"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.post(f"{BASE_URL}/api/chat/lumi", headers=headers, json={
            "message": "Hola",
            "history": [],
            "period": "7d"
        })
        # Endpoint should exist (200 or 500 if no data, but not 404)
        assert response.status_code != 404, "Lumi chat endpoint not found"


class TestUsersEndpoints:
    """Test users endpoints"""
    
    def test_users_list(self, dev_token):
        """GET /api/users - Returns users list"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/users", headers=headers)
        assert response.status_code == 200, f"Users list failed: {response.text}"
        data = response.json()
        # Response is a list directly or wrapped in 'users'
        assert isinstance(data, list) or "users" in data, "Invalid users response"


class TestClientsProviders:
    """Test clients and providers endpoints"""
    
    def test_clients_list(self, dev_token):
        """GET /api/clients - Returns clients list"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/clients", headers=headers)
        assert response.status_code == 200, f"Clients list failed: {response.text}"
    
    def test_providers_list(self, dev_token):
        """GET /api/providers - Returns providers list"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/providers", headers=headers)
        assert response.status_code == 200, f"Providers list failed: {response.text}"


class TestAgentPermissions:
    """Test that agent role has correct permissions"""
    
    def test_agent_cannot_access_system_health(self, agent_token):
        """Agent should not access system health (403)"""
        headers = {"Authorization": f"Bearer {agent_token}"}
        response = requests.get(f"{BASE_URL}/api/system/health", headers=headers)
        assert response.status_code == 403, f"Agent should not access system health, got {response.status_code}"
    
    def test_agent_cannot_access_webhooks_crud(self, agent_token):
        """Agent should not access webhooks CRUD (403)"""
        headers = {"Authorization": f"Bearer {agent_token}"}
        response = requests.get(f"{BASE_URL}/api/webhooks", headers=headers)
        assert response.status_code == 403, f"Agent should not access webhooks, got {response.status_code}"
    
    def test_agent_can_view_journeys(self, agent_token):
        """Agent should be able to view journeys"""
        headers = {"Authorization": f"Bearer {agent_token}"}
        response = requests.get(f"{BASE_URL}/api/journeys", headers=headers)
        assert response.status_code == 200, f"Agent should access journeys, got {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
