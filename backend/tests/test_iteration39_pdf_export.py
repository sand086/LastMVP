"""
Iteration 39 - PDF Export Redesign Tests
Tests for the new multi-page PDF export using jsPDF + jspdf-autotable

Features tested:
1. Reports page API endpoints (GET /api/reports, POST /api/reports/generate-ai)
2. All supporting data endpoints for PDF generation
3. Excel export still works
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_session():
    """Module-scoped fixture for authenticated session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login as coordinator
    login_response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "yael@me.mx",
        "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
    })
    assert login_response.status_code == 200, f"Login failed: {login_response.text}"
    token = login_response.json().get("access_token")  # Fixed: access_token not token
    session.headers.update({"Authorization": f"Bearer {token}"})
    
    return session


class TestReportsAPIForPDFExport:
    """Tests for Reports API endpoints used by PDF export"""
    
    # Use 15d period to get existing data (journeys from 2026-03-27 to 2026-04-09)
    date_from = "2026-03-27"
    date_to = "2026-04-10"
    
    def test_health_check(self, auth_session):
        """Test API health endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✓ Health check passed")
    
    def test_reports_generate_endpoint(self, auth_session):
        """Test POST /api/reports/generate - main report data for PDF"""
        response = auth_session.post(f"{BASE_URL}/api/reports/generate", json={
            "date_from": self.date_from,
            "date_to": self.date_to,
            "sections": ["providers", "drivers", "incidents", "attempts", "quality", "sla"]
        })
        assert response.status_code == 200, f"Reports generate failed: {response.text}"
        data = response.json()
        
        # Verify response structure for PDF generation
        assert "delivery_rate" in data, "Missing delivery_rate"
        assert "total_packages" in data, "Missing total_packages"
        assert "total_delivered" in data, "Missing total_delivered"
        assert "total_failed" in data, "Missing total_failed"
        assert "provider_metrics" in data, "Missing provider_metrics"
        assert "driver_metrics" in data, "Missing driver_metrics"
        
        print(f"✓ Reports generate: delivery_rate={data.get('delivery_rate')}%, total_packages={data.get('total_packages')}")
    
    def test_reports_quality_endpoint(self, auth_session):
        """Test GET /api/reports/quality - quality data for PDF"""
        response = auth_session.get(f"{BASE_URL}/api/reports/quality", params={
            "date_from": self.date_from,
            "date_to": self.date_to
        })
        assert response.status_code == 200, f"Quality report failed: {response.text}"
        data = response.json()
        
        # Verify quality data structure
        assert "summary" in data, "Missing summary in quality data"
        summary = data.get("summary", {})
        print(f"✓ Quality report: avg_score={summary.get('avg_score', 0)}%, total_evaluated={summary.get('total_evaluated', 0)}")
    
    def test_reports_attempts_endpoint(self, auth_session):
        """Test GET /api/reports/attempts - attempts data for PDF"""
        response = auth_session.get(f"{BASE_URL}/api/reports/attempts", params={
            "date_from": self.date_from,
            "date_to": self.date_to
        })
        assert response.status_code == 200, f"Attempts report failed: {response.text}"
        data = response.json()
        
        # Verify attempts data structure
        assert "first_attempt" in data, "Missing first_attempt"
        assert "second_attempt" in data, "Missing second_attempt"
        assert "third_attempt" in data, "Missing third_attempt"
        
        print(f"✓ Attempts report: first={data.get('first_attempt', {}).get('count', 0)}, second={data.get('second_attempt', {}).get('count', 0)}")
    
    def test_reports_sla_endpoint(self, auth_session):
        """Test GET /api/reports/sla - SLA data for PDF"""
        response = auth_session.get(f"{BASE_URL}/api/reports/sla", params={
            "date_from": self.date_from,
            "date_to": self.date_to
        })
        assert response.status_code == 200, f"SLA report failed: {response.text}"
        data = response.json()
        
        # Verify SLA data structure
        assert "consolidated" in data, "Missing consolidated SLA"
        consolidated = data.get("consolidated", {})
        assert "actual" in consolidated, "Missing actual SLA"
        assert "target" in consolidated, "Missing target SLA"
        
        print(f"✓ SLA report: actual={consolidated.get('actual')}%, target={consolidated.get('target')}%")
    
    def test_reports_generate_ai_endpoint(self, auth_session):
        """Test POST /api/reports/generate-ai - AI analysis for PDF"""
        response = auth_session.post(f"{BASE_URL}/api/reports/generate-ai", json={
            "date_from": self.date_from,
            "date_to": self.date_to
        })
        assert response.status_code == 200, f"AI report failed: {response.text}"
        data = response.json()
        
        # Verify AI response structure
        assert "narrative" in data, "Missing narrative in AI response"
        assert "cards" in data, "Missing cards in AI response"
        
        cards = data.get("cards", [])
        print(f"✓ AI report: narrative_length={len(data.get('narrative', ''))}, cards_count={len(cards)}")
        
        # Verify card structure if cards exist
        if cards:
            card = cards[0]
            assert "tipo" in card, "Card missing tipo"
            assert "titulo" in card, "Card missing titulo"
            assert "cuerpo" in card, "Card missing cuerpo"
    
    def test_clients_endpoint(self, auth_session):
        """Test GET /api/clients - for filter dropdown"""
        response = auth_session.get(f"{BASE_URL}/api/clients")
        assert response.status_code == 200, f"Clients endpoint failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Clients should return a list"
        print(f"✓ Clients endpoint: {len(data)} clients")
    
    def test_providers_endpoint(self, auth_session):
        """Test GET /api/providers - for filter dropdown"""
        response = auth_session.get(f"{BASE_URL}/api/providers")
        assert response.status_code == 200, f"Providers endpoint failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Providers should return a list"
        print(f"✓ Providers endpoint: {len(data)} providers")
    
    def test_excel_export_endpoint(self, auth_session):
        """Test POST /api/reports/generate-excel - Excel export still works"""
        response = auth_session.post(f"{BASE_URL}/api/reports/generate-excel", json={
            "date_from": self.date_from,
            "date_to": self.date_to,
            "sections": ["providers", "drivers", "incidents"]
        })
        assert response.status_code == 200, f"Excel export failed: {response.text}"
        
        # Verify it returns binary data (Excel file)
        content_type = response.headers.get("Content-Type", "")
        assert "spreadsheet" in content_type or "octet-stream" in content_type or len(response.content) > 0, \
            f"Excel export should return binary data, got content-type: {content_type}"
        
        print(f"✓ Excel export: {len(response.content)} bytes")
    
    def test_reports_page_data_completeness(self, auth_session):
        """Test that all data needed for PDF export is available"""
        # Fetch all data in parallel (simulating what Reports.jsx does)
        report_res = auth_session.post(f"{BASE_URL}/api/reports/generate", json={
            "date_from": self.date_from,
            "date_to": self.date_to,
            "sections": ["providers", "drivers", "incidents", "attempts", "quality", "sla"]
        })
        quality_res = auth_session.get(f"{BASE_URL}/api/reports/quality", params={
            "date_from": self.date_from,
            "date_to": self.date_to
        })
        attempts_res = auth_session.get(f"{BASE_URL}/api/reports/attempts", params={
            "date_from": self.date_from,
            "date_to": self.date_to
        })
        sla_res = auth_session.get(f"{BASE_URL}/api/reports/sla", params={
            "date_from": self.date_from,
            "date_to": self.date_to
        })
        
        # All should succeed
        assert report_res.status_code == 200, "Report generate failed"
        assert quality_res.status_code == 200, "Quality report failed"
        assert attempts_res.status_code == 200, "Attempts report failed"
        assert sla_res.status_code == 200, "SLA report failed"
        
        report_data = report_res.json()
        quality_data = quality_res.json()
        attempts_res.json()
        sla_data = sla_res.json()
        
        # Verify data exists for PDF pages
        has_providers = len(report_data.get("provider_metrics", {})) > 0
        has_drivers = len(report_data.get("driver_metrics", {})) > 0
        has_incidents = len(report_data.get("incidents_by_type", {})) > 0
        has_quality = quality_data.get("summary", {}).get("total_evaluated", 0) > 0
        has_sla = sla_data.get("consolidated", {}).get("actual") is not None
        
        print("✓ PDF data completeness check:")
        print(f"  - Providers: {'✓' if has_providers else '✗'}")
        print(f"  - Drivers: {'✓' if has_drivers else '✗'}")
        print(f"  - Incidents: {'✓' if has_incidents else '✗'}")
        print(f"  - Quality: {'✓' if has_quality else '✗'}")
        print(f"  - SLA: {'✓' if has_sla else '✗'}")
        
        # At least some data should exist for the 15d period
        assert has_providers or has_drivers, "Should have provider or driver data for 15d period"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
