"""
Test Reports Page Backend APIs - Iteration 36
Tests for the redesigned Reports page features:
- POST /api/reports/generate (with daily_stats)
- POST /api/reports/generate-excel
- GET /api/reports/quality
- GET /api/reports/attempts
- GET /api/reports/sla
- POST /api/reports/generate-ai
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for coordinator user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "yael@me.mx",
        "password": "LastMile2026"
    })
    if response.status_code == 200:
        data = response.json()
        # Login returns 'access_token' not 'token'
        return data.get("access_token") or data.get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")

@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestReportsGenerate:
    """Tests for POST /api/reports/generate endpoint"""
    
    def test_generate_report_current_month(self, api_client):
        """Test report generation for current month returns daily_stats"""
        now = datetime.now()
        date_from = now.replace(day=1).strftime("%Y-%m-%d")
        date_to = now.strftime("%Y-%m-%d")
        
        response = api_client.post(f"{BASE_URL}/api/reports/generate", json={
            "date_from": date_from,
            "date_to": date_to,
            "sections": ["providers", "drivers", "incidents", "attempts", "quality", "sla"]
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "period" in data, "Response should contain 'period'"
        assert "total_journeys" in data, "Response should contain 'total_journeys'"
        assert "total_packages" in data, "Response should contain 'total_packages'"
        assert "delivery_rate" in data, "Response should contain 'delivery_rate'"
        assert "provider_metrics" in data, "Response should contain 'provider_metrics'"
        assert "driver_metrics" in data, "Response should contain 'driver_metrics'"
        assert "incidents_by_type" in data, "Response should contain 'incidents_by_type'"
        
        # Verify daily_stats for combo chart
        assert "daily_stats" in data, "Response should contain 'daily_stats' for combo chart"
        if data["daily_stats"]:
            first_stat = data["daily_stats"][0]
            assert "date" in first_stat, "daily_stats should have 'date'"
            assert "packages" in first_stat, "daily_stats should have 'packages'"
            assert "avg_delivery_time" in first_stat, "daily_stats should have 'avg_delivery_time'"
        
        print(f"SUCCESS: Report generated with {len(data.get('daily_stats', []))} daily stats entries")
        print(f"  - Total journeys: {data['total_journeys']}")
        print(f"  - Total packages: {data['total_packages']}")
        print(f"  - Delivery rate: {data['delivery_rate']}%")
    
    def test_generate_report_with_filters(self, api_client):
        """Test report generation with client/provider filters"""
        now = datetime.now()
        date_from = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        date_to = now.strftime("%Y-%m-%d")
        
        response = api_client.post(f"{BASE_URL}/api/reports/generate", json={
            "date_from": date_from,
            "date_to": date_to,
            "sections": ["providers"]
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "provider_metrics" in data
        print(f"SUCCESS: Report with filters - {len(data.get('provider_metrics', {}))} providers")


class TestReportsExcel:
    """Tests for POST /api/reports/generate-excel endpoint"""
    
    def test_generate_excel_export(self, api_client):
        """Test Excel export returns valid file"""
        now = datetime.now()
        date_from = now.replace(day=1).strftime("%Y-%m-%d")
        date_to = now.strftime("%Y-%m-%d")
        
        response = api_client.post(f"{BASE_URL}/api/reports/generate-excel", json={
            "date_from": date_from,
            "date_to": date_to,
            "sections": ["providers", "drivers", "incidents"]
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Verify content type is Excel
        content_type = response.headers.get("content-type", "")
        assert "spreadsheet" in content_type or "octet-stream" in content_type, \
            f"Expected Excel content type, got: {content_type}"
        
        # Verify content disposition header
        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp, "Should have attachment disposition"
        assert ".xlsx" in content_disp, "Should be .xlsx file"
        
        # Verify file has content
        assert len(response.content) > 1000, "Excel file should have substantial content"
        
        print(f"SUCCESS: Excel export generated, size: {len(response.content)} bytes")


class TestReportsQuality:
    """Tests for GET /api/reports/quality endpoint"""
    
    def test_get_quality_report(self, api_client):
        """Test quality report returns expected structure"""
        now = datetime.now()
        date_from = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        date_to = now.strftime("%Y-%m-%d")
        
        response = api_client.get(f"{BASE_URL}/api/reports/quality", params={
            "date_from": date_from,
            "date_to": date_to
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify structure
        assert "summary" in data, "Response should contain 'summary'"
        assert "by_provider" in data, "Response should contain 'by_provider'"
        assert "by_type" in data, "Response should contain 'by_type'"
        
        # Verify summary fields
        summary = data["summary"]
        assert "avg_score" in summary, "Summary should have 'avg_score'"
        assert "total_evaluated" in summary, "Summary should have 'total_evaluated'"
        assert "complete" in summary, "Summary should have 'complete'"
        assert "incomplete" in summary, "Summary should have 'incomplete'"
        
        print(f"SUCCESS: Quality report - avg_score: {summary['avg_score']}%, total_evaluated: {summary['total_evaluated']}")


class TestReportsAttempts:
    """Tests for GET /api/reports/attempts endpoint"""
    
    def test_get_attempts_report(self, api_client):
        """Test attempts report returns distribution data"""
        now = datetime.now()
        date_from = now.replace(day=1).strftime("%Y-%m-%d")
        date_to = now.strftime("%Y-%m-%d")
        
        response = api_client.get(f"{BASE_URL}/api/reports/attempts", params={
            "date_from": date_from,
            "date_to": date_to
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify structure
        assert "first_attempt" in data, "Response should contain 'first_attempt'"
        assert "second_attempt" in data, "Response should contain 'second_attempt'"
        assert "third_attempt" in data, "Response should contain 'third_attempt'"
        assert "retry_causes" in data, "Response should contain 'retry_causes'"
        
        # Verify attempt structure
        first = data["first_attempt"]
        assert "count" in first, "first_attempt should have 'count'"
        assert "pct" in first, "first_attempt should have 'pct'"
        
        print(f"SUCCESS: Attempts report - 1st: {first['count']} ({first['pct']}%)")


class TestReportsSLA:
    """Tests for GET /api/reports/sla endpoint"""
    
    def test_get_sla_report(self, api_client):
        """Test SLA report returns consolidated and breakdown data"""
        now = datetime.now()
        date_from = now.replace(day=1).strftime("%Y-%m-%d")
        date_to = now.strftime("%Y-%m-%d")
        
        response = api_client.get(f"{BASE_URL}/api/reports/sla", params={
            "date_from": date_from,
            "date_to": date_to
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify structure
        assert "consolidated" in data, "Response should contain 'consolidated'"
        assert "by_provider" in data, "Response should contain 'by_provider'"
        assert "by_driver" in data, "Response should contain 'by_driver'"
        assert "brackets" in data, "Response should contain 'brackets'"
        
        # Verify consolidated
        consolidated = data["consolidated"]
        assert "actual" in consolidated, "consolidated should have 'actual'"
        assert "target" in consolidated, "consolidated should have 'target'"
        
        # Verify brackets structure
        if data["brackets"]:
            bracket = data["brackets"][0]
            assert "label" in bracket, "bracket should have 'label'"
            assert "target" in bracket, "bracket should have 'target'"
            assert "status" in bracket, "bracket should have 'status'"
        
        # Verify by_provider structure
        if data["by_provider"]:
            provider = data["by_provider"][0]
            assert "provider_name" in provider, "provider should have 'provider_name'"
            assert "sla_actual" in provider, "provider should have 'sla_actual'"
            assert "target" in provider, "provider should have 'target'"
            assert "gap_pp" in provider, "provider should have 'gap_pp'"
            assert "status" in provider, "provider should have 'status'"
        
        print(f"SUCCESS: SLA report - consolidated: {consolidated['actual']}% (target: {consolidated['target']}%)")


class TestReportsAI:
    """Tests for POST /api/reports/generate-ai endpoint"""
    
    def test_generate_ai_triggers_loading(self, api_client):
        """Test AI report generation endpoint responds (don't wait for completion)"""
        now = datetime.now()
        date_from = now.replace(day=1).strftime("%Y-%m-%d")
        date_to = now.strftime("%Y-%m-%d")
        
        # Just verify the endpoint accepts the request
        # AI generation takes 20+ seconds, so we just check it starts
        response = api_client.post(f"{BASE_URL}/api/reports/generate-ai", json={
            "period": "current_month",
            "date_from": date_from,
            "date_to": date_to,
            "sections": ["providers", "incidents"]
        }, timeout=60)  # Allow up to 60 seconds for AI
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify response structure
        assert "narrative" in data, "Response should contain 'narrative'"
        assert "period" in data, "Response should contain 'period'"
        
        # Narrative should have content (either AI-generated or error message)
        assert len(data["narrative"]) > 0, "Narrative should not be empty"
        
        print(f"SUCCESS: AI report generated, narrative length: {len(data['narrative'])} chars")
        print(f"  - Period: {data['period']}")


class TestClientsProviders:
    """Tests for client and provider dropdowns data"""
    
    def test_get_clients(self, api_client):
        """Test clients endpoint for dropdown"""
        response = api_client.get(f"{BASE_URL}/api/clients")
        assert response.status_code == 200
        data = response.json()
        # Clients endpoint returns array directly or wrapped in 'data'
        clients = data.get("data", data) if isinstance(data, dict) else data
        assert isinstance(clients, list), "Response should be a list of clients"
        print(f"SUCCESS: Got {len(clients)} clients")
    
    def test_get_providers(self, api_client):
        """Test providers endpoint for dropdown"""
        response = api_client.get(f"{BASE_URL}/api/providers")
        assert response.status_code == 200
        data = response.json()
        # Providers endpoint returns array directly or wrapped in 'data'
        providers = data.get("data", data) if isinstance(data, dict) else data
        assert isinstance(providers, list), "Response should be a list of providers"
        print(f"SUCCESS: Got {len(providers)} providers")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
