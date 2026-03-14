# C4 Container Diagram — Notification Service

**Nível**: Container (C4 Nível 2)  
**Serviço**: `notification-service`  
**Atualizado**: 2026-03-13

---

```mermaid
C4Container
    title Container Diagram — Notification Service

    Person(user, "Usuário", "Recebe e-mails de notificação sobre seus jobs")

    System_Ext(workerService, "Worker Service", "Processa vídeos e publica eventos de erro/sucesso")
    System_Ext(smtpProvider, "SMTP Provider", "Servidor de e-mail externo (porta 587, STARTTLS)")

    Container_Boundary(notifBoundary, "notification-service") {
        Container(consumer, "Consumer Loop", "Python 3.11, aio-pika", "Consome mensagens da fila 'notifications' via AMQP; gerencia ACK/NACK e retries com backoff")
        Container(notifService, "Notification Service", "Python 3.11", "Orquestra deduplicação, renderização de template e envio de e-mail")
        Container(templateRenderer, "Template Renderer", "Jinja2", "Renderiza templates HTML (DONE.html.j2 / ERROR.html.j2) sem expor detalhes técnicos")
        Container(emailSender, "Email Sender", "aiosmtplib", "Envia e-mail via SMTP com STARTTLS obrigatório")
        Container(metrics, "Metrics Server", "prometheus-client", "Expõe /metrics na porta 8002: notifications_sent_total, notifications_deduplicated_total")
    }

    ContainerDb(redis, "Redis", "Redis 7", "Deduplicação via chave 'notif:sent:{job_id}' (SET NX EX, TTL 24h)")
    ContainerQueue(rabbitmq, "RabbitMQ", "RabbitMQ 3", "Fila 'notifications' (durable); mensagens persistidas em disco")

    Rel(workerService, rabbitmq, "Publica evento de job finalizado", "AMQP")
    Rel(consumer, rabbitmq, "Consome fila 'notifications'", "AMQP")
    Rel(consumer, notifService, "Delega processamento da mensagem", "In-process")
    Rel(notifService, redis, "Verifica e grava chave de deduplicação", "Redis protocol")
    Rel(notifService, templateRenderer, "Solicita renderização do template", "In-process")
    Rel(notifService, emailSender, "Delega envio do e-mail renderizado", "In-process")
    Rel(emailSender, smtpProvider, "Envia e-mail", "SMTP / STARTTLS")
    Rel(smtpProvider, user, "Entrega e-mail", "E-mail")
```

---

## Elementos

| Elemento | Tipo | Tecnologia | Responsabilidade |
|----------|------|-----------|-----------------|
| Consumer Loop | Container | Python + aio-pika | Consume AMQP, gerencia ACK/NACK, backoff de reconexão |
| Notification Service | Container | Python | Orquestra fluxo: dedup → template → envio |
| Template Renderer | Container | Jinja2 | HTML sem stack traces / dados internos |
| Email Sender | Container | aiosmtplib | SMTP async com STARTTLS |
| Metrics Server | Container | prometheus-client | `/metrics` porta 8002 |
| Redis | ContainerDb | Redis 7 | Deduplicação idempotente (SET NX EX) |
| RabbitMQ | ContainerQueue | RabbitMQ 3 | Fila `notifications` durable |

## Decisões de design

- Sem banco de dados relacional próprio — `user_email` vem na mensagem (responsabilidade do Worker)
- Deduplicação Redis garante idempotência em ambiente multi-réplica
- Consumer usa `basic_nack(requeue=True)` para falhas transitórias e `basic_nack(requeue=False)` após `MAX_NOTIFICATION_RETRIES`
