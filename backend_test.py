#!/usr/bin/env python3
"""
Backend API Testing for Fuel Finder App
Tests all backend endpoints and functionality
"""

import requests
import json
import sys
from typing import Dict, Any, List

# Backend URL from frontend .env
BASE_URL = "https://fuel-locator-26.preview.emergentagent.com/api"

class FuelFinderAPITester:
    def __init__(self):
        self.base_url = BASE_URL
        self.session = requests.Session()
        self.session.timeout = 30
        self.test_results = []
        
    def log_test(self, test_name: str, success: bool, details: str = "", response_data: Any = None):
        """Log test results"""
        result = {
            "test": test_name,
            "success": success,
            "details": details,
            "response_data": response_data
        }
        self.test_results.append(result)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"   Details: {details}")
        if not success and response_data:
            print(f"   Response: {response_data}")
        print()

    def test_health_check(self):
        """Test GET /api/ health check endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/")
            
            if response.status_code == 200:
                data = response.json()
                expected_keys = ["message", "version"]
                
                if all(key in data for key in expected_keys):
                    if data["message"] == "Fuel Finder API" and data["version"] == "1.0.0":
                        self.log_test("Health Check Endpoint", True, 
                                    f"Correct response: {data}")
                    else:
                        self.log_test("Health Check Endpoint", False, 
                                    f"Incorrect message/version: {data}")
                else:
                    self.log_test("Health Check Endpoint", False, 
                                f"Missing required keys: {data}")
            else:
                self.log_test("Health Check Endpoint", False, 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("Health Check Endpoint", False, f"Exception: {str(e)}")

    def test_stations_endpoint_gas(self):
        """Test GET /api/stations with gas fuel type (NYC location)"""
        params = {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "fuel_type": "gas"
        }
        
        try:
            response = self.session.get(f"{self.base_url}/stations", params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check response structure
                required_keys = ["stations", "fuel_type", "user_location", "total_found"]
                if not all(key in data for key in required_keys):
                    self.log_test("Stations Endpoint (Gas - NYC)", False, 
                                f"Missing required keys in response: {list(data.keys())}")
                    return
                
                # Check fuel_type matches request
                if data["fuel_type"] != "gas":
                    self.log_test("Stations Endpoint (Gas - NYC)", False, 
                                f"Fuel type mismatch: expected 'gas', got '{data['fuel_type']}'")
                    return
                
                # Check user_location matches request
                user_loc = data["user_location"]
                if user_loc["latitude"] != 40.7128 or user_loc["longitude"] != -74.0060:
                    self.log_test("Stations Endpoint (Gas - NYC)", False, 
                                f"User location mismatch: {user_loc}")
                    return
                
                # Check stations array
                stations = data["stations"]
                if not isinstance(stations, list):
                    self.log_test("Stations Endpoint (Gas - NYC)", False, 
                                "Stations is not a list")
                    return
                
                if len(stations) == 0:
                    self.log_test("Stations Endpoint (Gas - NYC)", False, 
                                "No stations returned")
                    return
                
                # Check station structure
                station = stations[0]
                required_station_keys = [
                    "id", "place_id", "name", "address", "latitude", "longitude", 
                    "distance_miles", "gas_price", "gas_price_formatted", 
                    "diesel_price", "diesel_price_formatted", "fuel_options"
                ]
                
                missing_keys = [key for key in required_station_keys if key not in station]
                if missing_keys:
                    self.log_test("Stations Endpoint (Gas - NYC)", False, 
                                f"Station missing keys: {missing_keys}")
                    return
                
                # Check if stations are sorted by gas price (cheapest first)
                gas_prices = [s.get("gas_price") for s in stations if s.get("gas_price") is not None]
                if len(gas_prices) > 1:
                    is_sorted = all(gas_prices[i] <= gas_prices[i+1] for i in range(len(gas_prices)-1))
                    if not is_sorted:
                        self.log_test("Stations Endpoint (Gas - NYC)", False, 
                                    f"Stations not sorted by gas price: {gas_prices[:5]}")
                        return
                
                # Check distance calculation
                if station["distance_miles"] <= 0:
                    self.log_test("Stations Endpoint (Gas - NYC)", False, 
                                f"Invalid distance: {station['distance_miles']}")
                    return
                
                # Check that we don't exceed 10 stations
                if len(stations) > 10:
                    self.log_test("Stations Endpoint (Gas - NYC)", False, 
                                f"Too many stations returned: {len(stations)}")
                    return
                
                self.log_test("Stations Endpoint (Gas - NYC)", True, 
                            f"Found {len(stations)} stations, sorted by price")
                
            else:
                self.log_test("Stations Endpoint (Gas - NYC)", False, 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("Stations Endpoint (Gas - NYC)", False, f"Exception: {str(e)}")

    def test_stations_endpoint_diesel(self):
        """Test GET /api/stations with diesel fuel type (NYC location)"""
        params = {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "fuel_type": "diesel"
        }
        
        try:
            response = self.session.get(f"{self.base_url}/stations", params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check fuel_type matches request
                if data["fuel_type"] != "diesel":
                    self.log_test("Stations Endpoint (Diesel - NYC)", False, 
                                f"Fuel type mismatch: expected 'diesel', got '{data['fuel_type']}'")
                    return
                
                stations = data["stations"]
                if len(stations) == 0:
                    self.log_test("Stations Endpoint (Diesel - NYC)", False, 
                                "No stations returned")
                    return
                
                # Check if stations are sorted by diesel price (cheapest first)
                diesel_prices = [s.get("diesel_price") for s in stations if s.get("diesel_price") is not None]
                if len(diesel_prices) > 1:
                    is_sorted = all(diesel_prices[i] <= diesel_prices[i+1] for i in range(len(diesel_prices)-1))
                    if not is_sorted:
                        self.log_test("Stations Endpoint (Diesel - NYC)", False, 
                                    f"Stations not sorted by diesel price: {diesel_prices[:5]}")
                        return
                
                self.log_test("Stations Endpoint (Diesel - NYC)", True, 
                            f"Found {len(stations)} stations, sorted by diesel price")
                
            else:
                self.log_test("Stations Endpoint (Diesel - NYC)", False, 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("Stations Endpoint (Diesel - NYC)", False, f"Exception: {str(e)}")

    def test_stations_endpoint_default_fuel(self):
        """Test GET /api/stations with default fuel type (should be gas)"""
        params = {
            "latitude": 40.7128,
            "longitude": -74.0060
        }
        
        try:
            response = self.session.get(f"{self.base_url}/stations", params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check default fuel_type is gas
                if data["fuel_type"] != "gas":
                    self.log_test("Stations Endpoint (Default Fuel)", False, 
                                f"Default fuel type should be 'gas', got '{data['fuel_type']}'")
                    return
                
                self.log_test("Stations Endpoint (Default Fuel)", True, 
                            "Default fuel type correctly set to 'gas'")
                
            else:
                self.log_test("Stations Endpoint (Default Fuel)", False, 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("Stations Endpoint (Default Fuel)", False, f"Exception: {str(e)}")

    def test_stations_endpoint_la_location(self):
        """Test GET /api/stations with LA location"""
        params = {
            "latitude": 34.0522,
            "longitude": -118.2437,
            "fuel_type": "gas"
        }
        
        try:
            response = self.session.get(f"{self.base_url}/stations", params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check user_location matches request
                user_loc = data["user_location"]
                if user_loc["latitude"] != 34.0522 or user_loc["longitude"] != -118.2437:
                    self.log_test("Stations Endpoint (LA Location)", False, 
                                f"User location mismatch: {user_loc}")
                    return
                
                stations = data["stations"]
                if len(stations) == 0:
                    self.log_test("Stations Endpoint (LA Location)", False, 
                                "No stations returned for LA location")
                    return
                
                self.log_test("Stations Endpoint (LA Location)", True, 
                            f"Found {len(stations)} stations in LA")
                
            else:
                self.log_test("Stations Endpoint (LA Location)", False, 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("Stations Endpoint (LA Location)", False, f"Exception: {str(e)}")

    def test_stations_endpoint_missing_params(self):
        """Test GET /api/stations with missing required parameters"""
        try:
            # Test missing latitude
            response = self.session.get(f"{self.base_url}/stations", 
                                      params={"longitude": -74.0060})
            
            if response.status_code == 422:  # FastAPI validation error
                self.log_test("Stations Endpoint (Missing Latitude)", True, 
                            "Correctly returns 422 for missing latitude")
            else:
                self.log_test("Stations Endpoint (Missing Latitude)", False, 
                            f"Expected 422, got {response.status_code}")
            
            # Test missing longitude
            response = self.session.get(f"{self.base_url}/stations", 
                                      params={"latitude": 40.7128})
            
            if response.status_code == 422:  # FastAPI validation error
                self.log_test("Stations Endpoint (Missing Longitude)", True, 
                            "Correctly returns 422 for missing longitude")
            else:
                self.log_test("Stations Endpoint (Missing Longitude)", False, 
                            f"Expected 422, got {response.status_code}")
                
        except Exception as e:
            self.log_test("Stations Endpoint (Missing Params)", False, f"Exception: {str(e)}")

    def test_distance_calculation(self):
        """Test distance calculation accuracy"""
        params = {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "fuel_type": "gas"
        }
        
        try:
            response = self.session.get(f"{self.base_url}/stations", params=params)
            
            if response.status_code == 200:
                data = response.json()
                stations = data["stations"]
                
                if len(stations) == 0:
                    self.log_test("Distance Calculation", False, "No stations to test distance")
                    return
                
                # Check that all distances are reasonable (not 0, not extremely large)
                invalid_distances = []
                for station in stations:
                    distance = station["distance_miles"]
                    if distance <= 0 or distance > 50:  # Reasonable range for nearby stations
                        invalid_distances.append({
                            "name": station["name"],
                            "distance": distance
                        })
                
                if invalid_distances:
                    self.log_test("Distance Calculation", False, 
                                f"Invalid distances found: {invalid_distances}")
                else:
                    self.log_test("Distance Calculation", True, 
                                "All distances are within reasonable range")
                
            else:
                self.log_test("Distance Calculation", False, 
                            f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_test("Distance Calculation", False, f"Exception: {str(e)}")

    def run_all_tests(self):
        """Run all backend tests"""
        print("🚀 Starting Fuel Finder Backend API Tests")
        print(f"Base URL: {self.base_url}")
        print("=" * 60)
        
        # Test health check
        self.test_health_check()
        
        # Test stations endpoint with different parameters
        self.test_stations_endpoint_gas()
        self.test_stations_endpoint_diesel()
        self.test_stations_endpoint_default_fuel()
        self.test_stations_endpoint_la_location()
        
        # Test error handling
        self.test_stations_endpoint_missing_params()
        
        # Test specific functionality
        self.test_distance_calculation()
        
        # Summary
        print("=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests} ✅")
        print(f"Failed: {failed_tests} ❌")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"  - {result['test']}: {result['details']}")
        
        return failed_tests == 0

if __name__ == "__main__":
    tester = FuelFinderAPITester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)