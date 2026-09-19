# PayE — Multi-Processor Payment Orchestration Platform

PayE is a backend payment orchestration project built with Python and FastAPI.

It simulates a payment platform that can route a payment across multiple payment
processors and asynchronously notify a merchant about the final payment result.

The project demonstrates:

- Multi-processor payment routing
- Processor eligibility and weighted scoring
- Processor failover for technical failures
- Payment idempotency
- Card-vault separation
- MySQL persistence
- Transactional Outbox Pattern
- Kafka-based asynchronous events
- Merchant webhooks
- Docker Compose based local deployment

> **Note:** This is a learning/portfolio project. The payment processors and
> merchant server are simulated. Do not use it to process real payment data.

---

## Architecture

```text
                         Client
                           |
                           v
                    +--------------+
                    | Payment API  |
                    |   FastAPI    |
                    +------+-------+
                           |
             +-------------+-------------+
             |                           |
             v                           v
        +---------+                +------------+
        |  MySQL  |                | Card Vault |
        +----+----+                +------------+
             |
             v
       +-------------+
       | outbox_     |
       | events      |
       +------+------+
              |
              | polling
              v
       +---------------+
       | Outbox        |
       | Publisher     |
       +-------+-------+
               |
               v
          +---------+
          |  Kafka  |
          |payment- |
          | events  |
          +----+----+
               |
               v
       +---------------+
       | Webhook       |
       | Consumer      |
       +-------+-------+
               |
               | HTTP
               v
       +---------------+
       | Merchant      |
       | Server        |
       +---------------+


        Payment Orchestrator
          /       |       \
         v        v        v
   Processor A  Processor B  Processor C
```

---

## Technology Stack

- Python 3.11
- FastAPI
- SQLAlchemy
- MySQL
- Kafka
- aiokafka
- HTTPX
- JWT
- Docker
- Docker Compose

---

# Running the Application After Cloning

## 1. Prerequisites

Install the following:

- Git
- Docker Desktop
- MySQL 8.x (or a compatible MySQL installation)

Verify Docker:

```bash
docker --version
docker compose version
```

Make sure Docker Desktop is running before starting the application.

---

## 2. Clone the Repository

Clone the `merchant_webhook` branch:

```bash
git clone -b merchant_webhook https://github.com/sapta94/payment-workflow.git
cd payment-workflow
```

If you have already cloned the repository:

```bash
git checkout merchant_webhook
git pull origin merchant_webhook
```

---

## 3. Create the MySQL Databases

PayE currently uses two MySQL databases:

- `payment_workflow`
- `payment_vault`

Create them if they do not already exist:

```sql
CREATE DATABASE payment_workflow;
CREATE DATABASE payment_vault;
```

The application expects the required tables to exist in these databases.

If you are setting up a fresh environment, use the SQL/table definitions
provided with the project or create the schema from the project's current
database models.

---

## 4. Configure Environment Variables

Create a `.env` file in the project root.

If the repository contains `.env.example`, start from it:

```bash
cp .env.example .env
```

Then update the values for your local MySQL installation.

For Docker, the application containers connect to MySQL running on the host
through `host.docker.internal`.

A typical local configuration looks like:

```env
DATABASE_URL=mysql+asyncmy://root:YOUR_PASSWORD@localhost:3306/payment_workflow?charset=utf8mb4

VAULT_DATABASE_URL=mysql+asyncmy://root:YOUR_PASSWORD@localhost:3306/payment_vault?charset=utf8mb4

DATABASE_URL_DOCKER=mysql+asyncmy://root:YOUR_PASSWORD@host.docker.internal:3306/payment_workflow?charset=utf8mb4

VAULT_DATABASE_URL_DOCKER=mysql+asyncmy://root:YOUR_PASSWORD@host.docker.internal:3306/payment_vault?charset=utf8mb4

KAFKA_BOOTSTRAP_SERVERS=kafka:29092

JWT_SECRET_KEY=change-this-for-local-development
JWT_ALGORITHM=HS256

CARD_VAULT_ENCRYPTION_KEY=change-this-for-local-development
MERCHANT_VAULT_ENCRYPTION_KEY=change-this-for-local-development
```

Use your actual MySQL password and the encryption/JWT values required by your
current configuration.

**Do not commit `.env` or real secrets to GitHub.**

---

