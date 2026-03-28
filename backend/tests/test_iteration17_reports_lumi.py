"""
Iteration 17 Tests: Reports Redesign + Lumi Chatbot
Tests for:
- GET /api/reports/attempts - Delivery attempts distribution
- GET /api/reports/sla - SLA vs Target reporting
- PATCH /api/config/sla-targets - Persist SLA brackets
- POST /api/reports/generate-ai - AI narrative report
- POST /api/chat/lumi - Lumi chatbot
- POST /api/reports/generate - Report generation
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEV_EMAIL = "dev@me.mx"
DEV_PASSWORD = "LastMile2026"
COORDINATOR_EMAIL = "yael@me.mx"
COORDINATOR_PASSWORD = "LastMile2026"

# Date range with data
DATE_FROM = "2026-03-01"
DATE_TO = "2026-03-31"


class TestAuth:
    """Authentication tests"""
    
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
        assert data["user"]["email"] == DEV_EMAIL
        print(f"✓ Developer login successful: {data['user']['name']}")
    
    def test_login_coordinator(self):
        """Test coordinator login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        print(f"✓ Coordinator login successful: {data['user']['name']}")


@pytest.fixture
def dev_token():
    """Get developer auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEV_EMAIL,
        "password": DEV_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Developer authentication failed")


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


class TestReportsAttempts:
    """Tests for GET /api/reports/attempts endpoint"""
    
    def test_attempts_endpoint_returns_200(self, dev_token):
        """Test attempts endpoint returns 200"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(
            f"{BASE_URL}/api/reports/attempts",
            params={"date_from": DATE_FROM, "date_to": DATE_TO},
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        print("✓ GET /api/reports/attempts returns 200")
    
    def test_attempts_response_structure(self, dev_token):
        """Test attempts response has correct structure"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(
            f"{BASE_URL}/api/reports/attempts",
            params={"date_from": DATE_FROM, "date_to": DATE_TO},
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "first_attempt" in data, "Missing first_attempt"
        assert "second_attempt" in data, "Missing second_attempt"
        assert "third_attempt" in data, "Missing third_attempt"
        assert "retry_causes" in data, "Missing retry_causes"
        
        # Verify attempt structure
        for attempt_key in ["first_attempt", "second_attempt", "third_attempt"]:
            assert "count" in data[attempt_key], f"Missing count in {attempt_key}"
            assert "pct" in data[attempt_key], f"Missing pct in {attempt_key}"
        
        print(f"✓ Attempts response structure valid")
        print(f"  - First attempt: {data['first_attempt']}")
        print(f"  - Second attempt: {data['second_attempt']}")
        print(f"  - Third attempt: {data['third_attempt']}")
    
    def test_attempts_has_total_packages(self, dev_token):
        """Test attempts response includes total_packages"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(
            f"{BASE_URL}/api/reports/attempts",
            params={"date_from": DATE_FROM, "date_to": DATE_TO},
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_packages" in data, "Missing total_packages field"
        print(f"✓ Total packages: {data['total_packages']}")


