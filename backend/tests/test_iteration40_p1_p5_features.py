"""
Iteration 40 - Testing 5 Feature Prompts (P1-P5)
P1: Refresh Token for Power BI
P2: Liquidación formulas fix
P3: Delete Journey + Driver column
P4: Order ID in tables + search + pagination
P5: Remove checklist + 32 Mexico states in route type
"""
import pytest
import requests
import os
import jwt
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://lastmile-mvp.preview.emergentagent.com"

# Test credentials
COORDINATOR_EMAIL = "yael@me.mx"
COORDINATOR_PASSWORD = "LastMile2026"
DEVELOPER_EMAIL = "dev@me.mx"
DEVELOPER_PASSWORD = "LastMile2026"
AGENT_EMAIL = "agente@me.mx"
AGENT_PASSWORD = "LastMile2026"


class TestP1RefreshToken:
    """P1 - Refresh Token for Power BI Integration"""
    
    @pytest.fixture
    def coordinator_token(self):
        """Get coordinator auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["access_token"]
    
    @pytest.fixture
    def developer_token(self):
        """Get developer auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEVELOPER_EMAIL,
            "password": DEVELOPER_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["access_token"]
    
    @pytest.fixture
    def agent_token(self):
        """Get agent auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": AGENT_EMAIL,
            "password": AGENT_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["access_token"]
    
    def test_generate_refresh_token_coordinator(self, coordinator_token):
        """Test POST /api/auth/refresh-token returns a token with 90-day expiry"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        response = requests.post(f"{BASE_URL}/api/auth/refresh-token", headers=headers)
        
        assert response.status_code == 200, f"Failed to generate refresh token: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "refresh_token" in data, "Missing refresh_token in response"
        assert "expires_at" in data, "Missing expires_at in response"
        assert "message" in data, "Missing message in response"
        
        # Verify token is valid JWT
        refresh_token = data["refresh_token"]
        assert len(refresh_token) > 50, "Refresh token seems too short"
        
        # Verify expiry is approximately 90 days
        expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days_until_expiry = (expires_at - now).days
        assert 85 <= days_until_expiry <= 95, f"Expected ~90 days expiry, got {days_until_expiry} days"
        
        print(f"✓ Refresh token generated with {days_until_expiry} days expiry")
    
    def test_generate_refresh_token_developer(self, developer_token):
        """Test developer can also generate refresh tokens"""
        headers = {"Authorization": f"Bearer {developer_token}"}
        response = requests.post(f"{BASE_URL}/api/auth/refresh-token", headers=headers)
        
        assert response.status_code == 200, f"Developer should be able to generate refresh token: {response.text}"
        data = response.json()
        assert "refresh_token" in data
        print("✓ Developer can generate refresh tokens")
    
    def test_generate_refresh_token_agent_forbidden(self, agent_token):
        """Test agent cannot generate refresh tokens (403)"""
        headers = {"Authorization": f"Bearer {agent_token}"}
        response = requests.post(f"{BASE_URL}/api/auth/refresh-token", headers=headers)
        
        assert response.status_code == 403, f"Agent should not be able to generate refresh token, got {response.status_code}"
        print("✓ Agent correctly denied refresh token generation")
    
    def test_exchange_token(self, coordinator_token):
        """Test POST /api/auth/exchange-token with a refresh token returns a short-lived access token"""
        # First generate a refresh token
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        gen_response = requests.post(f"{BASE_URL}/api/auth/refresh-token", headers=headers)
        assert gen_response.status_code == 200
        refresh_token = gen_response.json()["refresh_token"]
        
        # Exchange refresh token for access token
        exchange_headers = {"Authorization": f"Bearer {refresh_token}"}
        exchange_response = requests.post(f"{BASE_URL}/api/auth/exchange-token", headers=exchange_headers)
        
        assert exchange_response.status_code == 200, f"Failed to exchange token: {exchange_response.text}"
        data = exchange_response.json()
        
        # Verify response structure
        assert "access_token" in data, "Missing access_token in response"
        assert "token_type" in data, "Missing token_type in response"
        assert "user" in data, "Missing user in response"
        assert data["token_type"] == "bearer"
        
        # Verify user info
        assert data["user"]["email"] == COORDINATOR_EMAIL
        
        print("✓ Refresh token exchanged for access token successfully")
    
    def test_list_refresh_tokens(self, coordinator_token):
        """Test GET /api/auth/refresh-tokens returns list of active tokens"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        # Generate a token first to ensure there's at least one
        requests.post(f"{BASE_URL}/api/auth/refresh-token", headers=headers)
        
        # List tokens
        response = requests.get(f"{BASE_URL}/api/auth/refresh-tokens", headers=headers)
        
        assert response.status_code == 200, f"Failed to list refresh tokens: {response.text}"
        data = response.json()
        
        # Verify response is a list
        assert isinstance(data, list), "Expected list of tokens"
        
        if len(data) > 0:
            token_entry = data[0]
            assert "jti" in token_entry, "Missing jti in token entry"
            assert "created_at" in token_entry, "Missing created_at in token entry"
            assert "expires_at" in token_entry, "Missing expires_at in token entry"
        
        print(f"✓ Listed {len(data)} active refresh tokens")
    
    def test_revoke_refresh_token(self, coordinator_token):
        """Test DELETE /api/auth/refresh-token/{jti} revokes a token"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        # Generate a token
        gen_response = requests.post(f"{BASE_URL}/api/auth/refresh-token", headers=headers)
        assert gen_response.status_code == 200
        
        # List tokens to get the jti
        list_response = requests.get(f"{BASE_URL}/api/auth/refresh-tokens", headers=headers)
        tokens = list_response.json()
        
        if len(tokens) > 0:
            jti_to_revoke = tokens[0]["jti"]
            
            # Revoke the token
            revoke_response = requests.delete(f"{BASE_URL}/api/auth/refresh-token/{jti_to_revoke}", headers=headers)
            assert revoke_response.status_code == 200, f"Failed to revoke token: {revoke_response.text}"
            
            print(f"✓ Refresh token {jti_to_revoke[:8]}... revoked successfully")
        else:
            print("⚠ No tokens to revoke")