## 5. Make Sure the Merchant Webhook URL Is Configured

The demo merchant server runs inside Docker.

For a merchant such as `merchant_id = 1001`, set its webhook URL to:

```sql
UPDATE merchant_list
SET webhook_url = 'http://merchant-server:9000/webhook'
WHERE merchant_id = 1001;
```

The hostname `merchant-server` is the Docker Compose service name, so it is
reachable from the webhook consumer inside the Docker network.

---

## 6. Start the Application

From the project root:

```bash
docker compose up --build
```

Or run it in the background:

```bash
docker compose up --build -d
```

The first build can take some time because the application and processor
containers install their dependencies.

---

## 7. Check the Services

Run:

```bash
docker compose ps
```

The main services should be running:

```text
payment-api
processor_a
processor_b
processor_c
merchant-server
kafka
outbox-publisher
webhook-consumer
```

If a service is restarting, check its logs:

```bash
docker compose logs <service-name>
```

Examples:

```bash
docker compose logs payment-api
docker compose logs kafka
docker compose logs outbox-publisher
docker compose logs webhook-consumer
```

To follow logs live:

```bash
docker compose logs -f outbox-publisher
```

---

# Local Service Endpoints

| Service | URL / Port | Purpose |
|---|---|---|
| Payment API | `http://localhost:8000` | Main payment API |
| Swagger UI | `http://localhost:8000/docs` | API documentation |
| Processor A | `http://localhost:8001` | Mock payment processor |
| Processor B | `http://localhost:8002` | Mock payment processor |
| Processor C | `http://localhost:8003` | Mock payment processor |
| Merchant Server | `http://localhost:9000` | Demo merchant webhook |
| Kafka | `localhost:9092` | Host-side Kafka listener |

Inside Docker, application services communicate with Kafka using:

```text
kafka:29092
```

---

# Payment Flow

A successful payment follows this flow:

```text
Client
  |
  v
Payment API
  |
  +--> Payment Orchestrator
  |        |
  |        +--> Processor A
  |        +--> Processor B
  |        +--> Processor C
  |
  v
MySQL
  |
  +--> payment
  |
  +--> outbox_events
          |
          | polling
          v
     Outbox Publisher
          |
          v
        Kafka
          |
          v
    Webhook Consumer
          |
          | HTTP POST
          v
    Merchant Server
```

The payment result and the corresponding outbox event are written in the same
database transaction.

Kafka publication happens asynchronously after the payment transaction has
been committed.

---

# Transactional Outbox

PayE uses a polling-based Transactional Outbox Pattern.

It intentionally does **not** use Debezium or CDC.

The flow is:

```text
Payment transaction
       |
       +--> Update payment
       |
       +--> Insert outbox event
       |
       +--> COMMIT
                |
                v
         Outbox Publisher
                |
                v
              Kafka
```

This keeps payment processing independent from Kafka availability.

The outbox publisher looks for events where:

```text
published_at IS NULL
```

and publishes them to the:

```text
payment-events
```

Kafka topic.

---

# Kafka Events

The Kafka topic used by the application is:

```text
payment-events
```

Events are distinguished using `event_type`.

Examples:

```text
payment.succeeded
payment.failed
```

A published event has a structure similar to:

```json
{
  "event_id": "uuid",
  "event_type": "payment.succeeded",
  "event_version": 1,
  "aggregate_type": "payment",
  "aggregate_id": 12345,
  "source": "payment-service",
  "occurred_at": "2026-01-01T10:00:00",
  "payload": {
    "payment_id": 12345,
    "merchant_id": 1001,
    "amount": "100.00",
    "currency": "USD",
    "status": "SUCCESS",
    "processor": "PROCESSOR_A",
    "transaction_id": "PA-12345"
  }
}
```

---

# Merchant Webhook

The webhook consumer reads events from Kafka and sends the final payment
status to the merchant.

Example request:

```http
POST /webhook
Content-Type: application/json
```

```json
{
  "event_id": "uuid",
  "payment_id": 12345,
  "merchant_id": 1001,
  "payment_status": "SUCCESS"
}
```

The demo merchant server keeps its own simple order state and uses
`event_id` to avoid processing the same event more than once.

Both successful and failed payments are valid payment outcomes.

A webhook delivery failure is different from a payment failure:

```text
Payment FAILED
    ≠
Webhook delivery FAILED
```

---

# Processor Routing

The payment orchestrator first filters processors based on eligibility and
then ranks eligible processors.

The current score is:

```text
Score =
    0.20 × capability
  + 0.15 × geography
  + 0.15 × currency
  + 0.30 × success_rate
  + 0.20 × reliability
```

`base_priority` is used as a deterministic tie-breaker.

Processor failover is intended for technical failures such as:

- Connection failures
- Processor unavailable
- Timeouts

A normal business decline is not treated as a technical failure and is not
automatically retried on another processor.

---

# Testing the Payment API

Open Swagger:

```text
http://localhost:8000/docs
```

or use the API directly with `curl`.

For example, the payment endpoint can be called with an idempotency key:

```bash
curl -X POST "http://localhost:8000/api/v1/make-payment" \
  -H "Content-Type: application/json" \
  -H "idempotency-key: demo-payment-001" \
  -d '{
    "merchant_id": 1001,
    "payment_method_id": 1,
    "amount": 100.00,
    "currency": "USD"
  }'
```

Use values that exist in your local database for the merchant and payment
method.

The exact request schema can always be checked in Swagger:

```text
http://localhost:8000/docs
```

---

# Verifying the Outbox Flow

After making a payment, check the outbox table:

```sql
SELECT
    id,
    event_id,
    event_type,
    aggregate_id,
    published_at
FROM outbox_events
ORDER BY id DESC;
```

A successfully published event should have a non-null:

```text
published_at
```

You can also watch the publisher:

```bash
docker compose logs -f outbox-publisher
```

and the webhook consumer:

```bash
docker compose logs -f webhook-consumer
```

The expected flow is:

```text
Payment created
      ↓
Payment processed
      ↓
Outbox event created
      ↓
Outbox publisher reads event
      ↓
Kafka
      ↓
Webhook consumer
      ↓
Merchant webhook
```

---

# Stopping the Application

To stop the containers:

```bash
docker compose down
```

To stop and remove the Kafka volume as well:

```bash
docker compose down -v
```

> Be careful with `-v` because it removes Docker-managed volumes such as the
> Kafka data volume.

---

# Rebuilding After Code Changes

If the application code has changed and the Dockerfile copies the source into
the image, rebuild the affected service:

```bash
docker compose build payment-api
docker compose up -d payment-api
```

For messaging changes:

```bash
docker compose build outbox-publisher webhook-consumer
docker compose up -d outbox-publisher webhook-consumer
```

Or rebuild everything:

```bash
docker compose up --build
```

---

# Project Structure

```text
payment-workflow/
│
├── app/
│   ├── api/
│   ├── core/
│   ├── database/
│   ├── messaging/
│   │   ├── kafka_producer.py
│   │   ├── outbox_publisher.py
│   │   ├── publisher_main.py
│   │   ├── webhook_consumer.py
│   │   └── consumer_main.py
│   └── orchestrator/
│
├── processor_servers/
│   ├── processor_a/
│   ├── processor_b/
│   └── processor_c/
│
├── merchant_server/
│   └── main.py
│
├── Dockerfile
├── Dockerfile.processor
├── docker-compose.yaml
├── pyproject.toml
├── .env.example
└── README.md
```

---

# Troubleshooting

## Kafka connection refused

If you see:

```text
Unable to connect to "kafka:29092"
```

Kafka may still be starting.

Check:

```bash
docker compose ps
docker compose logs kafka
```

Docker services should use:

```text
kafka:29092
```

not:

```text
localhost:9092
```

`localhost:9092` is the external listener intended for clients running on
the host machine.

---

## Outbox publisher keeps restarting

Check:

```bash
docker compose logs outbox-publisher
```

The Compose command should run:

```text
python -m app.messaging.publisher_main
```

because `publisher_main.py` creates the Kafka producer and starts the
`OutboxPublisher`.

---

## Webhook consumer keeps restarting

Check:

```bash
docker compose logs webhook-consumer
```

The Compose command should run:

```text
python -m app.messaging.consumer_main
```

---

# Important Security Note

This repository is a demonstration project.

Never put real:

- Card numbers
- CVV values
- Production database credentials
- JWT secrets
- Encryption keys
- Payment processor credentials

into `.env`, source code or Git history.

Use test data and local credentials only.