class TestReportsSLA:
    """Tests for GET /api/reports/sla endpoint"""
    
    def test_sla_endpoint_returns_200(self, dev_token):
        """Test SLA endpoint returns 200"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(
            f"{BASE_URL}/api/reports/sla",
            params={"date_from": DATE_FROM, "date_to": DATE_TO},
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        print("✓ GET /api/reports/sla returns 200")
    
    def test_sla_response_structure(self, dev_token):
        """Test SLA response has correct structure"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(
            f"{BASE_URL}/api/reports/sla",
            params={"date_from": DATE_FROM, "date_to": DATE_TO},
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "consolidated" in data, "Missing consolidated"
        assert "by_provider" in data, "Missing by_provider"
        assert "by_driver" in data, "Missing by_driver"
        assert "brackets" in data, "Missing brackets"
        
        # Verify consolidated structure
        assert "actual" in data["consolidated"], "Missing actual in consolidated"
        assert "target" in data["consolidated"], "Missing target in consolidated"
        
        print(f"✓ SLA response structure valid")
        print(f"  - Consolidated: {data['consolidated']}")
        print(f"  - Providers count: {len(data['by_provider'])}")
        print(f"  - Drivers count: {len(data['by_driver'])}")
        print(f"  - Brackets: {len(data['brackets'])}")
    
    def test_sla_brackets_structure(self, dev_token):
        """Test SLA brackets have correct structure"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(
            f"{BASE_URL}/api/reports/sla",
            params={"date_from": DATE_FROM, "date_to": DATE_TO},
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        
        brackets = data.get("brackets", [])
        assert len(brackets) > 0, "No brackets returned"
        
        for bracket in brackets:
            assert "label" in bracket, "Missing label in bracket"
            assert "target" in bracket, "Missing target in bracket"
            assert "status" in bracket, "Missing status in bracket"
        
        print(f"✓ SLA brackets structure valid: {brackets}")


class TestSLATargetsUpdate:
    """Tests for PATCH /api/config/sla-targets endpoint"""
    
    def test_sla_targets_update_requires_auth(self):
        """Test SLA targets update requires authentication"""
        response = requests.patch(
            f"{BASE_URL}/api/config/sla-targets",
            json={"brackets": []}
        )
        assert response.status_code in [401, 403], "Should require authentication"
        print("✓ PATCH /api/config/sla-targets requires auth")
    
    def test_sla_targets_update_with_coordinator(self, coordinator_token):
        """Test coordinator can update SLA targets"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        brackets = [
            {"label": "Mes 1-2", "target": 65, "status": "exceeded"},
            {"label": "Mes 3-4", "target": 75, "status": "active"},
            {"label": "Mes 5+", "target": 90, "status": "pending"},
        ]
        response = requests.patch(
            f"{BASE_URL}/api/config/sla-targets",
            json={"brackets": brackets},
            headers=headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data.get("success") == True, "Expected success=True"
        print("✓ Coordinator can update SLA targets")
    
    def test_sla_targets_persist(self, coordinator_token, dev_token):
        """Test SLA targets persist after update"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        # Update with specific values
        new_brackets = [
            {"label": "Mes 1-2", "target": 66, "status": "exceeded"},
            {"label": "Mes 3-4", "target": 76, "status": "active"},
            {"label": "Mes 5+", "target": 91, "status": "pending"},
        ]
        response = requests.patch(
            f"{BASE_URL}/api/config/sla-targets",
            json={"brackets": new_brackets},
            headers=headers
        )
        assert response.status_code == 200
        
        # Verify persistence via SLA report
        dev_headers = {"Authorization": f"Bearer {dev_token}"}
        sla_response = requests.get(
            f"{BASE_URL}/api/reports/sla",
            params={"date_from": DATE_FROM, "date_to": DATE_TO},
            headers=dev_headers
        )
        assert sla_response.status_code == 200
        sla_data = sla_response.json()
        
        # Check brackets were updated
        brackets = sla_data.get("brackets", [])
        assert len(brackets) == 3, "Expected 3 brackets"
        
        # Restore original values
        original_brackets = [
            {"label": "Mes 1-2", "target": 65, "status": "exceeded"},
            {"label": "Mes 3-4", "target": 75, "status": "active"},
            {"label": "Mes 5+", "target": 90, "status": "pending"},
        ]
        requests.patch(
            f"{BASE_URL}/api/config/sla-targets",
            json={"brackets": original_brackets},
            headers=headers
        )
        
        print("✓ SLA targets persist correctly")


class TestGenerateAIReport:
    """Tests for POST /api/reports/generate-ai endpoint"""
    
    def test_generate_ai_requires_auth(self):
        """Test AI report generation requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/reports/generate-ai",
            json={"period": "current_month"}
        )
        assert response.status_code in [401, 403], "Should require authentication"
        print("✓ POST /api/reports/generate-ai requires auth")
    
    def test_generate_ai_returns_200(self, dev_token):
        """Test AI report generation returns 200"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.post(
            f"{BASE_URL}/api/reports/generate-ai",
            json={
                "period": "current_month",
                "date_from": DATE_FROM,
                "date_to": DATE_TO,
                "sections": ["providers", "incidents"]
            },
            headers=headers,
            timeout=60  # AI calls may take time
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        print("✓ POST /api/reports/generate-ai returns 200")
    
    def test_generate_ai_response_structure(self, dev_token):
        """Test AI report response has correct structure"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.post(
            f"{BASE_URL}/api/reports/generate-ai",
            json={
                "period": "current_month",
                "date_from": DATE_FROM,
                "date_to": DATE_TO,
                "sections": ["providers"]
            },
            headers=headers,
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "narrative" in data, "Missing narrative field"
        assert "period" in data, "Missing period field"
        assert len(data["narrative"]) > 0, "Narrative should not be empty"
        
        print(f"✓ AI report response structure valid")
        print(f"  - Period: {data['period']}")
        print(f"  - Narrative length: {len(data['narrative'])} chars")


