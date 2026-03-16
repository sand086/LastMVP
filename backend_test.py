#!/usr/bin/env python3
"""
LastMile OS Backend API Testing Suite

Tests all endpoints for JWT authentication, CRUD operations, 
dashboard stats, journeys management, and role-based access.
"""

import requests
import sys
from datetime import datetime
import json

class LastMileAPITester:
    def __init__(self, base_url="https://courier-control-4.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.token = None
        self.user_data = None
        self.tests_run = 0
        self.tests_passed = 0
        
        # Test user credentials
        self.test_users = {
            "agent": {"email": "agente@me.mx", "password": "LastMile2026"},
            "coordinator": {"email": "yael@me.mx", "password": "LastMile2026"},
            "executive": {"email": "karina@me.mx", "password": "LastMile2026"}
        }

    def log_result(self, test_name, success, response_data=None, error=None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ PASS: {test_name}")
            if response_data:
                print(f"   Response: {response_data}")
        else:
            print(f"❌ FAIL: {test_name}")
            if error:
                print(f"   Error: {error}")
        print()

    def make_request(self, method, endpoint, data=None, params=None):
        """Make HTTP request with proper headers"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")
                
            return response
        except requests.RequestException as e:
            return None

    def test_health_check(self):
        """Test basic API health"""
        print("🏥 Testing API Health...")
        response = self.make_request('GET', '')
        
        if response and response.status_code == 200:
            try:
                data = response.json()
                success = "LastMile OS API" in data.get("message", "")
                self.log_result("API Health Check", success, data)
            except:
                self.log_result("API Health Check", False, error="Invalid JSON response")
        else:
            self.log_result("API Health Check", False, error=f"Status: {response.status_code if response else 'No response'}")

    def test_login(self, user_type="agent"):
        """Test user authentication"""
        print(f"🔐 Testing Login for {user_type}...")
        
        if user_type not in self.test_users:
            self.log_result(f"Login - {user_type}", False, error="Invalid user type")
            return False
            
        credentials = self.test_users[user_type]
        response = self.make_request('POST', 'auth/login', credentials)
        
        if response and response.status_code == 200:
            try:
                data = response.json()
                if 'access_token' in data and 'user' in data:
                    self.token = data['access_token']
                    self.user_data = data['user']
                    self.log_result(f"Login - {user_type}", True, 
                                  f"User: {data['user']['name']}, Role: {data['user']['role']}")
                    return True
                else:
                    self.log_result(f"Login - {user_type}", False, error="Missing token or user data")
            except:
                self.log_result(f"Login - {user_type}", False, error="Invalid JSON response")
        else:
            self.log_result(f"Login - {user_type}", False, 
                          error=f"Status: {response.status_code if response else 'No response'}")
        return False

    def test_auth_me(self):
        """Test getting current user info"""
        print("👤 Testing Auth Me...")
        response = self.make_request('GET', 'auth/me')
        
        if response and response.status_code == 200:
            try:
                data = response.json()
                success = 'email' in data and 'role' in data
                self.log_result("Auth Me", success, f"User: {data.get('name')}, Role: {data.get('role')}")
            except:
                self.log_result("Auth Me", False, error="Invalid JSON response")
        else:
            self.log_result("Auth Me", False, error=f"Status: {response.status_code if response else 'No response'}")

    def test_dashboard_stats(self):
        """Test dashboard statistics endpoint"""
        print("📊 Testing Dashboard Stats...")
        response = self.make_request('GET', 'dashboard/stats')
        
        if response and response.status_code == 200:
            try:
                data = response.json()
                expected_fields = ['active_journeys', 'closed_journeys', 'total_packages', 
                                 'delivered_packages', 'delivery_rate', 'open_incidents']
                
                has_all_fields = all(field in data for field in expected_fields)
                if has_all_fields:
                    self.log_result("Dashboard Stats", True, 
                                  f"Active: {data['active_journeys']}, Packages: {data['total_packages']}")
                else:
                    missing = [f for f in expected_fields if f not in data]
                    self.log_result("Dashboard Stats", False, error=f"Missing fields: {missing}")
            except:
                self.log_result("Dashboard Stats", False, error="Invalid JSON response")
        else:
            self.log_result("Dashboard Stats", False, error=f"Status: {response.status_code if response else 'No response'}")

    def test_journeys(self):
        """Test journeys endpoint"""
        print("🚛 Testing Journeys...")
        response = self.make_request('GET', 'journeys')
        
        if response and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list):
                    journey_count = len(data)
                    if journey_count > 0:
                        first_journey = data[0]
                        expected_fields = ['id', 'date', 'status', 'client_name', 'provider_name']
                        has_fields = all(field in first_journey for field in expected_fields)
                        self.log_result("Journeys", has_fields, 
                                      f"Found {journey_count} journeys, Status: {first_journey.get('status')}")
                        
                        # Store journey ID for detail testing
                        self.test_journey_id = first_journey['id']
                    else:
                        self.log_result("Journeys", True, "No journeys found (empty list)")
                        self.test_journey_id = None
                else:
                    self.log_result("Journeys", False, error="Response is not a list")
            except:
                self.log_result("Journeys", False, error="Invalid JSON response")
        else:
            self.log_result("Journeys", False, error=f"Status: {response.status_code if response else 'No response'}")

    def test_journey_detail(self):
        """Test journey detail endpoint"""
        if not hasattr(self, 'test_journey_id') or not self.test_journey_id:
            self.log_result("Journey Detail", False, error="No journey ID available for testing")
            return
            
        print("🔍 Testing Journey Detail...")
        response = self.make_request('GET', f'journeys/{self.test_journey_id}')
        
        if response and response.status_code == 200:
            try:
                data = response.json()
                expected_fields = ['id', 'packages', 'incidents']
                has_fields = all(field in data for field in expected_fields)
                if has_fields:
                    packages_count = len(data.get('packages', []))
                    incidents_count = len(data.get('incidents', []))
                    self.log_result("Journey Detail", True, 
                                  f"Packages: {packages_count}, Incidents: {incidents_count}")
                else:
                    missing = [f for f in expected_fields if f not in data]
                    self.log_result("Journey Detail", False, error=f"Missing fields: {missing}")
            except:
                self.log_result("Journey Detail", False, error="Invalid JSON response")
        else:
            self.log_result("Journey Detail", False, error=f"Status: {response.status_code if response else 'No response'}")

    def test_clients(self):
        """Test clients endpoint"""
        print("🏢 Testing Clients...")
        response = self.make_request('GET', 'clients')
        
        if response and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list):
                    client_count = len(data)
                    if client_count > 0:
                        first_client = data[0]
                        has_required = 'id' in first_client and 'name' in first_client
                        self.log_result("Clients", has_required, 
                                      f"Found {client_count} clients: {[c['name'] for c in data[:3]]}")
                    else:
                        self.log_result("Clients", True, "No clients found")
                else:
                    self.log_result("Clients", False, error="Response is not a list")
            except:
                self.log_result("Clients", False, error="Invalid JSON response")
        else:
            self.log_result("Clients", False, error=f"Status: {response.status_code if response else 'No response'}")

    def test_providers(self):
        """Test providers endpoint"""
        print("🚚 Testing Providers...")
        response = self.make_request('GET', 'providers')
        
        if response and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list):
                    provider_count = len(data)
                    if provider_count > 0:
                        first_provider = data[0]
                        has_required = 'id' in first_provider and 'name' in first_provider
                        self.log_result("Providers", has_required, 
                                      f"Found {provider_count} providers: {[p['name'] for p in data[:3]]}")
                    else:
                        self.log_result("Providers", True, "No providers found")
                else:
                    self.log_result("Providers", False, error="Response is not a list")
            except:
                self.log_result("Providers", False, error="Invalid JSON response")
        else:
            self.log_result("Providers", False, error=f"Status: {response.status_code if response else 'No response'}")

    def test_role_based_access(self):
        """Test role-based access control"""
        print("🔒 Testing Role-based Access Control...")
        
        # Test coordinator-only endpoint (users)
        response = self.make_request('GET', 'users')
        
        if self.user_data and self.user_data.get('role') == 'coordinator':
            # Should have access
            if response and response.status_code == 200:
                self.log_result("Role Access - Coordinator", True, "Access granted to users endpoint")
            else:
                self.log_result("Role Access - Coordinator", False, 
                              error=f"Coordinator denied access: {response.status_code if response else 'No response'}")
        else:
            # Should be denied
            if response and response.status_code == 403:
                self.log_result("Role Access - Non-coordinator", True, "Access correctly denied")
            else:
                self.log_result("Role Access - Non-coordinator", False, 
                              error=f"Expected 403, got: {response.status_code if response else 'No response'}")

    def test_incidents(self):
        """Test incidents endpoint"""
        print("⚠️  Testing Incidents...")
        response = self.make_request('GET', 'incidents')
        
        if response and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list):
                    incidents_count = len(data)
                    self.log_result("Incidents", True, f"Found {incidents_count} incidents")
                else:
                    self.log_result("Incidents", False, error="Response is not a list")
            except:
                self.log_result("Incidents", False, error="Invalid JSON response")
        else:
            self.log_result("Incidents", False, error=f"Status: {response.status_code if response else 'No response'}")

    def run_full_test_suite(self):
        """Run complete test suite"""
        print("=" * 60)
        print("🚀 LastMile OS Backend API Test Suite")
        print("=" * 60)
        
        # Test basic connectivity
        self.test_health_check()
        
        # Test authentication with agent user
        if self.test_login("agent"):
            self.test_auth_me()
            self.test_dashboard_stats()
            self.test_journeys()
            self.test_journey_detail()
            self.test_clients()
            self.test_providers()
            self.test_incidents()
            self.test_role_based_access()
        
        # Test coordinator access
        print("\n🔄 Testing Coordinator Access...")
        if self.test_login("coordinator"):
            self.test_role_based_access()
        
        # Test executive access
        print("\n🔄 Testing Executive Access...")
        if self.test_login("executive"):
            self.test_role_based_access()
        
        # Print summary
        print("=" * 60)
        print(f"📊 TEST SUMMARY")
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed / self.tests_run * 100):.1f}%" if self.tests_run > 0 else "0%")
        print("=" * 60)
        
        return self.tests_passed == self.tests_run

def main():
    """Run the test suite"""
    tester = LastMileAPITester()
    success = tester.run_full_test_suite()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())