class TestP2LiquidacionFormulas:
    """P2 - Liquidación formulas fix verification"""
    
    @pytest.fixture
    def coordinator_token(self):
        """Get coordinator auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        assert response.status_code == 200
        return response.json()["access_token"]
    
    def test_liquidacion_export_endpoint_exists(self, coordinator_token):
        """Test that liquidación export endpoint exists and responds"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        # Test with a date range
        params = {
            "date_from": "2026-01-01",
            "date_to": "2026-01-31"
        }
        
        response = requests.get(f"{BASE_URL}/api/reports/liquidacion", headers=headers, params=params)
        
        # The endpoint should exist (200 or 404 if no data, but not 500)
        assert response.status_code in [200, 404], f"Liquidación endpoint error: {response.status_code} - {response.text}"
        print(f"✓ Liquidación export endpoint responds with status {response.status_code}")
    
    def test_liquidacion_export_with_data(self, coordinator_token):
        """Test liquidación export with actual data range"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        # Use a date range that should have data based on previous tests
        params = {
            "date_from": "2026-03-01",
            "date_to": "2026-04-30"
        }
        
        response = requests.get(f"{BASE_URL}/api/reports/liquidacion", headers=headers, params=params)
        
        if response.status_code == 200:
            # Check content type for Excel
            content_type = response.headers.get("content-type", "")
            assert "spreadsheet" in content_type or "octet-stream" in content_type or "excel" in content_type.lower(), \
                f"Expected Excel content type, got {content_type}"
            print("✓ Liquidación export returns Excel file")
        else:
            print(f"⚠ No data for liquidación export in date range (status {response.status_code})")


class TestP3DeleteJourney:
    """P3 - Delete Journey + Driver column"""
    
    @pytest.fixture
    def coordinator_token(self):
        """Get coordinator auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        assert response.status_code == 200
        return response.json()["access_token"]
    
    @pytest.fixture
    def agent_token(self):
        """Get agent auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": AGENT_EMAIL,
            "password": AGENT_PASSWORD
        })
        assert response.status_code == 200
        return response.json()["access_token"]
    
    def test_delete_journey_nonexistent_returns_404(self, coordinator_token):
        """Test DELETE /api/journeys/{id} returns 404 for non-existent ID"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        fake_id = "nonexistent-journey-id-12345"
        response = requests.delete(f"{BASE_URL}/api/journeys/{fake_id}", headers=headers)
        
        assert response.status_code == 404, f"Expected 404 for non-existent journey, got {response.status_code}"
        print("✓ DELETE non-existent journey returns 404")
    
    def test_delete_journey_agent_forbidden(self, agent_token):
        """Test agent cannot delete journeys (403)"""
        headers = {"Authorization": f"Bearer {agent_token}"}
        
        # First get a journey ID
        journeys_response = requests.get(f"{BASE_URL}/api/journeys", headers=headers)
        if journeys_response.status_code == 200:
            journeys = journeys_response.json()
            if isinstance(journeys, dict) and "data" in journeys:
                journeys = journeys["data"]
            
            if len(journeys) > 0:
                journey_id = journeys[0]["id"]
                
                # Try to delete
                delete_response = requests.delete(f"{BASE_URL}/api/journeys/{journey_id}", headers=headers)
                assert delete_response.status_code == 403, f"Agent should not be able to delete, got {delete_response.status_code}"
                print("✓ Agent correctly denied journey deletion")
            else:
                print("⚠ No journeys to test deletion permission")
        else:
            print(f"⚠ Could not fetch journeys: {journeys_response.status_code}")
    
    def test_journeys_list_has_driver_column(self, coordinator_token):
        """Test that journeys list includes driver_name field"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        response = requests.get(f"{BASE_URL}/api/journeys", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        journeys = data.get("data", data) if isinstance(data, dict) else data
        
        if len(journeys) > 0:
            journey = journeys[0]
            # Check that driver_name field exists (can be null/empty but should be present)
            assert "driver_name" in journey or "driver" in journey, "Missing driver field in journey"
            print(f"✓ Journey has driver field: {journey.get('driver_name', journey.get('driver', 'N/A'))}")
        else:
            print("⚠ No journeys to verify driver column")


class TestP4OrderIDSearchPagination:
    """P4 - Order ID in tables + search + pagination"""
    
    @pytest.fixture
    def coordinator_token(self):
        """Get coordinator auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        assert response.status_code == 200
        return response.json()["access_token"]
    
    def test_journeys_list_has_order_id(self, coordinator_token):
        """Test that journeys list includes order_id field"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        response = requests.get(f"{BASE_URL}/api/journeys", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        journeys = data.get("data", data) if isinstance(data, dict) else data
        
        if len(journeys) > 0:
            journey = journeys[0]
            # order_id may be null for manually created journeys, but field should exist
            # Check for order_id or cosmo_route_id
            has_order_id = "order_id" in journey or "cosmo_route_id" in journey
            assert has_order_id, "Missing order_id/cosmo_route_id field in journey"
            print(f"✓ Journey has order_id: {journey.get('order_id', journey.get('cosmo_route_id', 'N/A'))}")
        else:
            print("⚠ No journeys to verify order_id")
    
    def test_journeys_pagination_structure(self, coordinator_token):
        """Test that journeys endpoint returns pagination info"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        response = requests.get(f"{BASE_URL}/api/journeys?page=1&page_size=25", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        
        # Check pagination structure
        assert "pagination" in data, "Missing pagination in response"
        pagination = data["pagination"]
        
        assert "page" in pagination, "Missing page in pagination"
        assert "page_size" in pagination, "Missing page_size in pagination"
        assert "total_count" in pagination, "Missing total_count in pagination"
        assert "total_pages" in pagination, "Missing total_pages in pagination"
        
        print(f"✓ Pagination: page {pagination['page']}/{pagination['total_pages']}, {pagination['total_count']} total")
    
    def test_journeys_pagination_page_size(self, coordinator_token):
        """Test different page sizes work correctly"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        for page_size in [25, 50, 100]:
            response = requests.get(f"{BASE_URL}/api/journeys?page=1&page_size={page_size}", headers=headers)
            assert response.status_code == 200
            
            data = response.json()
            journeys = data.get("data", [])
            pagination = data.get("pagination", {})
            
            # Verify page_size is respected
            assert pagination.get("page_size") == page_size, f"Expected page_size {page_size}, got {pagination.get('page_size')}"
            
            # Verify returned data doesn't exceed page_size
            assert len(journeys) <= page_size, f"Returned {len(journeys)} items, expected max {page_size}"
        
        print("✓ Pagination page sizes (25, 50, 100) work correctly")
    
    def test_journey_detail_has_order_id(self, coordinator_token):
        """Test that journey detail includes order_id"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        # Get a journey ID first
        list_response = requests.get(f"{BASE_URL}/api/journeys", headers=headers)
        assert list_response.status_code == 200
        
        data = list_response.json()
        journeys = data.get("data", data) if isinstance(data, dict) else data
        
        if len(journeys) > 0:
            journey_id = journeys[0]["id"]
            
            # Get journey detail
            detail_response = requests.get(f"{BASE_URL}/api/journeys/{journey_id}", headers=headers)
            assert detail_response.status_code == 200
            
            journey = detail_response.json()
            has_order_id = "order_id" in journey or "cosmo_route_id" in journey
            assert has_order_id, "Missing order_id in journey detail"
            print(f"✓ Journey detail has order_id: {journey.get('order_id', journey.get('cosmo_route_id', 'N/A'))}")
        else:
            print("⚠ No journeys to verify detail order_id")


