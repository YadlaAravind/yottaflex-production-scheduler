from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200


def test_analytics_endpoint():
    response = client.get("/analytics")
    assert response.status_code == 200


def test_orders_endpoint():
    response = client.get("/orders")
    assert response.status_code == 200
    assert len(response.json()) == 500


def test_unscheduled_endpoint():
    response = client.get("/unscheduled?limit=2000")

    assert response.status_code == 200

    data = response.json()
    print("Unscheduled response:", data)

    assert isinstance(data, (list, dict))


def test_schedule_endpoint():
    response = client.get("/schedule?limit=5000")

    assert response.status_code == 200

    data = response.json()
    print("Schedule response:", data)

    assert isinstance(data, (list, dict))