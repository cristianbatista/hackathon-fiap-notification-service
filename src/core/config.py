from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    rabbitmq_url: str = Field(
        "amqp://guest:guest@localhost:5672/", alias="RABBITMQ_URL"
    )
    redis_url: str = Field("redis://localhost:6379/0", alias="REDIS_URL")
    smtp_host: str = Field("localhost", alias="SMTP_HOST")
    smtp_port: int = Field(587, alias="SMTP_PORT")
    smtp_user: str = Field("", alias="SMTP_USER")
    smtp_password: str = Field("", alias="SMTP_PASSWORD")
    smtp_start_tls: bool = Field(True, alias="SMTP_START_TLS")
    email_from: str = Field("no-reply@example.com", alias="EMAIL_FROM")
    max_notification_retries: int = Field(3, alias="MAX_NOTIFICATION_RETRIES")
    notification_dedup_ttl_seconds: int = Field(
        86400, alias="NOTIFICATION_DEDUP_TTL_SECONDS"
    )
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    metrics_port: int = Field(8002, alias="METRICS_PORT")

    model_config = {"env_file": ".env", "populate_by_name": True}


settings = Settings()
