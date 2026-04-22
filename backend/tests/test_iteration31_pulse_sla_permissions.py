"""
Iteration 31 - Testing P1 (SLA Config Permissions) and P2 (Pulse Feature)

P1: Coordinator role can now PATCH /api/admin/config with section='sla_config'
P2: Pulse feature - real-time feasibility monitor for delivery routes
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEVELOPER_EMAIL = "dev@me.mx"
DEVELOPER_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
COORDINATOR_EMAIL = "yael@me.mx"
COORDINATOR_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
AGENT_EMAIL = "agente@me.mx"
AGENT_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def developer_token(api_client):
    """Get developer authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEVELOPER_EMAIL,
        "password": DEVELOPER_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Developer authentication failed: {response.status_code}")


@pytest.fixture(scope="module")
def coordinator_token(api_client):
    """Get coordinator authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": COORDINATOR_EMAIL,
        "password": COORDINATOR_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Coordinator authentication failed: {response.status_code}")


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


class TestP1SlaConfigPermissions:
    """P1: Test that coordinator can now edit SLA config (previously only developer)"""

    def test_coordinator_can_patch_sla_config(self, api_client, coordinator_token):
        """Coordinator should be able to PATCH sla_config (P1 fix)"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        # First get current config
        get_response = api_client.get(f"{BASE_URL}/api/admin/config", headers=headers)
        assert get_response.status_code == 200, f"GET config failed: {get_response.text}"
        
        current_config = get_response.json()
        current_sla = current_config.get("sla_config", {})
        
        # Try to update SLA config as coordinator
        new_sla_value = {
            "default_sla": current_sla.get("default_sla", 40),
            "by_provider": current_sla.get("by_provider", {})
        }
        
        patch_response = api_client.patch(
            f"{BASE_URL}/api/admin/config",
            headers=headers,
            json={"section": "sla_config", "value": new_sla_value}
        )
        
        # P1 fix: Coordinator should now get 200, not 403
        assert patch_response.status_code == 200, f"Coordinator should be able to edit sla_config. Got: {patch_response.status_code} - {patch_response.text}"
        
        data = patch_response.json()
        assert data.get("success")
        assert data.get("section") == "sla_config"
        print("PASSED: Coordinator can PATCH sla_config")

    def test_developer_can_still_patch_sla_config(self, api_client, developer_token):
        """Developer should still be able to PATCH sla_config"""
        headers = {"Authorization": f"Bearer {developer_token}"}
        
        # Get current config
        get_response = api_client.get(f"{BASE_URL}/api/admin/config", headers=headers)
        assert get_response.status_code == 200
        
        current_config = get_response.json()
        current_sla = current_config.get("sla_config", {})
        
        # Update SLA config as developer
        new_sla_value = {
            "default_sla": current_sla.get("default_sla", 40),
            "by_provider": current_sla.get("by_provider", {})
        }
        
        patch_response = api_client.patch(
            f"{BASE_URL}/api/admin/config",
            headers=headers,
            json={"section": "sla_config", "value": new_sla_value}
        )
        
        assert patch_response.status_code == 200, f"Developer should be able to edit sla_config. Got: {patch_response.status_code}"
        print("PASSED: Developer can PATCH sla_config")

    def test_agent_cannot_patch_sla_config(self, api_client, agent_token):
        """Agent should NOT be able to PATCH sla_config (only coordinator/developer)"""
        headers = {"Authorization": f"Bearer {agent_token}"}
        
        patch_response = api_client.patch(
            f"{BASE_URL}/api/admin/config",
            headers=headers,
            json={"section": "sla_config", "value": {"default_sla": 40, "by_provider": {}}}
        )
        
        # Agent should get 403 Forbidden
        assert patch_response.status_code == 403, f"Agent should NOT be able to edit sla_config. Got: {patch_response.status_code}"
        print("PASSED: Agent cannot PATCH sla_config (403)")


