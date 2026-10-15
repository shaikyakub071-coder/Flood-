"""
test_app.py - Integration and end-to-end tests for app.py with SQLite fallback.

Run with:
    pytest -v test_app.py
"""

import os
import tempfile
import pytest

# Ensure we use a clean temporary SQLite database for tests
temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
temp_db_path = temp_db.name
temp_db.close()
os.environ["SQLITE_DB"] = temp_db_path
os.environ.pop("DATABASE_URL", None)
os.environ["ADMIN_PASSWORD"] = "testpass"

from app import app, get_connection, initialize_database, _db_ready


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    initialize_database()
    yield
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    with app.test_client() as client:
        yield client


class TestAppEndpoints:
    def test_home_page_loads(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert b"Nandyal Bus Stand" in res.data
        assert b"Evacuation Center" in res.data

    def test_home_page_route_calculation_auto(self, client):
        res = client.post("/", data={
            "source": "Kundu River Bank",
            "destination": "AUTO",
            "people": "5"
        })
        assert res.status_code == 200
        assert b"km" in res.data
        assert b"Safest Route" in res.data or b"route" in res.data.lower()

    def test_home_page_route_calculation_manual(self, client):
        res = client.post("/", data={
            "source": "Nandyal Bus Stand",
            "destination": "Government Hospital",
            "people": "2"
        })
        assert res.status_code == 200
        assert b"2.0" in res.data or b"2" in res.data

    def test_api_status_endpoint(self, client):
        res = client.get("/api/status")
        assert res.status_code == 200
        data = res.get_json()
        assert data["ok"] is True
        assert "version" in data
        assert len(data["version"]) == 32  # md5 hex

    def test_evacuate_all_page(self, client):
        res = client.get("/evacuate-all")
        assert res.status_code == 200
        assert b"Evacuate All" in res.data or b"Evacuation Plan" in res.data or b"Total" in res.data

    def test_admin_requires_login(self, client):
        res = client.get("/admin")
        assert res.status_code == 302
        assert "/login" in res.headers["Location"]

    def test_login_flow(self, client):
        # Wrong password
        res = client.post("/login", data={"password": "wrongpassword"})
        assert res.status_code == 200
        assert b"Wrong password" in res.data

        # Correct password
        res = client.post("/login", data={"password": "testpass"}, follow_redirects=True)
        assert res.status_code == 200
        assert b"Admin" in res.data

    def test_admin_update_road(self, client):
        # Login first
        client.post("/login", data={"password": "testpass"})
        
        # Update a road
        res = client.post("/update_road", data={
            "road_name": "Bus Stand - Government Hospital",
            "flood_level": "high",
            "status": "open"
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"Updated: Bus Stand - Government Hospital" in res.data

    def test_admin_update_population(self, client):
        client.post("/login", data={"password": "testpass"})
        
        res = client.post("/update_population", data={
            "zone": "Kundu River Bank",
            "people": "850",
            "vulnerable": "120"
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"850 people" in res.data

    def test_reset_shelters(self, client):
        client.post("/login", data={"password": "testpass"})
        
        res = client.post("/reset_shelters", follow_redirects=True)
        assert res.status_code == 200
        assert b"All shelters emptied" in res.data

    def test_confirm_single_evacuation(self, client):
        res = client.post("/confirm_evacuation", data={
            "shelter": "Community Hall Shelter",
            "people": "10"
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"10 people assigned to Community Hall Shelter" in res.data

    def test_api_route_auto(self, client):
        res = client.get("/api/route?source=Nandyal+Bus+Stand&destination=AUTO&people=3")
        assert res.status_code == 200
        data = res.get_json()
        assert data["ok"] is True
        assert data["source"] == "Nandyal Bus Stand"
        assert "route" in data
        assert "distance_km" in data
        assert "eta" in data
        assert "car" in data["eta"]["formatted"]
        assert "walk" in data["eta"]["formatted"]
        assert "truck" in data["eta"]["formatted"]

    def test_api_route_post_json(self, client):
        res = client.post("/api/route", json={
            "source": "Government Hospital",
            "destination": "Evacuation Center",
            "people": 5
        })
        assert res.status_code == 200
        data = res.get_json()
        assert data["ok"] is True
        assert data["destination"] == "Evacuation Center"
        assert len(data["route"]) >= 2

    def test_api_route_missing_source(self, client):
        res = client.get("/api/route")
        assert res.status_code == 400
        data = res.get_json()
        assert data["ok"] is False

    def test_api_simulate_surge(self, client):
        res = client.get("/api/simulate?surge=1.0")
        assert res.status_code == 200
        data = res.get_json()
        assert data["ok"] is True
        assert data["surge_meters"] == 1.0
        assert len(data["roads"]) > 0

