"""
Iteration 33 - Discrepancy Detection Tests
Tests for confidence evaluation and discrepancy review endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEV_EMAIL = "dev@me.mx"
DEV_PASSWORD = "LastMile2026"

# Test journey with packages
TEST_JOURNEY_ID = "0c628824-b509-40a6-a7fd-b9b210b3eacd"


class TestDiscrepancyDetection:
    """Tests for discrepancy detection and confidence evaluation"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: authenticate and get token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get token
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEV_EMAIL,
            "password": DEV_PASSWORD
        })
        
        if login_response.status_code == 200:
            token = login_response.json().get("access_token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip(f"Authentication failed: {login_response.status_code}")
    
    # ─── Test 1: Evaluate Confidence Endpoint ───
    def test_evaluate_confidence_returns_expected_fields(self):
        """POST /api/journeys/{journey_id}/guides/evaluate-confidence returns evaluated, discrepancies, avg_confidence"""
        response = self.session.post(f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}/guides/evaluate-confidence")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify required fields exist
        assert "evaluated" in data, "Response missing 'evaluated' field"
        assert "discrepancies" in data, "Response missing 'discrepancies' field"
        assert "avg_confidence" in data, "Response missing 'avg_confidence' field"
        assert "message" in data, "Response missing 'message' field"
        
        # Verify data types
        assert isinstance(data["evaluated"], int), "evaluated should be an integer"
        assert isinstance(data["discrepancies"], int), "discrepancies should be an integer"
        assert isinstance(data["avg_confidence"], (int, float)), "avg_confidence should be a number"
        
        # Verify values are reasonable
        assert data["evaluated"] >= 0, "evaluated should be non-negative"
        assert data["discrepancies"] >= 0, "discrepancies should be non-negative"
        assert 0 <= data["avg_confidence"] <= 100, "avg_confidence should be between 0 and 100"
        
        print(f"✓ Evaluate confidence: evaluated={data['evaluated']}, discrepancies={data['discrepancies']}, avg_confidence={data['avg_confidence']}")
    
    def test_evaluate_confidence_nonexistent_journey(self):
        """POST /api/journeys/{invalid_id}/guides/evaluate-confidence returns 404"""
        response = self.session.post(f"{BASE_URL}/api/journeys/nonexistent-journey-id/guides/evaluate-confidence")
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Evaluate confidence with invalid journey returns 404")
    
    # ─── Test 2: Review Discrepancy - Invalid Decision ───
    def test_review_discrepancy_invalid_decision_returns_400(self):
        """PATCH /api/journeys/{journey_id}/guides/{guide_id}/review with invalid decision returns 400"""
        # First get a package from the journey (packages are embedded in journey response)
        journey_response = self.session.get(f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}")
        assert journey_response.status_code == 200, f"Failed to get journey: {journey_response.status_code}"
        
        journey = journey_response.json()
        packages = journey.get("packages", [])
        assert len(packages) > 0, "No packages found in journey"
        
        # Get first package's guide ID
        pkg = packages[0]
        guide_id = pkg.get("order_reference_id") or pkg.get("tracking_number") or pkg.get("id")
        
        # Try invalid decision
        response = self.session.patch(
            f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}/guides/{guide_id}/review",
            json={"decision": "invalid_decision"}
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, "Response should contain error detail"
        print(f"✓ Invalid decision returns 400: {data.get('detail')}")
    
    # ─── Test 3: Review Discrepancy - Confirm Return ───
    def test_review_discrepancy_confirm_return(self):
        """PATCH /api/journeys/{journey_id}/guides/{guide_id}/review with decision='confirm_return' changes status"""
        # Get packages (embedded in journey response)
        journey_response = self.session.get(f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}")
        assert journey_response.status_code == 200
        
        journey = journey_response.json()
        packages = journey.get("packages", [])
        assert len(packages) > 0
        
        # Find a package that's not already returned (to test the flow)
        test_pkg = None
        for pkg in packages:
            if pkg.get("status") != "returned":
                test_pkg = pkg
                break
        
        if not test_pkg:
            pytest.skip("No suitable package found for confirm_return test")
        
        guide_id = test_pkg.get("order_reference_id") or test_pkg.get("tracking_number") or test_pkg.get("id")
        original_status = test_pkg.get("status")
        
        # Call review endpoint with confirm_return
        response = self.session.patch(
            f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}/guides/{guide_id}/review",
            json={"decision": "confirm_return"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, "Response should indicate success"
        assert data.get("decision") == "confirm_return", "Response should echo the decision"
        assert "package_id" in data, "Response should contain package_id"
        
        # Verify the package status changed to 'returned'
        verify_response = self.session.get(f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}")
        assert verify_response.status_code == 200
        
        updated_journey = verify_response.json()
        updated_packages = updated_journey.get("packages", [])
        updated_pkg = next((p for p in updated_packages if p.get("id") == test_pkg.get("id")), None)
        
        assert updated_pkg is not None, "Package not found after update"
        assert updated_pkg.get("status") == "returned", f"Status should be 'returned', got {updated_pkg.get('status')}"
        assert updated_pkg.get("manual_review", {}).get("decision") == "confirm_return"
        
        print(f"✓ confirm_return: status changed from '{original_status}' to 'returned'")
    
    # ─── Test 4: Review Discrepancy - Mark Valid ───
    def test_review_discrepancy_mark_valid(self):
        """PATCH /api/journeys/{journey_id}/guides/{guide_id}/review with decision='mark_valid' clears discrepancy"""
        # Get packages (embedded in journey response)
        journey_response = self.session.get(f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}")
        assert journey_response.status_code == 200
        
        journey = journey_response.json()
        packages = journey.get("packages", [])
        assert len(packages) > 0
        
        # Find a package to test mark_valid (any package works)
        test_pkg = packages[1] if len(packages) > 1 else packages[0]
        guide_id = test_pkg.get("order_reference_id") or test_pkg.get("tracking_number") or test_pkg.get("id")
        original_status = test_pkg.get("status")
        
        # Call review endpoint with mark_valid
        response = self.session.patch(
            f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}/guides/{guide_id}/review",
            json={"decision": "mark_valid"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, "Response should indicate success"
        assert data.get("decision") == "mark_valid", "Response should echo the decision"
        
        # Verify the package discrepancy is cleared and status unchanged
        verify_response = self.session.get(f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}")
        assert verify_response.status_code == 200
        
        updated_journey = verify_response.json()
        updated_packages = updated_journey.get("packages", [])
        updated_pkg = next((p for p in updated_packages if p.get("id") == test_pkg.get("id")), None)
        
        assert updated_pkg is not None, "Package not found after update"
        # Status should remain unchanged (not changed to returned)
        assert updated_pkg.get("status") == original_status or updated_pkg.get("status") != "returned" or original_status == "returned", \
            f"Status should remain unchanged or not be 'returned' unless it was already"
        
        # Discrepancy should be cleared
        discrepancy = updated_pkg.get("discrepancy", {})
        assert discrepancy.get("detected") == False, "Discrepancy should be cleared (detected=False)"
        
        # Manual review should be recorded
        manual_review = updated_pkg.get("manual_review", {})
        assert manual_review.get("decision") == "mark_valid", "Manual review decision should be 'mark_valid'"
        
        print(f"✓ mark_valid: discrepancy cleared, status preserved as '{updated_pkg.get('status')}'")
    
    # ─── Test 5: Review Nonexistent Guide ───
    def test_review_discrepancy_nonexistent_guide(self):
        """PATCH /api/journeys/{journey_id}/guides/{invalid_guide}/review returns 404"""
        response = self.session.patch(
            f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}/guides/NONEXISTENT-GUIDE-12345/review",
            json={"decision": "mark_valid"}
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Review nonexistent guide returns 404")
    
    # ─── Test 6: Verify Confidence Data in Packages ───
    def test_packages_have_confidence_data_after_evaluation(self):
        """After evaluate-confidence, packages should have confidence and discrepancy fields"""
        # First run evaluate-confidence
        eval_response = self.session.post(f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}/guides/evaluate-confidence")
        assert eval_response.status_code == 200
        
        # Get packages (embedded in journey response)
        journey_response = self.session.get(f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}")
        assert journey_response.status_code == 200
        
        journey = journey_response.json()
        packages = journey.get("packages", [])
        assert len(packages) > 0
        
        # Check that packages have confidence data
        packages_with_confidence = [p for p in packages if p.get("confidence")]
        assert len(packages_with_confidence) > 0, "At least some packages should have confidence data"
        
        # Verify confidence structure
        sample_pkg = packages_with_confidence[0]
        confidence = sample_pkg.get("confidence", {})
        
        assert "score" in confidence, "Confidence should have 'score' field"
        assert "level" in confidence, "Confidence should have 'level' field"
        assert "factors" in confidence, "Confidence should have 'factors' field"
        
        # Verify discrepancy structure
        discrepancy = sample_pkg.get("discrepancy", {})
        assert "detected" in discrepancy, "Discrepancy should have 'detected' field"
        
        print(f"✓ Packages have confidence data: {len(packages_with_confidence)}/{len(packages)} packages with confidence scores")


class TestJourneyExists:
    """Verify test journey exists and has packages"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: authenticate"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEV_EMAIL,
            "password": DEV_PASSWORD
        })
        
        if login_response.status_code == 200:
            token = login_response.json().get("access_token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip("Authentication failed")
    
    def test_journey_exists(self):
        """Verify test journey exists"""
        response = self.session.get(f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}")
        assert response.status_code == 200, f"Journey not found: {response.status_code}"
        
        journey = response.json()
        assert journey.get("id") == TEST_JOURNEY_ID
        print(f"✓ Journey exists: {journey.get('route_name', 'N/A')}")
    
    def test_journey_has_packages(self):
        """Verify test journey has packages"""
        response = self.session.get(f"{BASE_URL}/api/journeys/{TEST_JOURNEY_ID}")
        assert response.status_code == 200
        
        journey = response.json()
        packages = journey.get("packages", [])
        assert len(packages) > 0, "Journey should have packages"
        print(f"✓ Journey has {len(packages)} packages")
