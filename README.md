# notification-service

Serviço responsável por consumir a fila `notifications` do RabbitMQ, deduplicar notificações via Redis e enviar e-mails formatados com templates HTML (Jinja2) via SMTP.

## Visão Geral

| Item | Valor |
|---|---|
| Linguagem | Python 3.11 |
| Fila consumida | `notifications` (RabbitMQ) |
| Deduplicação | Redis — chave `notif:sent:{job_id}`, TTL 24 h |
| E-mail | aiosmtplib, STARTTLS, templates Jinja2 |
| Métricas | Prometheus (`/metrics` na porta 8002) |
| Cobertura mínima | 90 % |

## Variáveis de Ambiente

Copie `.env.example` para `.env` e ajuste os valores.

| Variável | Padrão | Descrição |
|---|---|---|
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | URL de conexão com o broker |
| `REDIS_URL` | `redis://localhost:6379/0` | URL do Redis para deduplicação |
| `SMTP_HOST` | `localhost` | Host SMTP |
| `SMTP_PORT` | `587` | Porta SMTP (STARTTLS) |
| `SMTP_USER` | — | Usuário SMTP (opcional) |
| `SMTP_PASSWORD` | — | Senha SMTP (opcional) |
| `EMAIL_FROM` | `no-reply@example.com` | Endereço de envio |
| `MAX_NOTIFICATION_RETRIES` | `3` | Tentativas antes de dead-letter |
| `NOTIFICATION_DEDUP_TTL_SECONDS` | `86400` | TTL da chave de deduplicação (segundos) |
| `LOG_LEVEL` | `INFO` | Nível de log (DEBUG, INFO, WARNING, ERROR) |
| `METRICS_PORT` | `8002` | Porta do servidor Prometheus |

## Execução local

```bash
# Instalar dependências
pip install -r requirements.txt

# Copiar configurações
cp .env.example .env

# Iniciar
python -m src.main
```

## Testes

```bash
# Rodar todos os testes unitários e de contrato (sem integrações)
make test

# Com relatório de cobertura HTML
make coverage
```

## Linting

```bash
make lint    # ruff + black (check)
make format  # black (auto-format)
```

## Docker

```bash
docker build -t notification-service .
docker run --env-file .env notification-service
```

## Dependências de infra

- **RabbitMQ** — fila `notifications` publicada pelo `worker-service`
- **Redis** — deduplicação de notificações
- **SMTP relay** — para envio de e-mails

## Fluxo de processamento

```
RabbitMQ (notifications)
  └─ base_consumer.py
       ├─ Deserializar JSON: job_id, user_email, status, error_message
       ├─ notification_service.send_notification()
       │    ├─ Redis has_dedup_key(job_id)?  → ack (skip)
       │    ├─ render_template(status) → HTML
       │    ├─ aiosmtplib.send(...) via STARTTLS
       │    └─ Redis set_dedup_key(job_id)
       └─ ack / nack (retry até MAX_NOTIFICATION_RETRIES)
```

## Arquitetura

Diagramas Mermaid versionados junto ao serviço:

- [C4 Container Diagram](docs/architecture/c4-container.md) — visão estrutural dos containers e dependências externas
- [Sequence Diagrams](docs/architecture/sequence.md) — happy path + erros críticos (deduplicação, retry esgotado)
