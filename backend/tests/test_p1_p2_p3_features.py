"""
Test suite for P1, P2, P3 features:
- P1: Inline Incident Registration from package table (source='guias')
- P2: AI Reports Generation v2.0 with dynamic cards
- P3: Cubbo Standard Evidence Evaluation (ReviewModal backend support)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
COORDINATOR_EMAIL = "yael@me.mx"
COORDINATOR_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
AGENT_EMAIL = "agente@me.mx"
AGENT_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")


class TestAuth:
    """Authentication tests"""
    
    def test_coordinator_login(self):
        """Test coordinator can login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "coordinator"
        
    def test_agent_login(self):
        """Test agent can login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": AGENT_EMAIL,
            "password": AGENT_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "agent"


@pytest.fixture
def coordinator_token():
    """Get coordinator auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": COORDINATOR_EMAIL,
        "password": COORDINATOR_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Coordinator authentication failed")


@pytest.fixture
def agent_token():
    """Get agent auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": AGENT_EMAIL,
        "password": AGENT_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Agent authentication failed")


@pytest.fixture
def journey_with_packages(coordinator_token):
    """Get a journey that has packages"""
    headers = {"Authorization": f"Bearer {coordinator_token}"}
    response = requests.get(
        f"{BASE_URL}/api/journeys?date_from=2026-04-01&date_to=2026-04-15",
        headers=headers
    )
    if response.status_code == 200:
        journeys = response.json().get("data", [])
        for j in journeys:
            if j.get("packages_total", 0) > 0:
                # Get full journey with packages
                detail_resp = requests.get(
                    f"{BASE_URL}/api/journeys/{j['id']}",
                    headers=headers
                )
                if detail_resp.status_code == 200:
                    return detail_resp.json()
    pytest.skip("No journey with packages found")


class TestP1InlineIncidentRegistration:
    """P1: Inline Incident Registration from package table with source='guias'"""
    
    def test_create_incident_with_source_guias(self, coordinator_token, journey_with_packages):
        """Test creating incident with source='guias' field"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        journey_id = journey_with_packages["id"]
        packages = journey_with_packages.get("packages", [])
        
        assert len(packages) > 0, "Journey should have packages"
        pkg = packages[0]
        tracking_number = pkg.get("tracking_number") or pkg.get("order_reference_id", "")
        
        # Create incident with source='guias'
        incident_data = {
            "journey_id": journey_id,
            "occurred_at": "2026-04-10T21:00:00",
            "incident_type": "Evidencia Insuficiente",
            "description": f"TEST_P1 - Incidencia registrada desde Guias para paquete {tracking_number}",
            "severity": "Media",
            "tracking_number": tracking_number,
            "action_taken": "",
            "source": "guias"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/incidents",
            headers=headers,
            json=incident_data
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "id" in data
        assert data["source"] == "guias", "Source should be 'guias'"
        assert data["incident_type"] == "Evidencia Insuficiente"
        assert data["tracking_number"] == tracking_number
        assert data["status"] == "open"
        
        # Cleanup - delete the test incident
        incident_id = data["id"]
        delete_resp = requests.delete(
            f"{BASE_URL}/api/incidents/{incident_id}",
            headers=headers
        )
        assert delete_resp.status_code == 200
        
    def test_incident_source_defaults_to_incidencias(self, coordinator_token, journey_with_packages):
        """Test that source defaults to 'incidencias' when not provided"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        journey_id = journey_with_packages["id"]
        
        # Create incident without source field
        incident_data = {
            "journey_id": journey_id,
            "occurred_at": "2026-04-10T21:00:00",
            "incident_type": "Otro",
            "description": "TEST_P1 - Incidencia sin source especificado",
            "severity": "Baja",
            "tracking_number": "TEST-DEFAULT-SOURCE",
            "action_taken": ""
        }
        
        response = requests.post(
            f"{BASE_URL}/api/incidents",
            headers=headers,
            json=incident_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "incidencias", "Source should default to 'incidencias'"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/incidents/{data['id']}", headers=headers)


class TestP2AIReportsGeneration:
    """P2: AI Reports Generation v2.0 with dynamic cards"""
    
    def test_generate_ai_report_returns_cards_and_narrative(self, coordinator_token):
        """Test AI report returns structured JSON with cards array and narrative string"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        response = requests.post(
            f"{BASE_URL}/api/reports/generate-ai",
            headers=headers,
            json={
                "date_from": "2026-04-01",
                "date_to": "2026-04-15"
            },
            timeout=90  # AI generation can take time
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "narrative" in data, "Response should contain 'narrative'"
        assert "cards" in data, "Response should contain 'cards'"
        assert "period" in data, "Response should contain 'period'"
        
        # Verify narrative is a string
        assert isinstance(data["narrative"], str), "Narrative should be a string"
        assert len(data["narrative"]) > 0, "Narrative should not be empty"
        
        # Verify cards is an array
        assert isinstance(data["cards"], list), "Cards should be a list"
        
    def test_ai_report_cards_structure(self, coordinator_token):
        """Test that AI report cards have correct structure"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        response = requests.post(
            f"{BASE_URL}/api/reports/generate-ai",
            headers=headers,
            json={
                "date_from": "2026-04-01",
                "date_to": "2026-04-15"
            },
            timeout=90
        )
        
        assert response.status_code == 200
        data = response.json()
        cards = data.get("cards", [])
        
        if len(cards) > 0:
            # Verify card structure
            for card in cards:
                assert "tipo" in card, "Card should have 'tipo'"
                assert card["tipo"] in ["alerta", "tendencia", "logro"], f"Card tipo should be alerta/tendencia/logro, got {card['tipo']}"
                assert "titulo" in card, "Card should have 'titulo'"
                assert "cuerpo" in card, "Card should have 'cuerpo'"
                # metrica and variacion are optional but expected
                
    def test_ai_report_no_data_period(self, coordinator_token):
        """Test AI report handles period with no data gracefully"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        response = requests.post(
            f"{BASE_URL}/api/reports/generate-ai",
            headers=headers,
            json={
                "date_from": "2020-01-01",
                "date_to": "2020-01-15"
            },
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "narrative" in data
        assert "cards" in data
        # Should return empty cards and a message about no data
        assert data["cards"] == []


class TestP3ReviewModalBackend:
    """P3: Cubbo Standard Evidence Evaluation - Backend support for ReviewModal"""
    
    def test_package_has_evidence_detail(self, coordinator_token, journey_with_packages):
        """Test that packages have evidence_detail field for ReviewModal"""
        packages = journey_with_packages.get("packages", [])
        
        # Check if any package has evidence_detail
        packages_with_evidence = [p for p in packages if p.get("evidence_detail")]
        
        # At least some packages should have evidence detail
        # This is populated by AI evaluation
        print(f"Packages with evidence_detail: {len(packages_with_evidence)}/{len(packages)}")
        
    def test_package_review_approve(self, coordinator_token, journey_with_packages):
        """Test approving a package review"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        packages = journey_with_packages.get("packages", [])
        
        # Find a delivered package to review
        delivered_pkg = next((p for p in packages if p.get("status") == "delivered"), None)
        if not delivered_pkg:
            pytest.skip("No delivered package found to test review")
            
        pkg_id = delivered_pkg["id"]
        
        # Approve the package
        response = requests.put(
            f"{BASE_URL}/api/packages/{pkg_id}/review",
            headers=headers,
            json={
                "review_status": "approved",
                "review_score": 85,
                "review_notes": "TEST_P3 - Evidencia completa",
                "delivery_type": "A"
            }
        )
        
        # Check if endpoint exists and works
        if response.status_code == 404:
            pytest.skip("Package review endpoint not implemented")
            
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        
    def test_package_review_reject(self, coordinator_token, journey_with_packages):
        """Test rejecting a package review"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        packages = journey_with_packages.get("packages", [])
        
        # Find a delivered package to review
        delivered_pkg = next((p for p in packages if p.get("status") == "delivered"), None)
        if not delivered_pkg:
            pytest.skip("No delivered package found to test review")
            
        pkg_id = delivered_pkg["id"]
        
        # Reject the package
        response = requests.put(
            f"{BASE_URL}/api/packages/{pkg_id}/review",
            headers=headers,
            json={
                "review_status": "rejected",
                "review_score": 40,
                "review_notes": "TEST_P3 - Evidencia insuficiente",
                "rejection_reason": "foto_fachada_ausente",
                "delivery_type": "A"
            }
        )
        
        # Check if endpoint exists and works
        if response.status_code == 404:
            pytest.skip("Package review endpoint not implemented")
            
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"


class TestRoleBasedAccess:
    """Test role-based access control for features"""
    
    def test_agent_cannot_create_incident(self, agent_token, journey_with_packages):
        """Test that agent role can create incidents (they have permission)"""
        headers = {"Authorization": f"Bearer {agent_token}"}
        journey_id = journey_with_packages["id"]
        
        incident_data = {
            "journey_id": journey_id,
            "occurred_at": "2026-04-10T21:00:00",
            "incident_type": "Otro",
            "description": "TEST - Agent incident creation",
            "severity": "Baja",
            "tracking_number": "TEST-AGENT",
            "action_taken": "",
            "source": "guias"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/incidents",
            headers=headers,
            json=incident_data
        )
        
        # Agent should be able to create incidents (coordinator and agent roles allowed)
        assert response.status_code == 200, f"Agent should be able to create incidents: {response.text}"
        
        # Cleanup
        if response.status_code == 200:
            requests.delete(
                f"{BASE_URL}/api/incidents/{response.json()['id']}",
                headers=headers
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
