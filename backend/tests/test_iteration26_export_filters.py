"""
Iteration 26 - Export Filters Bug Fixes Testing

Tests for:
1. Reports Excel export (POST /api/reports/generate-excel) - client_id and provider_id filters
2. System Logs CSV export (GET /api/system/logs/export) - errors_only filter
3. Reports generate endpoint (POST /api/reports/generate) - client_id and provider_id filters
4. Admin Routes Report export (GET /api/admin/routes-report/export) - all filters
5. Quality report export (POST /api/reports/quality-export)
6. Heatmap export (POST /api/analytics/heatmap-export)
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://lastmile-mvp.preview.emergentagent.com')

# Test credentials
DEV_EMAIL = os.environ.get('TEST_DEV_EMAIL', 'dev@me.mx')
DEV_PASSWORD = os.environ.get('TEST_DEV_PASSWORD', 'LastMile2026')
COORD_EMAIL = os.environ.get('TEST_COORD_EMAIL', 'yael@me.mx')
COORD_PASSWORD = os.environ.get('TEST_COORD_PASSWORD', 'LastMile2026')


@pytest.fixture(scope="module")
def dev_token():
    """Get developer auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEV_EMAIL,
        "password": DEV_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Developer login failed: {response.status_code}")


@pytest.fixture(scope="module")
def coord_token():
    """Get coordinator auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": COORD_EMAIL,
        "password": COORD_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Coordinator login failed: {response.status_code}")


@pytest.fixture(scope="module")
def test_dates():
    """Get date range for testing"""
    today = datetime.now()
    date_from = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    date_to = today.strftime("%Y-%m-%d")
    return {"date_from": date_from, "date_to": date_to}


@pytest.fixture(scope="module")
def clients_and_providers(dev_token):
    """Get available clients and providers for filter testing"""
    headers = {"Authorization": f"Bearer {dev_token}"}
    
    clients_res = requests.get(f"{BASE_URL}/api/clients", headers=headers)
    providers_res = requests.get(f"{BASE_URL}/api/providers", headers=headers)
    
    # API returns list directly or dict with "data" key
    clients_data = clients_res.json() if clients_res.status_code == 200 else []
    providers_data = providers_res.json() if providers_res.status_code == 200 else []
    
    # Handle both list and dict responses
    clients = clients_data if isinstance(clients_data, list) else clients_data.get("data", [])
    providers = providers_data if isinstance(providers_data, list) else providers_data.get("data", [])
    
    return {
        "client_id": clients[0]["id"] if clients else None,
        "provider_id": providers[0]["id"] if providers else None,
        "clients": clients,
        "providers": providers
    }


class TestReportsGenerateEndpoint:
    """Test POST /api/reports/generate with client_id and provider_id filters"""
    
    def test_generate_report_without_filters(self, dev_token, test_dates):
        """Test report generation without filters"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        payload = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "sections": ["providers", "drivers", "incidents"]
        }
        
        response = requests.post(f"{BASE_URL}/api/reports/generate", json=payload, headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "period" in data or "total_journeys" in data or "error" in data
        print(f"✓ Report generated without filters: {data.get('total_journeys', 0)} journeys")
    
    def test_generate_report_with_client_filter(self, dev_token, test_dates, clients_and_providers):
        """BUG FIX 3: Test report generation with client_id filter"""
        if not clients_and_providers["client_id"]:
            pytest.skip("No clients available for testing")
        
        headers = {"Authorization": f"Bearer {dev_token}"}
        payload = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "sections": ["providers"],
            "client_id": clients_and_providers["client_id"]
        }
        
        response = requests.post(f"{BASE_URL}/api/reports/generate", json=payload, headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        print(f"✓ Report with client_id filter: {data.get('total_journeys', 0)} journeys")
    
    def test_generate_report_with_provider_filter(self, dev_token, test_dates, clients_and_providers):
        """BUG FIX 3: Test report generation with provider_id filter"""
        if not clients_and_providers["provider_id"]:
            pytest.skip("No providers available for testing")
        
        headers = {"Authorization": f"Bearer {dev_token}"}
        payload = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "sections": ["providers"],
            "provider_id": clients_and_providers["provider_id"]
        }
        
        response = requests.post(f"{BASE_URL}/api/reports/generate", json=payload, headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        print(f"✓ Report with provider_id filter: {data.get('total_journeys', 0)} journeys")
    
    def test_generate_report_with_both_filters(self, dev_token, test_dates, clients_and_providers):
        """BUG FIX 3: Test report generation with both client_id and provider_id filters"""
        if not clients_and_providers["client_id"] or not clients_and_providers["provider_id"]:
            pytest.skip("No clients or providers available for testing")
        
        headers = {"Authorization": f"Bearer {dev_token}"}
        payload = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "sections": ["providers", "drivers"],
            "client_id": clients_and_providers["client_id"],
            "provider_id": clients_and_providers["provider_id"]
        }
        
        response = requests.post(f"{BASE_URL}/api/reports/generate", json=payload, headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        print(f"✓ Report with both filters: {data.get('total_journeys', 0)} journeys")


class TestReportsExcelExport:
    """Test POST /api/reports/generate-excel with client_id and provider_id filters"""
    
    def test_excel_export_without_filters(self, dev_token, test_dates):
        """Test Excel export without filters"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        payload = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "sections": ["providers"]
        }
        
        response = requests.post(f"{BASE_URL}/api/reports/generate-excel", json=payload, headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify it's an Excel file
        content_type = response.headers.get("content-type", "")
        assert "spreadsheet" in content_type or "octet-stream" in content_type or len(response.content) > 0
        print(f"✓ Excel export without filters: {len(response.content)} bytes")
    
    def test_excel_export_with_client_filter(self, dev_token, test_dates, clients_and_providers):
        """BUG FIX 1: Test Excel export with client_id filter"""
        if not clients_and_providers["client_id"]:
            pytest.skip("No clients available for testing")
        
        headers = {"Authorization": f"Bearer {dev_token}"}
        payload = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "sections": ["providers"],
            "client_id": clients_and_providers["client_id"]
        }
        
        response = requests.post(f"{BASE_URL}/api/reports/generate-excel", json=payload, headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Excel export with client_id filter: {len(response.content)} bytes")
    
    def test_excel_export_with_provider_filter(self, dev_token, test_dates, clients_and_providers):
        """BUG FIX 1: Test Excel export with provider_id filter"""
        if not clients_and_providers["provider_id"]:
            pytest.skip("No providers available for testing")
        
        headers = {"Authorization": f"Bearer {dev_token}"}
        payload = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "sections": ["providers"],
            "provider_id": clients_and_providers["provider_id"]
        }
        
        response = requests.post(f"{BASE_URL}/api/reports/generate-excel", json=payload, headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Excel export with provider_id filter: {len(response.content)} bytes")
    
    def test_excel_export_with_both_filters(self, dev_token, test_dates, clients_and_providers):
        """BUG FIX 1: Test Excel export with both client_id and provider_id filters"""
        if not clients_and_providers["client_id"] or not clients_and_providers["provider_id"]:
            pytest.skip("No clients or providers available for testing")
        
        headers = {"Authorization": f"Bearer {dev_token}"}
        payload = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "sections": ["providers", "drivers"],
            "client_id": clients_and_providers["client_id"],
            "provider_id": clients_and_providers["provider_id"]
        }
        
        response = requests.post(f"{BASE_URL}/api/reports/generate-excel", json=payload, headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Excel export with both filters: {len(response.content)} bytes")


class TestSystemLogsExport:
    """Test GET /api/system/logs/export with errors_only filter"""
    
    def test_logs_export_without_filters(self, dev_token):
        """Test logs export without filters"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        
        response = requests.get(f"{BASE_URL}/api/system/logs/export", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify it's a CSV file
        content_type = response.headers.get("content-type", "")
        assert "csv" in content_type or "text" in content_type or len(response.content) > 0
        print(f"✓ Logs export without filters: {len(response.content)} bytes")
    
    def test_logs_export_with_date_filters(self, dev_token, test_dates):
        """Test logs export with date filters"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"]
        }
        
        response = requests.get(f"{BASE_URL}/api/system/logs/export", headers=headers, params=params)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Logs export with date filters: {len(response.content)} bytes")
    
    def test_logs_export_with_action_filter(self, dev_token):
        """Test logs export with action filter"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {"action": "login_success"}
        
        response = requests.get(f"{BASE_URL}/api/system/logs/export", headers=headers, params=params)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Logs export with action filter: {len(response.content)} bytes")
    
    def test_logs_export_with_errors_only_filter(self, dev_token):
        """BUG FIX 2: Test logs export with errors_only filter"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {"errors_only": "true"}
        
        response = requests.get(f"{BASE_URL}/api/system/logs/export", headers=headers, params=params)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Logs export with errors_only filter: {len(response.content)} bytes")
    
    def test_logs_export_with_all_filters(self, dev_token, test_dates):
        """BUG FIX 2: Test logs export with all filters combined"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "action": "login_failed",
            "errors_only": "true"
        }
        
        response = requests.get(f"{BASE_URL}/api/system/logs/export", headers=headers, params=params)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Logs export with all filters: {len(response.content)} bytes")


class TestAdminRoutesReportExport:
    """Test GET /api/admin/routes-report/export with all filters"""
    
    def test_routes_report_export_basic(self, dev_token, test_dates):
        """Test routes report export with basic date filters"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"]
        }
        
        response = requests.get(f"{BASE_URL}/api/admin/routes-report/export", headers=headers, params=params)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Routes report export basic: {len(response.content)} bytes")
    
    def test_routes_report_export_with_driver_filter(self, dev_token, test_dates):
        """Test routes report export with driver filter"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "driver": "test"
        }
        
        response = requests.get(f"{BASE_URL}/api/admin/routes-report/export", headers=headers, params=params)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Routes report export with driver filter: {len(response.content)} bytes")
    
    def test_routes_report_export_with_team_filter(self, dev_token, test_dates):
        """Test routes report export with team filter"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "team": "CDMX"
        }
        
        response = requests.get(f"{BASE_URL}/api/admin/routes-report/export", headers=headers, params=params)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Routes report export with team filter: {len(response.content)} bytes")
    
    def test_routes_report_export_with_provider_filter(self, dev_token, test_dates, clients_and_providers):
        """Test routes report export with provider_id filter"""
        if not clients_and_providers["provider_id"]:
            pytest.skip("No providers available for testing")
        
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "provider_id": clients_and_providers["provider_id"]
        }
        
        response = requests.get(f"{BASE_URL}/api/admin/routes-report/export", headers=headers, params=params)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Routes report export with provider_id filter: {len(response.content)} bytes")
    
    def test_routes_report_export_with_status_filter(self, dev_token, test_dates):
        """Test routes report export with status filter"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "status": "closed"
        }
        
        response = requests.get(f"{BASE_URL}/api/admin/routes-report/export", headers=headers, params=params)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Routes report export with status filter: {len(response.content)} bytes")
    
    def test_routes_report_export_with_columns_filter(self, dev_token, test_dates):
        """Test routes report export with columns filter"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "columns": "order_id,fecha,driver,proveedor,total_paquetes,completados"
        }
        
        response = requests.get(f"{BASE_URL}/api/admin/routes-report/export", headers=headers, params=params)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Routes report export with columns filter: {len(response.content)} bytes")
    
    def test_routes_report_export_with_all_filters(self, dev_token, test_dates, clients_and_providers):
        """Test routes report export with all filters combined"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "status": "closed",
            "columns": "order_id,fecha,driver,proveedor"
        }
        if clients_and_providers["provider_id"]:
            params["provider_id"] = clients_and_providers["provider_id"]
        
        response = requests.get(f"{BASE_URL}/api/admin/routes-report/export", headers=headers, params=params)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Routes report export with all filters: {len(response.content)} bytes")