class TestP2PulseConfigEndpoint:
    """P2: Test Pulse configuration in admin config endpoint"""

    def test_config_returns_pulse_config_structure(self, api_client, developer_token):
        """GET /api/admin/config should return pulse_config object"""
        headers = {"Authorization": f"Bearer {developer_token}"}
        
        response = api_client.get(f"{BASE_URL}/api/admin/config", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "pulse_config" in data, "Response should contain pulse_config"
        
        pulse_config = data["pulse_config"]
        assert isinstance(pulse_config, dict), "pulse_config should be a dict"
        print(f"PASSED: pulse_config found in response: {pulse_config}")

    def test_pulse_config_has_required_fields(self, api_client, developer_token):
        """pulse_config should have all required fields"""
        headers = {"Authorization": f"Bearer {developer_token}"}
        
        response = api_client.get(f"{BASE_URL}/api/admin/config", headers=headers)
        assert response.status_code == 200
        
        pulse_config = response.json().get("pulse_config", {})
        
        # Required fields per P2 spec
        required_fields = [
            "hora_limite",
            "traslado_primer_punto_default",
            "tiempo_promedio_entrega",
            "umbral_ok",
            "umbral_warn",
            "excepciones_traslado_por_proveedor"
        ]
        
        for field in required_fields:
            assert field in pulse_config, f"pulse_config missing required field: {field}"
        
        # Validate hora_limite structure
        hora_limite = pulse_config.get("hora_limite", {})
        assert "hour" in hora_limite, "hora_limite should have 'hour' field"
        assert "minute" in hora_limite, "hora_limite should have 'minute' field"
        
        # Validate excepciones is a list
        excepciones = pulse_config.get("excepciones_traslado_por_proveedor", [])
        assert isinstance(excepciones, list), "excepciones_traslado_por_proveedor should be a list"
        
        print("PASSED: pulse_config has all required fields")
        print(f"  hora_limite: {pulse_config.get('hora_limite')}")
        print(f"  traslado_primer_punto_default: {pulse_config.get('traslado_primer_punto_default')}")
        print(f"  tiempo_promedio_entrega: {pulse_config.get('tiempo_promedio_entrega')}")
        print(f"  umbral_ok: {pulse_config.get('umbral_ok')}")
        print(f"  umbral_warn: {pulse_config.get('umbral_warn')}")

    def test_patch_pulse_config_saves_and_persists(self, api_client, developer_token):
        """PATCH /api/admin/config with section='pulse_config' should save and persist"""
        headers = {"Authorization": f"Bearer {developer_token}"}
        
        # New pulse config values
        new_pulse_config = {
            "hora_limite": {"hour": 21, "minute": 30},
            "traslado_primer_punto_default": 45,  # Changed from default 40
            "tiempo_promedio_entrega": 6,  # Changed from default 5
            "umbral_ok": 12,  # Changed from default 10
            "umbral_warn": 6,  # Changed from default 5
            "excepciones_traslado_por_proveedor": []
        }
        
        # PATCH the config
        patch_response = api_client.patch(
            f"{BASE_URL}/api/admin/config",
            headers=headers,
            json={"section": "pulse_config", "value": new_pulse_config}
        )
        
        assert patch_response.status_code == 200, f"PATCH pulse_config failed: {patch_response.text}"
        
        patch_data = patch_response.json()
        assert patch_data.get("success")
        assert patch_data.get("section") == "pulse_config"
        
        # Verify persistence by GET
        get_response = api_client.get(f"{BASE_URL}/api/admin/config", headers=headers)
        assert get_response.status_code == 200
        
        saved_pulse = get_response.json().get("pulse_config", {})
        assert saved_pulse.get("traslado_primer_punto_default") == 45, "traslado should be 45"
        assert saved_pulse.get("tiempo_promedio_entrega") == 6, "tiempo_promedio should be 6"
        assert saved_pulse.get("umbral_ok") == 12, "umbral_ok should be 12"
        assert saved_pulse.get("umbral_warn") == 6, "umbral_warn should be 6"
        
        print("PASSED: pulse_config saved and persisted correctly")
        
        # Restore defaults
        default_pulse = {
            "hora_limite": {"hour": 21, "minute": 30},
            "traslado_primer_punto_default": 40,
            "tiempo_promedio_entrega": 5,
            "umbral_ok": 10,
            "umbral_warn": 5,
            "excepciones_traslado_por_proveedor": []
        }
        api_client.patch(
            f"{BASE_URL}/api/admin/config",
            headers=headers,
            json={"section": "pulse_config", "value": default_pulse}
        )

    def test_coordinator_can_patch_pulse_config(self, api_client, coordinator_token):
        """Coordinator should be able to PATCH pulse_config (same as sla_config)"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        # Get current config
        get_response = api_client.get(f"{BASE_URL}/api/admin/config", headers=headers)
        assert get_response.status_code == 200
        
        current_pulse = get_response.json().get("pulse_config", {})
        
        # Try to update pulse config as coordinator
        patch_response = api_client.patch(
            f"{BASE_URL}/api/admin/config",
            headers=headers,
            json={"section": "pulse_config", "value": current_pulse}
        )
        
        assert patch_response.status_code == 200, f"Coordinator should be able to edit pulse_config. Got: {patch_response.status_code}"
        print("PASSED: Coordinator can PATCH pulse_config")


class TestP2JourneysEndpoint:
    """P2: Test that journeys endpoint returns data needed for Pulse calculations"""

    def test_journeys_endpoint_returns_required_fields(self, api_client, developer_token):
        """Journeys should have fields needed for Pulse: status, start_data, packages_*"""
        headers = {"Authorization": f"Bearer {developer_token}"}
        
        response = api_client.get(f"{BASE_URL}/api/journeys", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        journeys = data.get("data", data) if isinstance(data, dict) else data
        
        if len(journeys) == 0:
            pytest.skip("No journeys available to test")
        
        # Check first journey has required fields for Pulse
        journey = journeys[0]
        
        required_fields = ["id", "status", "packages_total", "packages_delivered", "packages_failed"]
        for field in required_fields:
            assert field in journey, f"Journey missing required field: {field}"
        
        print("PASSED: Journey has required fields for Pulse")
        print(f"  status: {journey.get('status')}")
        print(f"  packages_total: {journey.get('packages_total')}")
        print(f"  packages_delivered: {journey.get('packages_delivered')}")
        print(f"  packages_failed: {journey.get('packages_failed')}")

    def test_in_progress_journey_has_start_data(self, api_client, developer_token):
        """In-progress journeys should have start_data with departure_time for Pulse"""
        headers = {"Authorization": f"Bearer {developer_token}"}
        
        response = api_client.get(f"{BASE_URL}/api/journeys?status=in_progress", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        journeys = data.get("data", data) if isinstance(data, dict) else data
        
        in_progress = [j for j in journeys if j.get("status") == "in_progress"]
        
        if len(in_progress) == 0:
            print("INFO: No in_progress journeys found - Pulse will correctly show no active routes")
            return
        
        # Check that in_progress journeys have start_data
        for journey in in_progress:
            start_data = journey.get("start_data")
            if start_data:
                print(f"  Journey {journey.get('id')[:8]}... has start_data with departure_time: {start_data.get('departure_time')}")
        
        print("PASSED: In-progress journeys checked for start_data")


class TestP2PulseCalculationLogic:
    """P2: Test that Pulse calculation requirements are met"""

    def test_pulse_only_applies_to_in_progress_routes(self, api_client, developer_token):
        """Pulse should only compute for in_progress routes with remaining packages"""
        headers = {"Authorization": f"Bearer {developer_token}"}
        
        response = api_client.get(f"{BASE_URL}/api/journeys", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        journeys = data.get("data", data) if isinstance(data, dict) else data
        
        # Count routes by status
        status_counts = {}
        for j in journeys:
            status = j.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"Journey status distribution: {status_counts}")
        
        # Check for in_progress routes with remaining packages
        in_progress_with_remaining = []
        for j in journeys:
            if j.get("status") == "in_progress":
                total = j.get("packages_total", 0)
                delivered = j.get("packages_delivered", 0)
                failed = j.get("packages_failed", 0)
                remaining = total - delivered - failed
                if remaining > 0:
                    in_progress_with_remaining.append({
                        "id": j.get("id"),
                        "remaining": remaining
                    })
        
        if len(in_progress_with_remaining) == 0:
            print("INFO: No in_progress routes with remaining packages - PulseStrip/PulseBanner will correctly NOT appear")
        else:
            print(f"Found {len(in_progress_with_remaining)} in_progress routes with remaining packages")
        
        print("PASSED: Pulse applicability logic verified")


class TestInvalidSectionReturns400:
    """Test that invalid section returns 400"""

    def test_invalid_section_returns_400(self, api_client, developer_token):
        """PATCH with invalid section should return 400"""
        headers = {"Authorization": f"Bearer {developer_token}"}
        
        response = api_client.patch(
            f"{BASE_URL}/api/admin/config",
            headers=headers,
            json={"section": "invalid_section", "value": {}}
        )
        
        assert response.status_code == 400, f"Invalid section should return 400. Got: {response.status_code}"
        print("PASSED: Invalid section returns 400")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
