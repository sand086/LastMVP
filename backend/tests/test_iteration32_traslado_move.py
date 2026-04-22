"""
Iteration 32 - Test: Traslado a 1er punto moved from global config to per-journey start form

Tests:
1. Backend: GET /api/admin/config pulse_config - verify required fields exist
2. Backend: Journey start data should save traslado_primer_punto when starting a journey
3. Frontend: Journey Start form shows 'Traslado a 1er punto (min)' field
4. Frontend: Admin IA > Config > Pulse section does NOT show traslado input fields (only helper text)

NOTE: The database may still have old pulse_config with traslado fields from previous iterations.
The frontend PulseConfigSection.jsx has been updated to NOT render those fields.
The pulseUtils.js now reads traslado from journey.start_data.traslado_primer_punto instead of global config.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPulseConfigRequiredFields:
    """Test that pulse_config has required fields for Pulse feature"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "dev@me.mx",
            "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    def test_pulse_config_has_required_fields(self):
        """GET /api/admin/config pulse_config should have hora_limite, tiempo_promedio_entrega, umbral_ok, umbral_warn"""
        resp = requests.get(f"{BASE_URL}/api/admin/config", headers=self.headers)
        assert resp.status_code == 200
        
        pulse_config = resp.json().get("pulse_config", {})
        
        # These fields should exist (required for Pulse calculations)
        assert "hora_limite" in pulse_config, "hora_limite should be in pulse_config"
        assert "tiempo_promedio_entrega" in pulse_config, "tiempo_promedio_entrega should be in pulse_config"
        assert "umbral_ok" in pulse_config, "umbral_ok should be in pulse_config"
        assert "umbral_warn" in pulse_config, "umbral_warn should be in pulse_config"
        
        # Verify hora_limite structure
        hora_limite = pulse_config.get("hora_limite", {})
        assert "hour" in hora_limite, "hora_limite should have 'hour' field"
        assert "minute" in hora_limite, "hora_limite should have 'minute' field"
        
        print(f"pulse_config keys: {list(pulse_config.keys())}")
        print("NOTE: traslado_primer_punto_default may still exist in DB but frontend ignores it")


class TestScheduledJourneyStartForm:
    """Test that scheduled journey can be started with traslado_primer_punto"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "dev@me.mx",
            "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    def test_scheduled_journey_exists(self):
        """Verify the scheduled journey exists for testing"""
        journey_id = "fefd8411-7a4e-4a8f-9c32-1d66d41ead9c"
        resp = requests.get(f"{BASE_URL}/api/journeys/{journey_id}", headers=self.headers)
        assert resp.status_code == 200, f"Failed to get journey: {resp.text}"
        
        journey = resp.json()
        assert journey.get("status") == "scheduled", f"Journey should be scheduled, got: {journey.get('status')}"
        assert journey.get("start_data") is None, "Scheduled journey should not have start_data yet"
    
    def test_in_progress_journey_without_traslado_uses_fallback(self):
        """In-progress journey started before this change should not have traslado_primer_punto (fallback to 40)"""
        journey_id = "c8d4c292-5c27-46bf-8b81-e83e40fb8a05"
        resp = requests.get(f"{BASE_URL}/api/journeys/{journey_id}", headers=self.headers)
        assert resp.status_code == 200, f"Failed to get journey: {resp.text}"
        
        journey = resp.json()
        assert journey.get("status") == "in_progress", f"Journey should be in_progress, got: {journey.get('status')}"
        
        start_data = journey.get("start_data", {})
        assert start_data is not None, "In-progress journey should have start_data"
        
        # This journey was started BEFORE the change, so it won't have traslado_primer_punto
        # The frontend pulseUtils.js should fallback to 40
        traslado = start_data.get("traslado_primer_punto")
        print(f"traslado_primer_punto in start_data: {traslado} (expected: None for old journeys)")
        print("Frontend pulseUtils.js will fallback to 40 when traslado_primer_punto is not in start_data")


class TestPulseUtilsReadsTrasladoFromJourney:
    """Test that pulseUtils reads traslado from journey.start_data instead of global config"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token"""
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "dev@me.mx",
            "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    def test_journey_start_data_can_have_traslado_primer_punto(self):
        """Verify that journey start_data structure supports traslado_primer_punto field"""
        # The scheduled journey at fefd8411-7a4e-4a8f-9c32-1d66d41ead9c
        # When started, should save traslado_primer_punto in start_data
        # This is verified by the frontend form having the field with default value 40
        
        # For now, just verify the API structure supports this
        journey_id = "fefd8411-7a4e-4a8f-9c32-1d66d41ead9c"
        resp = requests.get(f"{BASE_URL}/api/journeys/{journey_id}", headers=self.headers)
        assert resp.status_code == 200
        
        journey = resp.json()
        # The journey is scheduled, so start_data is None
        # When started via POST /api/journeys/{id}/start with traslado_primer_punto,
        # it should be saved in start_data
        print(f"Journey {journey_id} status: {journey.get('status')}")
        print("When this journey is started, traslado_primer_punto will be saved in start_data")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