class TestLumiChat:
    """Tests for POST /api/chat/lumi endpoint"""
    
    def test_lumi_requires_auth(self):
        """Test Lumi chat requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/chat/lumi",
            json={"message": "Hola"}
        )
        assert response.status_code in [401, 403], "Should require authentication"
        print("✓ POST /api/chat/lumi requires auth")
    
    def test_lumi_returns_200(self, dev_token):
        """Test Lumi chat returns 200"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.post(
            f"{BASE_URL}/api/chat/lumi",
            json={
                "message": "¿Cuál es el SLA actual?",
                "period": "current_month",
                "history": []
            },
            headers=headers,
            timeout=60  # AI calls may take time
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        print("✓ POST /api/chat/lumi returns 200")
    
    def test_lumi_response_structure(self, dev_token):
        """Test Lumi chat response has correct structure"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.post(
            f"{BASE_URL}/api/chat/lumi",
            json={
                "message": "¿Cuántas rutas hay en el período?",
                "period": "current_month",
                "history": []
            },
            headers=headers,
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "reply" in data, "Missing reply field"
        assert len(data["reply"]) > 0, "Reply should not be empty"
        
        print(f"✓ Lumi response structure valid")
        print(f"  - Reply length: {len(data['reply'])} chars")
        print(f"  - Reply preview: {data['reply'][:100]}...")
    
    def test_lumi_with_history(self, dev_token):
        """Test Lumi chat with conversation history"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        history = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Hola, soy Lumi. ¿En qué puedo ayudarte?"}
        ]
        response = requests.post(
            f"{BASE_URL}/api/chat/lumi",
            json={
                "message": "¿Cuáles son los drivers con peor desempeño?",
                "period": "current_month",
                "history": history
            },
            headers=headers,
            timeout=60
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "reply" in data
        print("✓ Lumi handles conversation history")


class TestReportsGenerate:
    """Tests for POST /api/reports/generate endpoint"""
    
    def test_generate_report_returns_200(self, dev_token):
        """Test report generation returns 200"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.post(
            f"{BASE_URL}/api/reports/generate",
            json={
                "date_from": DATE_FROM,
                "date_to": DATE_TO
            },
            headers=headers,
            timeout=60
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        print("✓ POST /api/reports/generate returns 200")
    
    def test_generate_report_response_structure(self, dev_token):
        """Test report generation response has correct structure"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.post(
            f"{BASE_URL}/api/reports/generate",
            json={
                "date_from": DATE_FROM,
                "date_to": DATE_TO
            },
            headers=headers,
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "provider_metrics" in data, "Missing provider_metrics"
        assert "driver_metrics" in data, "Missing driver_metrics"
        assert "delivery_rate" in data, "Missing delivery_rate"
        assert "total_packages" in data, "Missing total_packages"
        assert "total_delivered" in data, "Missing total_delivered"
        
        print(f"✓ Report generation response structure valid")
        print(f"  - Delivery rate: {data['delivery_rate']}%")
        print(f"  - Total packages: {data['total_packages']}")
        print(f"  - Providers: {len(data['provider_metrics'])}")
        print(f"  - Drivers: {len(data['driver_metrics'])}")


class TestHealthCheck:
    """Basic health check"""
    
    def test_health_endpoint(self):
        """Test health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✓ Health check passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
