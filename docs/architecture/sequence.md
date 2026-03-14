# Sequence Diagrams — Notification Service

**Serviço**: `notification-service`  
**Cobertura**: Happy path P1 + erros críticos  
**Atualizado**: 2026-03-13

---

## Fluxo 1 — Happy Path: E-mail enviado com sucesso

```mermaid
sequenceDiagram
    autonumber
    participant RabbitMQ as RabbitMQ<br/>(fila notifications)
    participant Consumer as Consumer Loop
    participant NotifService as Notification Service
    participant Redis as Redis
    participant Jinja2 as Template Renderer
    participant SMTP as SMTP Provider

    RabbitMQ->>Consumer: Entrega mensagem (job_id, user_email, status=ERROR)
    Consumer->>NotifService: send_notification(job_id, user_email, status)
    NotifService->>Redis: EXISTS notif:sent:{job_id}
    Redis-->>NotifService: False (primeira ocorrência)
    NotifService->>Jinja2: render_template("ERROR", {job_id})
    Jinja2-->>NotifService: HTML renderizado (sem detalhes técnicos)
    NotifService->>SMTP: aiosmtplib.send(to=user_email, html=...) [STARTTLS]
    SMTP-->>NotifService: 250 OK
    NotifService->>Redis: SET notif:sent:{job_id} 1 EX 86400 NX
    Redis-->>NotifService: OK
    NotifService-->>Consumer: sucesso
    Consumer->>RabbitMQ: basic_ack()
```

---

## Fluxo 2 — Deduplicação: Mensagem duplicada descartada

```mermaid
sequenceDiagram
    autonumber
    participant RabbitMQ as RabbitMQ<br/>(fila notifications)
    participant Consumer as Consumer Loop
    participant NotifService as Notification Service
    participant Redis as Redis

    RabbitMQ->>Consumer: Entrega mensagem duplicada (mesmo job_id)
    Consumer->>NotifService: send_notification(job_id, user_email, status)
    NotifService->>Redis: EXISTS notif:sent:{job_id}
    Redis-->>NotifService: True (já processado)
    NotifService-->>Consumer: descartado (sem envio de e-mail)
    Note over NotifService: incrementa notifications_deduplicated_total<br/>log: {event: "notification_deduplicated", job_id}
    Consumer->>RabbitMQ: basic_ack()
```

---

## Fluxo 3 — Falha SMTP com retries esgotados

```mermaid
sequenceDiagram
    autonumber
    participant RabbitMQ as RabbitMQ<br/>(fila notifications)
    participant Consumer as Consumer Loop
    participant NotifService as Notification Service
    participant Redis as Redis
    participant SMTP as SMTP Provider

    RabbitMQ->>Consumer: Entrega mensagem (job_id, user_email, status=ERROR)

    loop Até MAX_NOTIFICATION_RETRIES (padrão: 3)
        Consumer->>NotifService: send_notification(job_id, user_email, status)
        NotifService->>Redis: EXISTS notif:sent:{job_id}
        Redis-->>NotifService: False
        NotifService->>SMTP: aiosmtplib.send(...) [STARTTLS]
        SMTP-->>NotifService: Erro (connection refused / timeout)
        NotifService-->>Consumer: levanta EmailSendError
        Note over Consumer: incrementa retry counter<br/>log: {event: "notification_send_failed", attempt: N}
    end

    Note over Consumer: MAX_NOTIFICATION_RETRIES atingido
    Consumer->>RabbitMQ: basic_nack(requeue=False)
    Note over Consumer: log: {event: "notification_failed_permanently", job_id, attempts: MAX}
    Note over Consumer: incrementa notifications_sent_total{status="failure"}
```

---

## Resumo dos fluxos

| Fluxo | Trigger | Resultado final |
|-------|---------|----------------|
| Happy path | Mensagem nova + SMTP OK | E-mail enviado, `basic_ack` |
| Deduplicação | `job_id` já em Redis | Sem e-mail, `basic_ack` |
| Falha SMTP + retries esgotados | SMTP indisponível N vezes | `basic_nack(requeue=False)`, log permanente |
