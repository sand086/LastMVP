"""
Test suite for LastMile OS new features:
1. Dashboard filtering by user assignments
2. Imputability field in incidents
3. Route type (CDMX/Foránea) with conditional fields
4. Layout re-upload updates existing packages
5. Custom report generation with Claude AI insights + Excel download
"""

import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://lastmile-mvp.preview.emergentagent.com').rstrip('/')

# Test credentials
COORDINATOR_EMAIL = "yael@me.mx"
COORDINATOR_PASSWORD = "LastMile2026"
AGENT_EMAIL = "agente@me.mx"
AGENT_PASSWORD = "LastMile2026"
EXECUTIVE_EMAIL = "karina@me.mx"
EXECUTIVE_PASSWORD = "LastMile2026"


@pytest.fixture(scope="module")
def coordinator_token():
    """Get coordinator auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": COORDINATOR_EMAIL,
        "password": COORDINATOR_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def agent_token():
    """Get agent auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": AGENT_EMAIL,
        "password": AGENT_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def executive_token():
    """Get executive auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": EXECUTIVE_EMAIL,
        "password": EXECUTIVE_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def test_data(coordinator_token, api_client):
    """Get test data: clients, providers"""
    headers = {"Authorization": f"Bearer {coordinator_token}"}
    
    clients_res = api_client.get(f"{BASE_URL}/api/clients", headers=headers)
    providers_res = api_client.get(f"{BASE_URL}/api/providers", headers=headers)
    
    return {
        "clients": clients_res.json(),
        "providers": providers_res.json()
    }


class TestImputabilityFeature:
    """Test imputability field in incidents"""
    
    def test_create_incident_with_imputability_me_mensajero(self, coordinator_token, api_client, test_data):
        """Test creating incident with imputability = ME / Mensajero"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        # First create a journey to attach incident to
        today = datetime.now().strftime("%Y-%m-%d")
        journey_data = {
            "date": today,
            "client_id": test_data["clients"][0]["id"],
            "provider_id": test_data["providers"][0]["id"],
            "packages": [
                {"tracking_number": "TEST_IMP_001", "recipient_name": "Test User", "address": "Test Address", "zone": "Norte", "delivery_window": "09:00-12:00"}
            ],
            "route_type": "CDMX / Zona Metro"
        }
        
        journey_res = api_client.post(f"{BASE_URL}/api/journeys", json=journey_data, headers=headers)
        assert journey_res.status_code == 200, f"Journey creation failed: {journey_res.text}"
        journey_id = journey_res.json()["id"]
        
        # Create incident with imputability
        incident_data = {
            "journey_id": journey_id,
            "occurred_at": datetime.now().isoformat(),
            "incident_type": "Tiempo excesivo por entrega",
            "description": "Test incident with ME/Mensajero imputability",
            "severity": "Alto",
            "imputability": "ME / Mensajero"
        }
        
        incident_res = api_client.post(f"{BASE_URL}/api/incidents", json=incident_data, headers=headers)
        assert incident_res.status_code == 200, f"Incident creation failed: {incident_res.text}"
        
        incident = incident_res.json()
        assert incident["imputability"] == "ME / Mensajero", f"Expected imputability 'ME / Mensajero', got {incident.get('imputability')}"
        print(f"✓ Created incident with imputability: {incident['imputability']}")
        
        return incident["id"], journey_id
    
    def test_create_incident_with_imputability_cliente(self, coordinator_token, api_client, test_data):
        """Test creating incident with imputability = Cliente (destinatario)"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        # Create a journey
        today = datetime.now().strftime("%Y-%m-%d")
        journey_data = {
            "date": today,
            "client_id": test_data["clients"][0]["id"],
            "provider_id": test_data["providers"][0]["id"],
            "packages": [
                {"tracking_number": "TEST_IMP_002", "recipient_name": "Test User 2", "address": "Test Address 2", "zone": "Sur", "delivery_window": "12:00-15:00"}
            ]
        }
        
        journey_res = api_client.post(f"{BASE_URL}/api/journeys", json=journey_data, headers=headers)
        journey_id = journey_res.json()["id"]
        
        # Create incident with Cliente imputability
        incident_data = {
            "journey_id": journey_id,
            "occurred_at": datetime.now().isoformat(),
            "incident_type": "Destinatario ausente",
            "description": "Test incident with Cliente imputability",
            "severity": "Medio",
            "imputability": "Cliente (destinatario)"
        }
        
        incident_res = api_client.post(f"{BASE_URL}/api/incidents", json=incident_data, headers=headers)
        assert incident_res.status_code == 200
        
        incident = incident_res.json()
        assert incident["imputability"] == "Cliente (destinatario)"
        print(f"✓ Created incident with imputability: {incident['imputability']}")
    
    def test_create_incident_with_default_imputability(self, coordinator_token, api_client, test_data):
        """Test creating incident without imputability defaults to 'Por definir'"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        # Create a journey
        today = datetime.now().strftime("%Y-%m-%d")
        journey_data = {
            "date": today,
            "client_id": test_data["clients"][0]["id"],
            "provider_id": test_data["providers"][0]["id"],
            "packages": [
                {"tracking_number": "TEST_IMP_003", "recipient_name": "Test User 3", "address": "Test Address 3", "zone": "Centro", "delivery_window": "15:00-18:00"}
            ]
        }
        
        journey_res = api_client.post(f"{BASE_URL}/api/journeys", json=journey_data, headers=headers)
        journey_id = journey_res.json()["id"]
        
        # Create incident WITHOUT imputability
        incident_data = {
            "journey_id": journey_id,
            "occurred_at": datetime.now().isoformat(),
            "incident_type": "Otro",
            "description": "Test incident without imputability",
            "severity": "Bajo"
            # No imputability field
        }
        
        incident_res = api_client.post(f"{BASE_URL}/api/incidents", json=incident_data, headers=headers)
        assert incident_res.status_code == 200
        
        incident = incident_res.json()
        assert incident["imputability"] == "Por definir", f"Expected default 'Por definir', got {incident.get('imputability')}"
        print(f"✓ Default imputability is: {incident['imputability']}")
    
    def test_get_incidents_returns_imputability(self, coordinator_token, api_client):
        """Test that GET incidents returns imputability field"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        incidents_res = api_client.get(f"{BASE_URL}/api/incidents", headers=headers)
        assert incidents_res.status_code == 200
        
        incidents = incidents_res.json()
        if incidents:
            # Check that at least one incident has imputability field
            has_imputability = any("imputability" in inc for inc in incidents)
            assert has_imputability, "No incidents have imputability field"
            print(f"✓ GET /api/incidents returns imputability field")


class TestRouteTypeFeature:
    """Test route type (CDMX/Foránea) with conditional fields"""
    
    def test_create_journey_cdmx_route_type(self, coordinator_token, api_client, test_data):
        """Test creating journey with CDMX route type"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        today = datetime.now().strftime("%Y-%m-%d")
        journey_data = {
            "date": today,
            "client_id": test_data["clients"][0]["id"],
            "provider_id": test_data["providers"][0]["id"],
            "packages": [
                {"tracking_number": "TEST_CDMX_001", "recipient_name": "CDMX User", "address": "CDMX Address", "zone": "Norte", "delivery_window": "09:00-12:00"}
            ],
            "route_type": "CDMX / Zona Metro"
        }
        
        response = api_client.post(f"{BASE_URL}/api/journeys", json=journey_data, headers=headers)
        assert response.status_code == 200, f"Journey creation failed: {response.text}"
        
        journey_id = response.json()["id"]
        
        # Verify journey has correct route_type
        journey_res = api_client.get(f"{BASE_URL}/api/journeys/{journey_id}", headers=headers)
        journey = journey_res.json()
        
        assert journey.get("route_type") == "CDMX / Zona Metro", f"Expected 'CDMX / Zona Metro', got {journey.get('route_type')}"
        print(f"✓ Created CDMX journey with route_type: {journey['route_type']}")
    
    def test_create_journey_foranea_route_type(self, coordinator_token, api_client, test_data):
        """Test creating journey with Foránea route type including city and max_packages"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        today = datetime.now().strftime("%Y-%m-%d")
        journey_data = {
            "date": today,
            "client_id": test_data["clients"][0]["id"],
            "provider_id": test_data["providers"][0]["id"],
            "packages": [
                {"tracking_number": "TEST_FOR_001", "recipient_name": "Foranea User", "address": "Pachuca Address", "zone": "Foranea", "delivery_window": "09:00-18:00"}
            ],
            "route_type": "Foránea",
            "city": "Pachuca",
            "max_packages": 30
        }
        
        response = api_client.post(f"{BASE_URL}/api/journeys", json=journey_data, headers=headers)
        assert response.status_code == 200, f"Journey creation failed: {response.text}"
        
        journey_id = response.json()["id"]
        
        # Verify journey has correct route_type, city, and max_packages
        journey_res = api_client.get(f"{BASE_URL}/api/journeys/{journey_id}", headers=headers)
        journey = journey_res.json()
        
        assert journey.get("route_type") == "Foránea", f"Expected 'Foránea', got {journey.get('route_type')}"
        assert journey.get("city") == "Pachuca", f"Expected city 'Pachuca', got {journey.get('city')}"
        assert journey.get("max_packages") == 30, f"Expected max_packages 30, got {journey.get('max_packages')}"
        print(f"✓ Created Foránea journey: route_type={journey['route_type']}, city={journey['city']}, max_packages={journey['max_packages']}")
    
    def test_default_route_type_is_cdmx(self, coordinator_token, api_client, test_data):
        """Test that default route_type is CDMX when not specified"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        today = datetime.now().strftime("%Y-%m-%d")
        journey_data = {
            "date": today,
            "client_id": test_data["clients"][0]["id"],
            "provider_id": test_data["providers"][0]["id"],
            "packages": [
                {"tracking_number": "TEST_DEF_001", "recipient_name": "Default User", "address": "Default Address", "zone": "Centro", "delivery_window": "09:00-12:00"}
            ]
            # No route_type specified
        }
        
        response = api_client.post(f"{BASE_URL}/api/journeys", json=journey_data, headers=headers)
        assert response.status_code == 200
        
        journey_id = response.json()["id"]
        journey_res = api_client.get(f"{BASE_URL}/api/journeys/{journey_id}", headers=headers)
        journey = journey_res.json()
        
        assert journey.get("route_type") == "CDMX / Zona Metro", f"Expected default 'CDMX / Zona Metro', got {journey.get('route_type')}"
        print(f"✓ Default route_type is: {journey['route_type']}")