class TestQualityReportExport:
    """Test POST /api/reports/quality-export"""
    
    def test_quality_export_basic(self, dev_token, test_dates):
        """Test quality report export with basic date filters"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        
        # Use form data for this endpoint
        data = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"]
        }
        
        response = requests.post(f"{BASE_URL}/api/reports/quality-export", headers=headers, data=data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Quality export basic: {len(response.content)} bytes")
    
    def test_quality_export_with_provider_filter(self, dev_token, test_dates, clients_and_providers):
        """Test quality report export with provider_id filter"""
        if not clients_and_providers["provider_id"]:
            pytest.skip("No providers available for testing")
        
        headers = {"Authorization": f"Bearer {dev_token}"}
        data = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "provider_id": clients_and_providers["provider_id"]
        }
        
        response = requests.post(f"{BASE_URL}/api/reports/quality-export", headers=headers, data=data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Quality export with provider_id filter: {len(response.content)} bytes")


class TestHeatmapExport:
    """Test POST /api/analytics/heatmap-export"""
    
    def test_heatmap_export_basic(self, dev_token, test_dates):
        """Test heatmap export with basic date filters"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"]
        }
        
        response = requests.post(f"{BASE_URL}/api/analytics/heatmap-export", headers=headers, params=params)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Heatmap export basic: {len(response.content)} bytes")
    
    def test_heatmap_export_with_group_by(self, dev_token, test_dates):
        """Test heatmap export with group_by filter"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "group_by": "address_municipio"
        }
        
        response = requests.post(f"{BASE_URL}/api/analytics/heatmap-export", headers=headers, params=params)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Heatmap export with group_by filter: {len(response.content)} bytes")


class TestSystemLogsEndpoint:
    """Test GET /api/system/logs with errors_only filter"""
    
    def test_logs_with_errors_only_filter(self, dev_token):
        """BUG FIX 2: Test logs endpoint with errors_only filter"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {"errors_only": "true", "page": 1, "page_size": 10}
        
        response = requests.get(f"{BASE_URL}/api/system/logs", headers=headers, params=params)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "logs" in data
        assert "total" in data
        print(f"✓ Logs with errors_only filter: {data.get('total', 0)} total logs")
    
    def test_logs_with_all_filters(self, dev_token, test_dates):
        """Test logs endpoint with all filters"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {
            "date_from": test_dates["date_from"],
            "date_to": test_dates["date_to"],
            "action": "login_success",
            "errors_only": "false",
            "page": 1,
            "page_size": 10
        }
        
        response = requests.get(f"{BASE_URL}/api/system/logs", headers=headers, params=params)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "logs" in data
        print(f"✓ Logs with all filters: {data.get('total', 0)} total logs")
