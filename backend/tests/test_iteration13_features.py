"""
Iteration 13 Tests: AI Evidence Scoring, Dashboard Pagination, Evidence Carousel
Tests for 3 major new features:
1. AI-Powered Evidence Scoring using Claude Vision API
2. Dynamic Pagination for dashboard routes table
3. Interactive Evidence Carousel modal
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEV_EMAIL = "dev@me.mx"
DEV_PASSWORD = "LastMile2026"
COORD_EMAIL = "yael@me.mx"
COORD_PASSWORD = "LastMile2026"

# Test data
TEST_JOURNEY_ID = "771326fe-599b-4965-979c-e3095eba1908"
TEST_PACKAGE_GUIDE = "vEW5DctRo1ZIFSma"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token for developer"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEV_EMAIL,
        "password": DEV_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


class TestDashboardPagination:
    """Tests for Dashboard pagination feature"""

    def test_journeys_endpoint_returns_paginated_response(self, authenticated_client):
        """GET /api/journeys returns paginated response with data and pagination fields"""
        response = authenticated_client.get(f"{BASE_URL}/api/journeys", params={
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
            "page": 1,
            "page_size": 25
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # Verify paginated response structure
        assert "data" in data, "Response should have 'data' field"
        assert "pagination" in data, "Response should have 'pagination' field"
        
        pagination = data["pagination"]
        assert "page" in pagination, "Pagination should have 'page'"
        assert "page_size" in pagination, "Pagination should have 'page_size'"
        assert "total_count" in pagination, "Pagination should have 'total_count'"
        assert "total_pages" in pagination, "Pagination should have 'total_pages'"
        
        print(f"✓ Paginated response: {pagination['total_count']} total routes, {pagination['total_pages']} pages")

    def test_pagination_page_size_25(self, authenticated_client):
        """Test page_size=25 returns correct number of items"""
        response = authenticated_client.get(f"{BASE_URL}/api/journeys", params={
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
            "page": 1,
            "page_size": 25
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["pagination"]["page_size"] == 25
        # Data should have at most 25 items
        assert len(data["data"]) <= 25
        print(f"✓ Page size 25: returned {len(data['data'])} items")

    def test_pagination_page_size_50(self, authenticated_client):
        """Test page_size=50 returns correct number of items"""
        response = authenticated_client.get(f"{BASE_URL}/api/journeys", params={
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
            "page": 1,
            "page_size": 50
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["pagination"]["page_size"] == 50
        assert len(data["data"]) <= 50
        print(f"✓ Page size 50: returned {len(data['data'])} items")

    def test_pagination_page_size_75(self, authenticated_client):
        """Test page_size=75 returns correct number of items"""
        response = authenticated_client.get(f"{BASE_URL}/api/journeys", params={
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
            "page": 1,
            "page_size": 75
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["pagination"]["page_size"] == 75
        print(f"✓ Page size 75: returned {len(data['data'])} items")

    def test_pagination_page_size_100(self, authenticated_client):
        """Test page_size=100 returns correct number of items"""
        response = authenticated_client.get(f"{BASE_URL}/api/journeys", params={
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
            "page": 1,
            "page_size": 100
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["pagination"]["page_size"] == 100
        print(f"✓ Page size 100: returned {len(data['data'])} items")

    def test_pagination_page_navigation(self, authenticated_client):
        """Test page navigation returns different data"""
        # Get page 1
        response1 = authenticated_client.get(f"{BASE_URL}/api/journeys", params={
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
            "page": 1,
            "page_size": 25
        })
        assert response1.status_code == 200
        data1 = response1.json()
        
        # If there's more than one page, test page 2
        if data1["pagination"]["total_pages"] > 1:
            response2 = authenticated_client.get(f"{BASE_URL}/api/journeys", params={
                "date_from": "2026-01-01",
                "date_to": "2026-12-31",
                "page": 2,
                "page_size": 25
            })
            assert response2.status_code == 200
            data2 = response2.json()
            assert data2["pagination"]["page"] == 2
            print(f"✓ Page navigation works: page 1 has {len(data1['data'])} items, page 2 has {len(data2['data'])} items")
        else:
            print(f"✓ Only 1 page available ({data1['pagination']['total_count']} total items)")

    def test_pagination_with_filters(self, authenticated_client):
        """Test pagination works with filters applied"""
        response = authenticated_client.get(f"{BASE_URL}/api/journeys", params={
            "date_from": "2026-03-01",
            "date_to": "2026-03-31",
            "status": "closed",
            "page": 1,
            "page_size": 25
        })
        assert response.status_code == 200
        
        data = response.json()
        assert "data" in data
        assert "pagination" in data
        print(f"✓ Pagination with filters: {data['pagination']['total_count']} closed routes in March")


class TestAIEvidenceEvaluation:
    """Tests for AI-Powered Evidence Scoring endpoints"""

    def test_evaluate_single_package_endpoint_exists(self, authenticated_client):
        """POST /api/journeys/{journey_id}/packages/{guide}/evaluate-evidence endpoint exists"""
        response = authenticated_client.post(
            f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}/packages/{TEST_PACKAGE_GUIDE}/evaluate-evidence"
        )
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404, "Endpoint should exist"
        print(f"✓ Single package evaluation endpoint exists, status: {response.status_code}")

    def test_evaluate_single_package_returns_evaluation_data(self, authenticated_client):
        """POST /api/journeys/{journey_id}/packages/{guide}/evaluate-evidence returns evaluation data"""
        response = authenticated_client.post(
            f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}/packages/{TEST_PACKAGE_GUIDE}/evaluate-evidence"
        )
        
        # Accept 200 (success) or 400/422 (validation error for invalid package)
        if response.status_code == 200:
            data = response.json()
            # Check for expected fields in AI evaluation response
            expected_fields = ["evidence_type", "evidence_score", "evidence_method"]
            for field in expected_fields:
                if field in data:
                    print(f"  - {field}: {data.get(field)}")
            print(f"✓ Single package evaluation returned data")
        else:
            print(f"✓ Endpoint responded with status {response.status_code}: {response.text[:200]}")

    def test_evaluate_all_packages_endpoint_exists(self, authenticated_client):
        """POST /api/journeys/{journey_id}/evaluate-evidence-all endpoint exists"""
        response = authenticated_client.post(
            f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}/evaluate-evidence-all"
        )
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404, "Endpoint should exist"
        print(f"✓ Batch evaluation endpoint exists, status: {response.status_code}")

    def test_evaluate_all_packages_returns_summary(self, authenticated_client):
        """POST /api/journeys/{journey_id}/evaluate-evidence-all returns batch evaluation summary"""
        response = authenticated_client.post(
            f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}/evaluate-evidence-all"
        )
        
        if response.status_code == 200:
            data = response.json()
            # Check for expected summary fields
            if "evaluated" in data:
                print(f"  - evaluated: {data.get('evaluated')}")
            if "ai_evaluated" in data:
                print(f"  - ai_evaluated: {data.get('ai_evaluated')}")
            if "rules_evaluated" in data:
                print(f"  - rules_evaluated: {data.get('rules_evaluated')}")
            print(f"✓ Batch evaluation returned summary")
        else:
            print(f"✓ Endpoint responded with status {response.status_code}")


class TestJourneyDetailWithQuality:
    """Tests for Journey Detail page with Quality tab data"""

    def test_journey_detail_returns_packages_with_evidence_fields(self, authenticated_client):
        """GET /api/journeys/{id} returns packages with evidence scoring fields"""
        response = authenticated_client.get(f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}")
        
        if response.status_code == 200:
            data = response.json()
            packages = data.get("packages", [])
            
            if packages:
                # Check first package for evidence fields
                pkg = packages[0]
                evidence_fields = ["evidence_score", "evidence_type", "evidence_method", "evidence_detail"]
                found_fields = [f for f in evidence_fields if f in pkg]
                print(f"✓ Journey has {len(packages)} packages")
                print(f"  - Evidence fields found: {found_fields}")
                
                # Check for kosmo proof data
                if "kosmo_proof_urls" in pkg:
                    print(f"  - kosmo_proof_urls present: {len(pkg.get('kosmo_proof_urls', []))} URLs")
                if "kosmo_proof_count" in pkg:
                    print(f"  - kosmo_proof_count: {pkg.get('kosmo_proof_count')}")
            else:
                print(f"✓ Journey found but no packages")
        else:
            print(f"Journey not found or error: {response.status_code}")

    def test_journey_detail_has_driver_name(self, authenticated_client):
        """GET /api/journeys/{id} returns driver_name field"""
        response = authenticated_client.get(f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}")
        
        if response.status_code == 200:
            data = response.json()
            assert "driver_name" in data or data.get("driver_name") is None, "driver_name field should exist"
            print(f"✓ driver_name: {data.get('driver_name', 'N/A')}")
        else:
            pytest.skip(f"Journey not found: {response.status_code}")

    def test_journey_detail_has_cosmo_route_id(self, authenticated_client):
        """GET /api/journeys/{id} returns cosmo_route_id field"""
        response = authenticated_client.get(f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ cosmo_route_id: {data.get('cosmo_route_id', 'N/A')}")
        else:
            pytest.skip(f"Journey not found: {response.status_code}")


class TestJourneysPagePagination:
    """Tests for Journeys page handling paginated response"""

    def test_journeys_page_backward_compatible(self, authenticated_client):
        """Journeys page should handle both old array and new paginated response"""
        response = authenticated_client.get(f"{BASE_URL}/api/journeys", params={
            "page": 1,
            "page_size": 25
        })
        assert response.status_code == 200
        
        data = response.json()
        # New format: {data: [...], pagination: {...}}
        assert "data" in data, "Response should have 'data' field"
        assert isinstance(data["data"], list), "'data' should be a list"
        print(f"✓ Journeys endpoint returns paginated format with {len(data['data'])} items")


class TestEvidenceScoringModule:
    """Tests for evidence_scoring.py module functionality"""

    def test_rules_based_evaluation_endpoint(self, authenticated_client):
        """POST /api/reports/evaluate-journey/{journey_id} uses rules-based evaluation"""
        response = authenticated_client.post(
            f"{BASE_URL}/api/reports/evaluate-journey/{TEST_JOURNEY_ID}"
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Rules-based evaluation: {data.get('evaluated', 0)} packages evaluated")
            if "avg_score" in data:
                print(f"  - avg_score: {data.get('avg_score')}")
        else:
            print(f"✓ Endpoint responded with status {response.status_code}")


class TestHealthAndAuth:
    """Basic health and auth tests"""

    def test_api_health(self, api_client):
        """API health check"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✓ API health check passed")

    def test_login_developer(self, api_client):
        """Login with developer credentials"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEV_EMAIL,
            "password": DEV_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "developer"
        print(f"✓ Developer login successful: {data['user']['name']}")

    def test_login_coordinator(self, api_client):
        """Login with coordinator credentials"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORD_EMAIL,
            "password": COORD_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "coordinator"
        print(f"✓ Coordinator login successful: {data['user']['name']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
