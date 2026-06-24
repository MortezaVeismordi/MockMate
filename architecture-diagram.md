# Architecture Diagram

### 1. System Overview
MockMate is an AI-powered interview simulator that conducts real-time technical interviews via WebSocket. It uses Django as the backend framework, Django Channels for WebSocket handling, Celery for asynchronous task processing, PostgreSQL for persistent storage, Redis as a message broker and channel layer, and Nginx as a reverse proxy. The system supports multiple LLM providers (OpenAI, Anthropic, OpenRouter) through an abstraction layer, enabling pluggable AI backends. Authentication is OTP-based via phone, with JWT for session management. The platform includes a question bank that can be populated from GitHub repositories, and it generates AI-driven evaluations and final reports after each interview session.

### 2. Architecture Diagram
```mermaid
graph TD
    %% External Clients
    subgraph Clients
        Browser[Web Browser] -->|HTTPS/WSS| Nginx
        Mobile[Mobile App] -->|HTTPS/WSS| Nginx
    end

    %% Reverse Proxy
    Nginx[Nginx] -->|HTTP/WebSocket| Daphne[Daphne ASGI Server]

    %% Django ASGI Application
    Daphne -->|Routes| Django[Django Application]
    Django -->|HTTP Views| Users[Users App]
    Django -->|HTTP Views| Questions[Questions App]
    Django -->|HTTP Views| Interviews[Interviews App (REST)]
    Django -->|WebSocket Consumers| WS_Consumer[Interviews WebSocket Consumer]

    %% Channel Layer (Redis)
    WS_Consumer -->|Channel Layer| Redis[(Redis)]
    Redis -->|Channel Layer| WS_Consumer

    %% Database
    Django -->|ORM| Postgres[(PostgreSQL)]

    %% Celery Task Queue
    Django -->|Celery Calls| Redis
    Redis -->|Broker/Backend| Celery[Celery Worker]
    Redis -->|Broker/Backend| CeleryBeat[Celery Beat]
    Celery -->|Tasks| LLM_Task[LLM Evaluation Task]
    Celery -->|Tasks| Report_Task[Report Generation Task]
    Celery -->|Tasks| Ingestion_Task[Question Ingestion Task]
    Celery -->|Tasks| Notification_Task[Notification Task (SMS/Email)]

    %% LLM Abstraction Layer
    LLM_Task -->|Calls| LLM_Abstraction[Core LLM Abstraction]
    LLM_Abstraction -->|HTTP API| OpenAI[OpenAI API]
    LLM_Abstraction -->|HTTP API| Anthropic[Anthropic API]
    LLM_Abstraction -->|HTTP API| OpenRouter[OpenRouter API]

    %% Notification Providers
    Notification_Task -->|SMS| Twilio[Twilio SMS]
    Notification_Task -->|Email| SES[Amazon SES / SMTP]

    %% External Services
    style OpenAI fill:#f9f,stroke:#333,stroke-width:1px
    style Anthropic fill:#f9f,stroke:#333,stroke-width:1px
    style OpenRouter fill:#f9f,stroke:#333,stroke-width:1px
    style Twilio fill:#ff9,stroke:#333,stroke-width:1px
    style SES fill:#ff9,stroke:#333,stroke-width:1px

    %% Monitoring
    Flower[Flower] -->|Monitors| Redis
    style Flower fill:#cfc,stroke:#333,stroke-width:1px

    %% Styling
    classDef client fill:#bbf,stroke:#333,stroke-width:1px;
    classDef proxy fill:#bfb,stroke:#333,stroke-width:1px;
    classDef django fill:#cfc,stroke:#333,stroke-width:1px;
    classDef db fill:#fcc,stroke:#333,stroke-width:1px;
    classDef cache fill:#cfc,stroke:#333,stroke-width:1px;
    classDef worker fill:#fcb,stroke:#333,stroke-width:1px;
    classDef external fill:#f99,stroke:#333,stroke-width:1px;
    class Browser,Mobile client;
    class Nginx proxy;
    class Daphne,Django,Users,Questions,Interviews,WS_Consumer django;
    class Postgres db;
    class Redis cache;
    class Celery,CeleryBeat worker;
    class LLM_Abstraction,LLM_Task,Report_Task,Ingestion_Task,Notification_Task worker;
    class OpenAI,Anthropic,OpenRouter,Twilio,SES external;
    class Flower monitoring;
```

### 3. Components Breakdown

| Component | Responsibility |
|-----------|----------------|
| **Web Browser / Mobile App** | Client UI that interacts via REST API and WebSocket for interview sessions. |
| **Nginx** | Reverse proxy terminating TLS, forwarding HTTP/WebSocket to Daphne, serving static/media files. |
| **Daphne ASGI Server** | ASGI server that handles both HTTP and WebSocket requests, interfacing with Django. |
| **Django Application** | Core web framework containing all business logic: REST API views, WebSocket consumers, ORM models, authentication, etc. |
| **Users App** | Handles OTP-based phone authentication, JWT token issuance/refresh, user profiles, and account management. |
| **Questions App** | Manages question bank, categorization, difficulty levels, and provides ingestion pipelines from GitHub repositories. |
| **Interviews App** | Manages interview sessions (creation, state), WebSocket consumer for real-time interview flow, answer storage, and triggers async evaluation/report generation. |
| **Core LLM Abstraction** | Pluggable layer that abstracts LLM provider APIs (OpenAI, Anthropic, OpenRouter) allowing runtime switching via configuration. |
| **Celery Worker** | Executes asynchronous tasks such as LLM answer evaluation, report generation, question ingestion, and notification sending. |
| **Celery Beat** | Scheduler for periodic tasks (e.g., scheduled question ingestions). |
| **Redis** | Used as: <br>• Message broker for Celery <br>• Result backend for Celery <br>• Channel layer for Django Channels (WebSocket communication) <br>• Optional caching layer. |
| **PostgreSQL** | Primary relational database storing users, questions, interview sessions, answers, reports, etc. |
| **Flower** | Web-based monitoring tool for Celery clusters. |
| **External LLM Providers** | Third‑party AI services (OpenAI GPT‑4, Anthropic Claude, OpenRouter models) used to generate questions, evaluate answers, and produce feedback. |
| **Notification Providers (SMS/Email)** | Services like Twilio (SMS) and Amazon SES/SMTP (email) used to deliver OTP codes and optional alerts. |