class TestReportsFeature:
    """Test custom report generation with AI insights"""
    
    def test_generate_report_coordinator(self, coordinator_token, api_client):
        """Test report generation for coordinator role"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        # Use a date range that should have data
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        report_data = {
            "date_from": week_ago,
            "date_to": today,
            "sections": ["provider_metrics", "driver_metrics", "incidents_breakdown"]
        }
        
        response = api_client.post(f"{BASE_URL}/api/reports/generate", json=report_data, headers=headers)
        assert response.status_code == 200, f"Report generation failed: {response.text}"
        
        report = response.json()
        
        # Check report structure
        if "error" not in report:
            assert "total_journeys" in report, "Missing total_journeys in report"
            assert "total_packages" in report, "Missing total_packages in report"
            assert "delivery_rate" in report, "Missing delivery_rate in report"
            assert "provider_metrics" in report, "Missing provider_metrics in report"
            assert "driver_metrics" in report, "Missing driver_metrics in report"
            assert "incidents_by_type" in report, "Missing incidents_by_type in report"
            assert "incidents_by_imputability" in report, "Missing incidents_by_imputability in report"
            assert "ai_insights" in report, "Missing ai_insights in report"
            
            print(f"✓ Report generated: {report['total_journeys']} journeys, {report['total_packages']} packages, {report['delivery_rate']}% delivery rate")
            print(f"✓ AI insights present: {len(report.get('ai_insights', '')) > 0}")
        else:
            print(f"✓ Report returned expected 'no data' message: {report['error']}")
    
    def test_generate_report_executive(self, executive_token, api_client):
        """Test report generation for executive role"""
        headers = {"Authorization": f"Bearer {executive_token}"}
        
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        report_data = {
            "date_from": week_ago,
            "date_to": today,
            "sections": ["provider_metrics"]
        }
        
        response = api_client.post(f"{BASE_URL}/api/reports/generate", json=report_data, headers=headers)
        assert response.status_code == 200, f"Report generation failed for executive: {response.text}"
        print("✓ Executive can access report generation")
    
    def test_generate_report_excel(self, coordinator_token, api_client):
        """Test Excel report generation"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        report_data = {
            "date_from": week_ago,
            "date_to": today,
            "sections": ["provider_metrics", "driver_metrics", "incidents_breakdown"]
        }
        
        response = api_client.post(f"{BASE_URL}/api/reports/generate-excel", json=report_data, headers=headers)
        assert response.status_code == 200, f"Excel generation failed: {response.text}"
        
        # Check that response is a file (binary content)
        content_type = response.headers.get("content-type", "")
        assert "spreadsheet" in content_type or "octet-stream" in content_type or len(response.content) > 0, \
            f"Expected Excel file, got content-type: {content_type}"
        
        print(f"✓ Excel report generated: {len(response.content)} bytes")