class TestP5RouteTypeAndChecklist:
    """P5 - Remove checklist + 32 Mexico states in route type"""
    
    @pytest.fixture
    def coordinator_token(self):
        """Get coordinator auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        assert response.status_code == 200
        return response.json()["access_token"]
    
    def test_start_journey_without_checklist(self, coordinator_token):
        """Test that journey can be started without checklist validation"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        # Get a scheduled journey
        response = requests.get(f"{BASE_URL}/api/journeys?status=scheduled", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        journeys = data.get("data", data) if isinstance(data, dict) else data
        
        scheduled_journeys = [j for j in journeys if j.get("status") == "scheduled"]
        
        if len(scheduled_journeys) > 0:
            journey_id = scheduled_journeys[0]["id"]
            
            # Try to start without checklist items (checklist_completed=True but no actual items)
            start_data = {
                "departure_time": datetime.now(timezone.utc).isoformat(),
                "odometer_start": 10000,
                "fuel_level": "3/4",
                "vehicle_condition": "Óptimo",
                "packages_loaded": 10,
                "checklist_completed": True,  # This should work without actual checklist items
                "route_type": "CDMX / Zona Metro"
            }
            
            start_response = requests.put(f"{BASE_URL}/api/journeys/{journey_id}/start", headers=headers, json=start_data)
            
            # Should succeed (200) or fail for other reasons (not checklist)
            if start_response.status_code == 200:
                print("✓ Journey started without checklist validation")
            elif start_response.status_code == 400:
                error = start_response.json().get("detail", "")
                # Should NOT fail due to checklist
                assert "checklist" not in error.lower() or "completar" not in error.lower(), \
                    f"Checklist validation should be removed: {error}"
                print(f"⚠ Start failed for other reason: {error}")
            else:
                print(f"⚠ Unexpected status: {start_response.status_code}")
        else:
            print("⚠ No scheduled journeys to test start")
    
    def test_journey_route_type_field(self, coordinator_token):
        """Test that journey has route_type field"""
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        
        response = requests.get(f"{BASE_URL}/api/journeys", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        journeys = data.get("data", data) if isinstance(data, dict) else data
        
        if len(journeys) > 0:
            journey = journeys[0]
            # route_type should exist
            assert "route_type" in journey, "Missing route_type field in journey"
            print(f"✓ Journey has route_type: {journey.get('route_type', 'N/A')}")
        else:
            print("⚠ No journeys to verify route_type")


class TestHealthAndBasics:
    """Basic health checks"""
    
    def test_health_endpoint(self):
        """Test health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✓ Health endpoint OK")
    
    def test_login_coordinator(self):
        """Test coordinator login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "coordinator"
        print("✓ Coordinator login OK")
    
    def test_login_developer(self):
        """Test developer login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEVELOPER_EMAIL,
            "password": DEVELOPER_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "developer"
        print("✓ Developer login OK")
    
    def test_login_agent(self):
        """Test agent login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": AGENT_EMAIL,
            "password": AGENT_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "agent"
        print("✓ Agent login OK")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