### 4. Data Flow

1. **User Onboarding**  
   - Client sends phone number to `/api/v1/auth/send-otp/` (Users app).  
   - Users app triggers a Celery task (`notification_task`) to send OTP via Twilio/SMS (or email).  
   - User receives OTP and submits it to `/api/v1/auth/verify-otp/`.  
   - On success, Users app issues JWT access and refresh tokens (stored in Redis blacklist on logout).  

2. **Creating an Interview Session**  
   - Authenticated client calls `POST /api/v1/interviews/` with session parameters (target position, seniority, etc.).  
   - Interviews app creates a session record in PostgreSQL, assigns a UUID, and returns a WebSocket URL: `/ws/interviews/<uuid>/?token=<access_token>`.  

3. **WebSocket Connection Establishment**  
   - Browser opens a WebSocket to the URL, passing the JWT as a query parameter.  
   - `Interviews WebSocket Consumer` authenticates the token, retrieves the session, and sends a `greeting` event.  

4. **Question‑Answer Loop**  
   - Client sends `{type: "next_question"}` to request the first question.  
   - Consumer selects a question from the Questions app (filtered by session seniority/focus) stored in PostgreSQL.  
   - Consumer sends a `question` event with the question text and metadata.  
   - Client submits an answer via `{type: "answer", payload: <answer_text>}`.  
   - Consumer persists the answer (Answer model) and publishes a Celery task (`llm_evaluation_task`) to evaluate the answer.  

5. **Answer Evaluation (Async)**  
   - Celery worker receives the task, invokes the Core LLM abstraction.  
   - LLM abstraction calls the configured external LLM API (e.g., OpenAI) with a prompt containing the question and answer.  
   - LLM returns a JSON evaluation (score, feedback, strengths/weaknesses).  
   - Result is stored in the Answer model and sent back to the client via a WebSocket `evaluation` event.  

6. **Loop Continuation**  
   - Steps 4‑5 repeat until the session’s `total_questions` limit is reached.  

7. **Report Generation**  
   - After the final answer, the consumer triggers a Celery task (`generate_report_task`).  
   - Task aggregates all answers and evaluations, computes overall score, and creates a Report record in PostgreSQL.  
   - Upon completion, the consumer sends a `report_ready` event to the client.  

8. **Report Retrieval**  
   - Client can fetch the final report via `GET /api/v1/interviews/<uuid>/report/` (Interviews app REST endpoint).  

9. **Session Termination**  
   - Either party can close the WebSocket; the consumer updates the session state to `completed`.  

### 5. Deployment View

- **Development** – Single‑node Docker Compose (as seen in `docker-compose.yml`) with separate containers for:  
  - `db` (PostgreSQL 15)  
  - `redis` (Redis 7)  
  - `web` (Django + Daphne, built from `docker/django/Dockerfile`)  
  - `celery` (Celery worker)  
  - `flower` (Celery monitoring)  
  - `nginx` (Reverse proxy)  
  - Volumes for persistent data (PostgreSQL, Redis, static/media).  

- **Production** – Similar compose file (`docker-compose.prod.yml`) or Kubernetes deployment with:  
  - Horizontal scaling of `web` (Daphne) replicas behind a load‑balancer/Nginx ingress.  
  - Multiple `celery` worker pools (e.g., default, high‑priority for LLM eval).  
  - Managed PostgreSQL (e.g., Amazon RDS, Cloud SQL) and managed Redis (e.g., AWS Elasticache, Redis Cloud).  
  - Separate services for monitoring (Prometheus + Grafana) and logging (ELK stack).  
  - Environment‑specific secrets managed via Docker secrets, Kubernetes secrets, or a vault.  
  - SSL termination at the ingress/Nginx level.  
  - Health checks and readiness probes for all services.  

- **Scalability & Fault Tolerance**  
  - Stateless Django/Daphne instances allow easy scaling.  
  - Redis provides pub/sub for WebSocket broadcasting and is a single point of failure; in production, use Redis Cluster or a managed HA offering.  
  - PostgreSQL can be replicated with read‑replicas for scaling read‑heavy workloads (e.g., question listing).  
  - Celery workers can be autoscale based on queue depth.  
  - LLM API calls are external; rate‑limiting and retry logic are handled in the abstraction layer.  
  - Notification tasks are idempotent and can be retried; failure to send OTP does not block core interview flow (user can request a new OTP).  

- **Caching Strategy**  
  - Redis caches frequently accessed data such as question lists, user profiles, and session metadata to reduce DB load.  
  - Django’s per‑site cache framework can be configured to use Redis.  
  - Static/media files are served directly by Nginx from mounted volumes, optionally backed by a CDN in production.  

- **Real‑Time Communication**  
  - Full‑duplex WebSocket via Django Channels enables low‑latency interview flow.  
  - Heartbeats/keepalives are managed by the JavaScript client; the server can detect disconnects and clean up resources.  

This architecture reflects a production‑ready, scalable, and fault‑tolerant system that leverages asynchronous processing, real‑time WebSocket communication, and pluggable AI providers to deliver a realistic interview simulation experience.