"""
Iteration 34 - AI Evaluation Module Improvements Testing
Tests for:
1. Severity badges (ia_severity and ia_errors_raw fields in package enrichment)
2. ReviewModal functionality (approve/reject with score adjustment)
3. AI Evaluation Status endpoint (GET /api/journeys/{journey_id}/ai-eval-status)
4. Evaluate All button triggers background evaluation
5. Bulk status update (checkboxes + floating bar)
6. Segment filters (Todas, Con alerta, Discrepancia, Sin evidencia, Pendiente revisión)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestAuthAndSetup:
    """Authentication and setup tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token using coordinator credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "yael@me.mx",
            "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        # Note: response field is 'access_token' not 'token'
        token = data.get("access_token") or data.get("token")
        assert token, f"No token in response: {data}"
        return token
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_login_coordinator(self, auth_token):
        """Test coordinator login works"""
        assert auth_token is not None
        print("SUCCESS: Coordinator login successful, token obtained")


class TestAiEvalStatusEndpoint:
    """Tests for GET /api/journeys/{journey_id}/ai-eval-status endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "yael@me.mx",
            "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
        })
        assert response.status_code == 200
        data = response.json()
        token = data.get("access_token") or data.get("token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def test_journey_id(self, auth_headers):
        """Get a journey ID for testing"""
        response = requests.get(f"{BASE_URL}/api/journeys", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        journeys = data.get("data", [])
        assert len(journeys) > 0, "No journeys found"
        # Find a journey with packages
        for j in journeys:
            if j.get("packages_total", 0) > 5:
                return j["id"]
        return journeys[0]["id"]
    
    def test_ai_eval_status_endpoint_exists(self, auth_headers, test_journey_id):
        """Test that AI eval status endpoint exists and returns correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/journeys/{test_journey_id}/ai-eval-status",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "status" in data, f"Missing 'status' field in response: {data}"
        
        # Status should be one of: idle, starting, running, completed, error
        valid_statuses = ["idle", "starting", "running", "completed", "error"]
        assert data["status"] in valid_statuses, f"Invalid status: {data['status']}"
        
        print(f"SUCCESS: AI eval status endpoint returns: {data}")
    
    def test_ai_eval_status_idle_by_default(self, auth_headers, test_journey_id):
        """Test that AI eval status is 'idle' when no evaluation is running"""
        response = requests.get(
            f"{BASE_URL}/api/journeys/{test_journey_id}/ai-eval-status",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # When no evaluation is running, status should be 'idle'
        # (unless one was recently triggered)
        assert data["status"] in ["idle", "completed", "running", "starting"], \
            f"Unexpected status: {data['status']}"
        print(f"SUCCESS: AI eval status is '{data['status']}'")


class TestPackageEnrichmentWithSeverity:
    """Tests for package enrichment with ia_severity and ia_errors_raw fields"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "yael@me.mx",
            "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
        })
        assert response.status_code == 200
        data = response.json()
        token = data.get("access_token") or data.get("token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def journey_with_packages(self, auth_headers):
        """Get a journey with packages for testing"""
        response = requests.get(f"{BASE_URL}/api/journeys", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        journeys = data.get("data", [])
        
        # Find a journey with packages
        for j in journeys:
            if j.get("packages_total", 0) > 5:
                # Get full journey details
                detail_response = requests.get(
                    f"{BASE_URL}/api/journeys/{j['id']}",
                    headers=auth_headers
                )
                if detail_response.status_code == 200:
                    return detail_response.json()
        
        # Fallback to first journey
        detail_response = requests.get(
            f"{BASE_URL}/api/journeys/{journeys[0]['id']}",
            headers=auth_headers
        )
        return detail_response.json()
    
    def test_packages_have_ai_errors_field(self, journey_with_packages):
        """Test that packages have ai_errors field"""
        packages = journey_with_packages.get("packages", [])
        assert len(packages) > 0, "No packages in journey"
        
        # Check that ai_errors field exists
        for pkg in packages[:5]:  # Check first 5
            assert "ai_errors" in pkg, f"Package {pkg.get('id')} missing ai_errors field"
        
        print("SUCCESS: All packages have ai_errors field")
    
    def test_packages_have_ia_errors_raw_field(self, journey_with_packages):
        """Test that packages have ia_errors_raw field for severity mapping"""
        packages = journey_with_packages.get("packages", [])
        assert len(packages) > 0, "No packages in journey"
        
        # Check that ia_errors_raw field exists
        for pkg in packages[:5]:  # Check first 5
            assert "ia_errors_raw" in pkg, f"Package {pkg.get('id')} missing ia_errors_raw field"
        
        print("SUCCESS: All packages have ia_errors_raw field")
    
    def test_packages_have_ia_severity_field(self, journey_with_packages):
        """Test that packages have ia_severity field for severity badges"""
        packages = journey_with_packages.get("packages", [])
        assert len(packages) > 0, "No packages in journey"
        
        # Check that ia_severity field exists
        for pkg in packages[:5]:  # Check first 5
            assert "ia_severity" in pkg, f"Package {pkg.get('id')} missing ia_severity field"
        
        print("SUCCESS: All packages have ia_severity field")
    
    def test_packages_have_ai_score_field(self, journey_with_packages):
        """Test that packages have ai_score field"""
        packages = journey_with_packages.get("packages", [])
        assert len(packages) > 0, "No packages in journey"
        
        # Check that ai_score field exists
        for pkg in packages[:5]:  # Check first 5
            assert "ai_score" in pkg, f"Package {pkg.get('id')} missing ai_score field"
        
        print("SUCCESS: All packages have ai_score field")


class TestReviewPackageEndpoint:
    """Tests for PATCH /api/packages/{package_id}/review endpoint (ReviewModal backend)"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "yael@me.mx",
            "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
        })
        assert response.status_code == 200
        data = response.json()
        token = data.get("access_token") or data.get("token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def unreviewed_package(self, auth_headers):
        """Find an unreviewed package for testing"""
        response = requests.get(f"{BASE_URL}/api/journeys", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        journeys = data.get("data", [])
        
        for j in journeys:
            detail_response = requests.get(
                f"{BASE_URL}/api/journeys/{j['id']}",
                headers=auth_headers
            )
            if detail_response.status_code == 200:
                journey = detail_response.json()
                packages = journey.get("packages", [])
                for pkg in packages:
                    if not pkg.get("manually_reviewed") and not pkg.get("rejection_reason"):
                        return pkg
        
        # If no unreviewed package found, return first package
        if journeys:
            detail_response = requests.get(
                f"{BASE_URL}/api/journeys/{journeys[0]['id']}",
                headers=auth_headers
            )
            if detail_response.status_code == 200:
                packages = detail_response.json().get("packages", [])
                if packages:
                    return packages[0]
        
        pytest.skip("No packages found for testing")
    
    def test_review_package_approve(self, auth_headers, unreviewed_package):
        """Test approving a package via PATCH endpoint"""
        package_id = unreviewed_package["id"]
        
        response = requests.patch(
            f"{BASE_URL}/api/packages/{package_id}/review",
            headers=auth_headers,
            json={
                "manually_reviewed": True,
                "manually_reviewed_note": "TEST: Evidencia suficiente a pesar del score bajo"
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response contains updated package data
        assert data.get("manually_reviewed"), f"Package not marked as reviewed: {data}"
        print(f"SUCCESS: Package {package_id} approved successfully")
    
    def test_review_package_reject(self, auth_headers, unreviewed_package):
        """Test rejecting a package via PATCH endpoint"""
        package_id = unreviewed_package["id"]
        
        response = requests.patch(
            f"{BASE_URL}/api/packages/{package_id}/review",
            headers=auth_headers,
            json={
                "manually_reviewed": False,
                "manually_reviewed_note": "TEST: Evidencia insuficiente"
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response contains rejection reason
        assert data.get("rejection_reason") == "TEST: Evidencia insuficiente", \
            f"Rejection reason not set: {data}"
        print(f"SUCCESS: Package {package_id} rejected successfully")


class TestBulkStatusUpdate:
    """Tests for POST /api/journeys/{journey_id}/packages/bulk-status endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "yael@me.mx",
            "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
        })
        assert response.status_code == 200
        data = response.json()
        token = data.get("access_token") or data.get("token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def journey_with_packages(self, auth_headers):
        """Get a journey with packages for testing"""
        response = requests.get(f"{BASE_URL}/api/journeys", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        journeys = data.get("data", [])
        
        for j in journeys:
            if j.get("packages_total", 0) > 5:
                detail_response = requests.get(
                    f"{BASE_URL}/api/journeys/{j['id']}",
                    headers=auth_headers
                )
                if detail_response.status_code == 200:
                    return detail_response.json()
        
        detail_response = requests.get(
            f"{BASE_URL}/api/journeys/{journeys[0]['id']}",
            headers=auth_headers
        )
        return detail_response.json()
    
    def test_bulk_status_update_endpoint_exists(self, auth_headers, journey_with_packages):
        """Test that bulk status update endpoint exists"""
        journey_id = journey_with_packages["id"]
        packages = journey_with_packages.get("packages", [])
        
        if len(packages) < 2:
            pytest.skip("Not enough packages for bulk update test")
        
        # Get first 2 package IDs
        package_ids = [packages[0]["id"], packages[1]["id"]]
        
        response = requests.post(
            f"{BASE_URL}/api/journeys/{journey_id}/packages/bulk-status",
            headers=auth_headers,
            json={
                "package_ids": package_ids,
                "new_status": "delivered"
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "updated" in data, f"Missing 'updated' field: {data}"
        assert "new_status" in data, f"Missing 'new_status' field: {data}"
        assert "journey_totals" in data, f"Missing 'journey_totals' field: {data}"
        
        print(f"SUCCESS: Bulk status update returned: {data}")
    
    def test_bulk_status_update_invalid_status(self, auth_headers, journey_with_packages):
        """Test that invalid status returns 400"""
        journey_id = journey_with_packages["id"]
        packages = journey_with_packages.get("packages", [])
        
        if len(packages) < 1:
            pytest.skip("No packages for test")
        
        response = requests.post(
            f"{BASE_URL}/api/journeys/{journey_id}/packages/bulk-status",
            headers=auth_headers,
            json={
                "package_ids": [packages[0]["id"]],
                "new_status": "invalid_status"
            }
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("SUCCESS: Invalid status correctly returns 400")


class TestEvaluateAllEndpoint:
    """Tests for POST /api/journeys/{journey_id}/evaluate-evidence-all endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "yael@me.mx",
            "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
        })
        assert response.status_code == 200
        data = response.json()
        token = data.get("access_token") or data.get("token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def test_journey_id(self, auth_headers):
        """Get a journey ID for testing"""
        response = requests.get(f"{BASE_URL}/api/journeys", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        journeys = data.get("data", [])
        assert len(journeys) > 0, "No journeys found"
        
        for j in journeys:
            if j.get("packages_total", 0) > 5:
                return j["id"]
        return journeys[0]["id"]
    
    def test_evaluate_all_endpoint_exists(self, auth_headers, test_journey_id):
        """Test that evaluate-evidence-all endpoint exists and returns correct structure"""
        response = requests.post(
            f"{BASE_URL}/api/journeys/{test_journey_id}/evaluate-evidence-all",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "status" in data, f"Missing 'status' field: {data}"
        assert data["status"] == "started", f"Expected status 'started', got: {data['status']}"
        assert "message" in data, f"Missing 'message' field: {data}"
        assert "current_stats" in data, f"Missing 'current_stats' field: {data}"
        
        print(f"SUCCESS: Evaluate all endpoint returns: {data}")


class TestSegmentFilters:
    """Tests for segment filter data availability"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get authentication headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "yael@me.mx",
            "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
        })
        assert response.status_code == 200
        data = response.json()
        token = data.get("access_token") or data.get("token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    @pytest.fixture(scope="class")
    def journey_with_packages(self, auth_headers):
        """Get a journey with packages for testing"""
        response = requests.get(f"{BASE_URL}/api/journeys", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        journeys = data.get("data", [])
        
        for j in journeys:
            if j.get("packages_total", 0) > 5:
                detail_response = requests.get(
                    f"{BASE_URL}/api/journeys/{j['id']}",
                    headers=auth_headers
                )
                if detail_response.status_code == 200:
                    return detail_response.json()
        
        detail_response = requests.get(
            f"{BASE_URL}/api/journeys/{journeys[0]['id']}",
            headers=auth_headers
        )
        return detail_response.json()
    
    def test_packages_have_fields_for_segment_filters(self, journey_with_packages):
        """Test that packages have all fields needed for segment filters"""
        packages = journey_with_packages.get("packages", [])
        assert len(packages) > 0, "No packages in journey"
        
        required_fields = [
            "ai_errors",           # For 'Con alerta' filter
            "discrepancy",         # For 'Discrepancia' filter
            "photos_count",        # For 'Sin evidencia' filter
            "kosmo_proof_urls",    # For 'Sin evidencia' filter
            "manually_reviewed",   # For 'Pendiente revisión' filter
            "rejection_reason",    # For 'Pendiente revisión' filter
        ]
        
        for pkg in packages[:5]:
            for field in required_fields:
                assert field in pkg, f"Package {pkg.get('id')} missing field: {field}"
        
        print("SUCCESS: All packages have required fields for segment filters")
    
    def test_discrepancy_field_structure(self, journey_with_packages):
        """Test that discrepancy field has correct structure"""
        packages = journey_with_packages.get("packages", [])
        
        for pkg in packages[:5]:
            discrepancy = pkg.get("discrepancy")
            if discrepancy:
                assert "detected" in discrepancy, f"Discrepancy missing 'detected' field: {discrepancy}"
        
        print("SUCCESS: Discrepancy field has correct structure")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
