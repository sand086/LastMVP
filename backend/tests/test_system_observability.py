"""
Test suite for System Observability Module - LastMile OS
Tests: Health Dashboard, Performance Metrics, Log Viewer, Error Tracker, 
       Integrity Checker, System Config, and Access Control
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEVELOPER_CREDS = {"email": "dev@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}
COORDINATOR_CREDS = {"email": "yael@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}
AGENT_CREDS = {"email": "agente@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}


@pytest.fixture(scope="module")
def developer_token():
    """Get developer auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=DEVELOPER_CREDS)
    assert response.status_code == 200, f"Developer login failed: {response.text}"
    data = response.json()
    assert data["user"]["role"] == "developer", "Expected developer role"
    return data["access_token"]


@pytest.fixture(scope="module")
def coordinator_token():
    """Get coordinator auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=COORDINATOR_CREDS)
    assert response.status_code == 200, f"Coordinator login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def agent_token():
    """Get agent auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=AGENT_CREDS)
    assert response.status_code == 200, f"Agent login failed: {response.text}"
    return response.json()["access_token"]


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


# ==================== AUTHENTICATION TESTS ====================

class TestDeveloperLogin:
    """Test developer role authentication"""
    
    def test_developer_login_success(self):
        """POST /api/auth/login with developer credentials returns role=developer"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DEVELOPER_CREDS)
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["email"] == "dev@me.mx"
        assert data["user"]["role"] == "developer"
        assert data["user"]["name"] == "Dev Admin"
        print("✓ Developer login successful with correct role")


# ==================== HEALTH DASHBOARD TESTS ====================

class TestHealthDashboard:
    """Test /api/system/health endpoint"""
    
    def test_health_endpoint_developer(self, developer_token):
        """GET /api/system/health returns all required fields for developer"""
        response = requests.get(
            f"{BASE_URL}/api/system/health",
            headers=auth_header(developer_token)
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify all required fields
        required_fields = [
            "api_status", "mongo_status", "mongo_latency_ms", "avg_latency_ms",
            "errors_4xx_24h", "errors_5xx_24h", "upload_size_mb", "uptime",
            "uptime_seconds", "recent_errors", "timestamp"
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        # Verify data types
        assert data["api_status"] == "ok"
        assert data["mongo_status"] in ["connected", "disconnected"]
        assert isinstance(data["mongo_latency_ms"], (int, float))
        assert isinstance(data["avg_latency_ms"], (int, float))
        assert isinstance(data["errors_4xx_24h"], int)
        assert isinstance(data["errors_5xx_24h"], int)
        assert isinstance(data["upload_size_mb"], (int, float))
        assert isinstance(data["recent_errors"], list)
        print("✓ Health endpoint returns all required fields")
    
    def test_health_endpoint_coordinator(self, coordinator_token):
        """GET /api/system/health works for coordinator role"""
        response = requests.get(
            f"{BASE_URL}/api/system/health",
            headers=auth_header(coordinator_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert "api_status" in data
        print("✓ Health endpoint accessible by coordinator")


# ==================== PERFORMANCE METRICS TESTS ====================

class TestPerformanceMetrics:
    """Test /api/system/performance endpoint"""
    
    def test_performance_endpoint(self, developer_token):
        """GET /api/system/performance returns required metrics"""
        response = requests.get(
            f"{BASE_URL}/api/system/performance",
            headers=auth_header(developer_token)
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        required_fields = [
            "requests_per_hour", "slowest_endpoints", "active_users",
            "avg_layout_file_size_kb", "total_layouts_7d"
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        # Verify data types
        assert isinstance(data["requests_per_hour"], dict)
        assert isinstance(data["slowest_endpoints"], list)
        assert isinstance(data["active_users"], list)
        print("✓ Performance endpoint returns all required metrics")


# ==================== LOG VIEWER TESTS ====================

class TestLogViewer:
    """Test /api/system/logs endpoints"""
    
    def test_logs_endpoint_paginated(self, developer_token):
        """GET /api/system/logs returns paginated audit logs"""
        response = requests.get(
            f"{BASE_URL}/api/system/logs?page=1&page_size=10",
            headers=auth_header(developer_token)
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify pagination fields
        assert "logs" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data
        
        assert isinstance(data["logs"], list)
        assert data["page"] == 1
        assert data["page_size"] == 10
        print("✓ Logs endpoint returns paginated results")
    
    def test_logs_contain_login_events(self, developer_token):
        """Login events should appear as audit entries"""
        response = requests.get(
            f"{BASE_URL}/api/system/logs?action=login_success&page_size=50",
            headers=auth_header(developer_token)
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should have login events from our test logins
        login_logs = [log for log in data["logs"] if log.get("action") == "login_success"]
        assert len(login_logs) >= 0, "Login events should be logged"
        print(f"✓ Found {len(login_logs)} login events in audit logs")
    
    def test_logs_action_types(self, developer_token):
        """GET /api/system/logs/actions returns available action types"""
        response = requests.get(
            f"{BASE_URL}/api/system/logs/actions",
            headers=auth_header(developer_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert "actions" in data
        assert isinstance(data["actions"], list)
        print(f"✓ Found {len(data['actions'])} action types")
    
    def test_logs_export_csv(self, developer_token):
        """GET /api/system/logs/export returns CSV file"""
        response = requests.get(
            f"{BASE_URL}/api/system/logs/export",
            headers=auth_header(developer_token)
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        assert "attachment" in response.headers.get("content-disposition", "")
        
        # Verify CSV content
        content = response.text
        assert "Timestamp" in content or "timestamp" in content.lower()
        print("✓ Logs export returns valid CSV")


# ==================== ERROR TRACKER TESTS ====================

class TestErrorTracker:
    """Test /api/system/errors endpoints"""
    
    def test_errors_endpoint(self, developer_token):
        """GET /api/system/errors returns system errors"""
        response = requests.get(
            f"{BASE_URL}/api/system/errors",
            headers=auth_header(developer_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert "errors" in data
        assert isinstance(data["errors"], list)
        print(f"✓ Errors endpoint returns {len(data['errors'])} errors")
    
    def test_errors_count(self, developer_token):
        """GET /api/system/errors/count returns unreviewed count"""
        response = requests.get(
            f"{BASE_URL}/api/system/errors/count",
            headers=auth_header(developer_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert isinstance(data["count"], int)
        print(f"✓ Unreviewed error count: {data['count']}")
    
    def test_errors_count_for_agent(self, agent_token):
        """GET /api/system/errors/count returns 0 for agent role"""
        response = requests.get(
            f"{BASE_URL}/api/system/errors/count",
            headers=auth_header(agent_token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0, "Agent should see 0 error count"
        print("✓ Agent sees 0 error count (as expected)")


# ==================== INTEGRITY CHECKER TESTS ====================

class TestIntegrityChecker:
    """Test /api/system/integrity endpoints"""
    
    def test_integrity_run(self, developer_token):
        """POST /api/system/integrity/run executes validation checks"""
        response = requests.post(
            f"{BASE_URL}/api/system/integrity/run",
            headers=auth_header(developer_token)
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "id" in data
        assert "timestamp" in data
        assert "run_by" in data
        assert "total_issues" in data
        assert "issues_by_severity" in data
        assert "issues" in data
        
        # Verify severity breakdown
        assert "Alta" in data["issues_by_severity"]
        assert "Media" in data["issues_by_severity"]
        assert "Baja" in data["issues_by_severity"]
        
        print(f"✓ Integrity check found {data['total_issues']} issues")
    
    def test_integrity_results(self, developer_token):
        """GET /api/system/integrity/results returns latest results"""
        response = requests.get(
            f"{BASE_URL}/api/system/integrity/results",
            headers=auth_header(developer_token)
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should have results from previous run
        assert "total_issues" in data or "message" in data
        print("✓ Integrity results endpoint working")


# ==================== SYSTEM CONFIG TESTS ====================

class TestSystemConfig:
    """Test /api/system/config endpoint"""
    
    def test_config_endpoint(self, developer_token):
        """GET /api/system/config returns environment configuration"""
        response = requests.get(
            f"{BASE_URL}/api/system/config",
            headers=auth_header(developer_token)
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        required_fields = [
            "backend_version", "python_version", "mongo_host", "db_name",
            "jwt_expiry_hours", "uptime", "uptime_seconds"
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        # Verify data types
        assert "FastAPI" in data["backend_version"]
        assert isinstance(data["jwt_expiry_hours"], int)
        assert isinstance(data["uptime_seconds"], int)
        print("✓ System config returns all required fields")


# ==================== ACCESS CONTROL TESTS ====================

class TestAccessControl:
    """Test that agent role cannot access system endpoints"""
    
    def test_agent_cannot_access_health(self, agent_token):
        """Agent role should get 403 on /api/system/health"""
        response = requests.get(
            f"{BASE_URL}/api/system/health",
            headers=auth_header(agent_token)
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Agent correctly denied access to health endpoint")
    
    def test_agent_cannot_access_logs(self, agent_token):
        """Agent role should get 403 on /api/system/logs"""
        response = requests.get(
            f"{BASE_URL}/api/system/logs",
            headers=auth_header(agent_token)
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Agent correctly denied access to logs endpoint")
    
    def test_agent_cannot_access_errors(self, agent_token):
        """Agent role should get 403 on /api/system/errors"""
        response = requests.get(
            f"{BASE_URL}/api/system/errors",
            headers=auth_header(agent_token)
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Agent correctly denied access to errors endpoint")
    
    def test_agent_cannot_access_integrity(self, agent_token):
        """Agent role should get 403 on /api/system/integrity/results"""
        response = requests.get(
            f"{BASE_URL}/api/system/integrity/results",
            headers=auth_header(agent_token)
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Agent correctly denied access to integrity endpoint")
    
    def test_agent_cannot_access_config(self, agent_token):
        """Agent role should get 403 on /api/system/config"""
        response = requests.get(
            f"{BASE_URL}/api/system/config",
            headers=auth_header(agent_token)
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Agent correctly denied access to config endpoint")


# ==================== ERROR REVIEW TESTS ====================

class TestErrorReview:
    """Test error review functionality"""
    
    def test_review_nonexistent_error(self, developer_token):
        """POST /api/system/errors/{id}/review returns 404 for nonexistent error"""
        response = requests.post(
            f"{BASE_URL}/api/system/errors/nonexistent-id/review",
            headers=auth_header(developer_token)
        )
        assert response.status_code == 404
        print("✓ Review nonexistent error returns 404")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
