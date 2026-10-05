import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app import main, telemetry


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "orders.db")
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture(scope="session", autouse=True)
def _stop_telemetry_background_threads():
    # The metric/log exporters run on periodic background threads. Stop them
    # before pytest tears down its own output capture, so they don't try to
    # write to a stream that is already closed.
    yield
    telemetry.tracer_provider.shutdown()
    telemetry.meter_provider.shutdown()
    telemetry.logger_provider.shutdown()


def test_health_and_seeded_orders(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    orders = client.get("/api/orders").json()
    assert len(orders) == 3
    assert {order["priority"] for order in orders} == {"standard", "express"}


def test_create_and_update_order(client):
    response = client.post(
        "/api/orders",
        json={"customer": "Taylor", "item": "Mug", "priority": "standard"},
    )
    assert response.status_code == 201
    order_id = response.json()["id"]
    assert client.get(f"/api/orders/{order_id}").json()["status"] == "received"
    updated = client.patch(f"/api/orders/{order_id}", json={"status": "shipped"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "shipped"


def test_missing_order(client):
    assert client.get("/api/orders/missing").status_code == 404


def test_seeded_express_order_lookup(client):
    # express-1002 is seeded on the last day of the previous month.
    response = client.get("/api/orders/express-1002")
    assert response.status_code == 200
    assert "estimated_delivery" in response.json()


@pytest.mark.parametrize(
    ("created_at", "expected"),
    [
        ("2026-09-30T12:00:00+00:00", "2026-10-02"),
        ("2026-01-31T12:00:00+00:00", "2026-02-02"),
        ("2026-12-31T12:00:00+00:00", "2027-01-02"),
        ("2026-10-05T12:00:00+00:00", "2026-10-07"),
    ],
)
def test_express_estimated_delivery_crosses_month_end(created_at, expected):
    order = main.order_detail(
        {"id": "x", "customer": "c", "item": "i", "priority": "express",
         "status": "received", "created_at": created_at}
    )
    assert order["estimated_delivery"] == expected


def test_order_lookup_emits_telemetry(client, caplog, monkeypatch):
    # Traces: attach an in-memory exporter to the real tracer provider so we can
    # inspect finished spans without depending on console output/capturing.
    span_exporter = InMemorySpanExporter()
    telemetry.tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))

    # Metrics: record what the request counter is called with.
    metric_calls = []
    original_add = telemetry.order_lookup_requests.add
    monkeypatch.setattr(
        telemetry.order_lookup_requests,
        "add",
        lambda amount, attributes=None: (
            metric_calls.append(attributes or {}),
            original_add(amount, attributes),
        ),
    )

    with caplog.at_level("INFO", logger="order_tracker"):
        client.get("/api/orders/standard-1001")
        client.get("/api/orders/missing")

    spans = {span.attributes["order.id"]: span for span in span_exporter.get_finished_spans()}
    assert spans["standard-1001"].attributes["http.route"] == "/api/orders/{order_id}"
    assert spans["standard-1001"].attributes["http.status_code"] == 200
    assert spans["missing"].attributes["http.route"] == "/api/orders/{order_id}"
    assert spans["missing"].attributes["http.status_code"] == 404

    assert {"http.route": "/api/orders/{order_id}", "http.status_code": 200} in metric_calls
    assert {"http.route": "/api/orders/{order_id}", "http.status_code": 404} in metric_calls

    assert "order lookup for standard-1001 -> 200" in caplog.text
    assert "order lookup for missing -> 404" in caplog.text
