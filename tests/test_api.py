from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_forecast_known_zone_returns_a_sane_prediction():
    resp = client.get("/forecast/106")
    assert resp.status_code == 200
    body = resp.json()
    assert body["zone"] == 106
    assert body["predicted_trips_next_hour"] >= 0


def test_forecast_invalid_zone_returns_404():
    resp = client.get("/forecast/999999")
    assert resp.status_code == 404


def test_experiment_readout_endpoints_return_the_documented_numbers():
    interference = client.get("/experiments/interference").json()
    assert interference["true_effect_min"] == -1.52
    assert interference["naive_bias_pct"] == -103.4

    cuped = client.get("/experiments/cuped").json()
    assert cuped["variance_reduction_pct"] == 26.3

    decision = client.get("/experiments/decision-layer").json()
    assert decision["optimizer_trips_per_hour"] == 27.1