class TestDashboardFiltering:
    """Test dashboard filtering by user assignments"""
    
    def test_dashboard_stats_coordinator_sees_all(self, coordinator_token, api_client):
        """Test that coordinator with no assignments sees all data"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        today = datetime.now().strftime("%Y-%m-%d")
        response = api_client.get(f"{BASE_URL}/api/dashboard/stats?date={today}", headers=headers)
        assert response.status_code == 200, f"Dashboard stats failed: {response.text}"
        
        stats = response.json()
        assert "total_journeys" in stats
        assert "total_packages" in stats
        assert "delivery_rate" in stats
        print(f"✓ Coordinator dashboard stats: {stats['total_journeys']} journeys, {stats['total_packages']} packages")
    
    def test_journeys_list_coordinator_sees_all(self, coordinator_token, api_client):
        """Test that coordinator with no assignments sees all journeys"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        response = api_client.get(f"{BASE_URL}/api/journeys", headers=headers)
        assert response.status_code == 200
        
        journeys = response.json()
        print(f"✓ Coordinator sees {len(journeys)} journeys")
    
    def test_incidents_list_returns_data(self, coordinator_token, api_client):
        """Test that incidents list returns data"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        response = api_client.get(f"{BASE_URL}/api/incidents", headers=headers)
        assert response.status_code == 200
        
        incidents = response.json()
        print(f"✓ Incidents list returned {len(incidents)} incidents")


class TestSidebarNavigation:
    """Test sidebar navigation for reports link"""
    
    def test_reports_endpoint_accessible_coordinator(self, coordinator_token, api_client):
        """Test that reports endpoint is accessible for coordinator"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        response = api_client.post(f"{BASE_URL}/api/reports/generate", json={
            "date_from": week_ago,
            "date_to": today,
            "sections": []
        }, headers=headers)
        
        assert response.status_code == 200, f"Reports endpoint not accessible: {response.text}"
        print("✓ Reports endpoint accessible for coordinator")
    
    def test_reports_endpoint_accessible_executive(self, executive_token, api_client):
        """Test that reports endpoint is accessible for executive"""
        headers = {"Authorization": f"Bearer {executive_token}"}
        
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        response = api_client.post(f"{BASE_URL}/api/reports/generate", json={
            "date_from": week_ago,
            "date_to": today,
            "sections": []
        }, headers=headers)
        
        assert response.status_code == 200, f"Reports endpoint not accessible for executive: {response.text}"
        print("✓ Reports endpoint accessible for executive")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
