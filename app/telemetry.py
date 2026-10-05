"""OpenTelemetry setup for the order tracker.

Exports traces, metrics, and logs to the console so they show up in
``docker compose logs app``. This is intentionally minimal: it wires up
console exporters for all three signals and hands back a tracer, a meter,
and a logger for the app to instrument endpoints with.
"""

import atexit
import logging

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogRecordExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

SERVICE_NAME = "order-tracker"
METRIC_EXPORT_INTERVAL_MILLIS = 5000

resource = Resource.create({"service.name": SERVICE_NAME})

# Traces: export each finished span to the console as soon as it ends.
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer("order_tracker")

# Metrics: export on a short interval so counts show up quickly in the logs.
metric_reader = PeriodicExportingMetricReader(
    ConsoleMetricExporter(), export_interval_millis=METRIC_EXPORT_INTERVAL_MILLIS
)
meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter("order_tracker")

order_lookup_requests = meter.create_counter(
    "order_lookup_requests",
    description="Requests to GET /api/orders/{order_id}",
    unit="1",
)

# Logs: route Python logging through OTel so log records also hit the console.
logger_provider = LoggerProvider(resource=resource)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(ConsoleLogRecordExporter()))
set_logger_provider(logger_provider)

otel_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
logger = logging.getLogger("order_tracker")
logger.setLevel(logging.INFO)
logger.addHandler(otel_handler)
logger.propagate = False

# Stop the background export threads at interpreter exit so they don't try to
# write to streams the process (or a test runner) has already torn down.
atexit.register(tracer_provider.shutdown)
atexit.register(meter_provider.shutdown)
atexit.register(logger_provider.shutdown)
