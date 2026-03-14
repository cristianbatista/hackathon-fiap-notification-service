import prometheus_client

from src.core.config import settings

notifications_sent_total = prometheus_client.Counter(
    "notifications_sent_total",
    "Total notifications sent",
    ["status"],
)

notifications_deduplicated_total = prometheus_client.Counter(
    "notifications_deduplicated_total",
    "Total notifications skipped due to deduplication",
)


def start_metrics_server() -> None:
    prometheus_client.start_http_server(settings.metrics_port)
