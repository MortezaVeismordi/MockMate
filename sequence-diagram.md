    # Sequence Diagram

    ## 1. Overview
    This document captures the key runtime flows of MockMate using Mermaid sequence diagrams. The flows covered are:
    1. **User Authentication Flow** – OTP sending, verification, and JWT issuance.
    2. **WebSocket Interview Session Flow** – connection, interview lifecycle (start, question‑answer, evaluation, report generation).
    3. **Async Task Execution Flow** – how Celery tasks are triggered and executed for OTP delivery, answer evaluation, and report generation.
    4. **External API Calls** – interactions with LLM providers (OpenAI/Anthropic/OpenRouter) and notification providers (Twilio/SMS).

    Each diagram shows the participants, messages, and synchronous/asynchronous interactions that occur during a typical execution.

    ---

    ## 2. Sequence Diagrams

    ### 2.1 User Authentication Flow (OTP / Login / JWT)
    ```mermaid
    sequenceDiagram
        participant Client
        participant API as Users API (SendOTPView/VerifyOTPView)
        participant Service as OTPService
        participant ModelUser as User Model
        participant ModelOTP as OTPCode Model
        participant ModelNotif as Notification Model
        participant Celery as Celery Worker (send_otp_notification_task)
        participant NotifService as NotificationService
        participant Provider as SMS Provider (e.g., Twilio)
        participant JWT as JWT Issuance (SimpleJWT)

        %% Send OTP
        Client->>API: POST /api/v1/users/auth/send-otp/ {phone, purpose}
        API->>Service: send_otp(phone, purpose, ip)
        Service->>ModelUser: get_or_create by phone
        alt new user
            ModelUser-->>Service: user (created=true)
        else existing
            ModelUser-->>Service: user (created=false)
        end
        Service->>ModelOTP: create OTP record
        ModelOTP-->>Service: otp (with code, remaining_seconds)
        Service->>ModelNotif: create Notification (PENDING)
        ModelNotif-->>Service: notification
        Service->>Celery: transaction.on_commit -> send_otp_notification_task.delay(notification_id)
        Service-->>API: success (is_new_user, remaining_seconds)
        API-->>Client: 200 OK {message, data}

        %% Async OTP delivery
        Celery->>NotifService: send_notification(notification_id)
        NotifService->>Provider: send(recipient, body)
        Provider-->>NotifService: (success, provider_id, error)
        NotifService->>ModelNotif: update status (SENT/FAILED) + provider_id/error
        ModelNotif-->>NotifService: updated
        NotifService-->>Celery: done

        %% Verify OTP
        Client->>API: POST /api/v1/users/auth/verify-otp/ {phone, code, purpose}
        API->>Service: verify_otp(phone, code, purpose)
        Service->>ModelUser: get by phone
        ModelUser-->>Service: user
        Service->>ModelOTP: verify_otp(user, code, purpose)
        ModelOTP-->>Service: (success, message)
        alt success
            Service->>ModelUser: update is_active=true, is_phone_verified=true
            ModelUser-->>Service: updated
            Service->>JWT: generate access/refresh tokens (via serializer)
            JWT-->>Service: tokens
            Service-->>API: success {tokens, user data}
            API-->>Client: 200 OK {message, data with tokens}
        else failure
            Service-->>API: failure {message}
            API-->>Client: 400 Bad Request {message}
        end
    ```

    ### 2.2 WebSocket Interview Session Flow
    ```mermaid
    sequenceDiagram
        participant Client
        participant WS as InterviewConsumer (WebSocket)
        participant SessionSvc as InterviewConductService
        participant ModelSession as InterviewSession Model
        participant ModelQuestion as Question Model
        participant ModelSQ as SessionQuestion Model
        participant ModelAnswer as UserAnswer Model
        participant CeleryEval as Celery Worker (evaluate_answer_task)
        participant EvalSvc as EvaluationService
        participant LLMClient as LLM Client
        participant LLMProv as LLM Provider (OpenAI/Anthropic/...)
        participant CeleryReport as Celery Worker (generate_report_task)
        participant ReportSvc as ReportService

        %% Connection (assumes JWT already validated by middleware, user in scope)
        Client->>WS: WebSocket connect ws://.../ws/interviews/<uuid>/?token=<jwt>
        WS->>WS: authenticate (user from scope)
        WS->>ModelSession: get session by uuid & user
        ModelSession-->>WS: session
        WS->>WS: accept connection
        WS->>WS: group_add interview_<uuid>
        WS-->>Client: connected event (session status, etc.)

        %% Start Interview
        Client->>WS: {type: "start"}
        WS->>SessionSvc: start_interview(session)
        SessionSvc->>ModelSession: transition to INTRO
        SessionSvc->>SessionSvc: _build_system_prompt + _save_message (SYSTEM)
        SessionSvc->>SessionSvc: _build_greeting + _save_message (GREETING)
        SessionSvc-->>WS: greeting_msg
        WS-->>Client: greeting event (content, turn_number)

        %% Loop: request next question
        Client->>WS: {type: "next_question"}
        WS->>SessionSvc: ask_next_question(session)
        SessionSvc->>ModelSQ: get next pending question
        ModelSQ-->>SessionSvc: session_question (or null if none)
        alt questions remain
            SessionSvc->>ModelSQ: set status ACTIVE
            SessionSvc->>ModelSession: update current_index, status=QUESTIONING
            SessionSvc->>ModelQuestion: get question body
            ModelQuestion-->>SessionSvc: content
            SessionSvc->>SessionSvc: _save_message (QUESTION) with metadata
            SessionSvc-->>WS: question_msg (content, turn_number, etc.)
            WS-->>Client: question event
        else no questions left
            SessionSvc->>SessionSvc: wrap_up(session)
            SessionSvc-->>WS: wrap_up_msg
            WS-->>Client: wrap_up event
            %% Report generation triggered later (see async)
        end

        %% Submit Answer
        Client->>WS: {type: "submit_answer", answer_text: "..."}
        WS->>SessionSvc: submit_answer(session, answer_text, duration?)
        SessionSvc->>ModelAnswer: create UserAnswer (PENDING)
        ModelAnswer-->>SessionSvc: answer
        SessionSvc->>ModelSQ: set status ANSWERED
        SessionSvc->>SessionSvc: _save_message (USER_ANSWER)
        SessionSvc-->>WS: answer_received event (answer_id)
        WS-->>Client: answer_received
        %% Trigger async evaluation
        SessionSvc->>CeleryEval: evaluate_answer_task.delay(answer.id)
        SessionSvc->>WS: evaluating event
        WS-->>Client: evaluating

        %% Async Evaluation (see separate flow for details)
        CeleryEval->>EvalSvc: evaluate_answer(answer)
        EvalSvc->>LLMClient: evaluate(context)
        LLMClient->>LLMProv: chat model invocation (structured output)
        LLMProv-->>LLMClient: EvaluationResult (score, feedback, etc.)
        LLMClient-->>EvalSvc: result dict
        EvalSvc->>ModelAnswer: update fields (score, feedback, status=GRADED, etc.)
        ModelAnswer-->>EvalSvc: updated answer
        EvalSvc-->>CeleryEval: done
        CeleryEval->>WS (via channel_layer): group_send interview.evaluation.done {answer_id, score, ...}
        WS-->>Client: evaluation_done event

        %% Repeat next_question / submit_answer until done ... (omitted for brevity)

        %% After wrap_up, report generation triggered
        WS->>SessionSvc: wrap_up(session) (called when no more questions)
        SessionSvc->>ModelSession: transition to WRAP_UP
        SessionSvc->>SessionSvc: _save_message (WRAP_UP)
        SessionSvc-->>WS: wrap_up_msg
        WS-->>Client: wrap_up event
        SessionSvc->>CeleryReport: generate_report_task.apply_async(session.pk, countdown=5)

        %% Async Report Generation
        CeleryReport->>ReportSvc: generate_final_report(session)
        ReportSvc->>ModelAnswer: get graded answers for session
        ModelAnswer-->>ReportSvc: list of answers
        ReportSvc->>ReportSvc: compute stats (avg_score, etc.)
        ReportSvc->>LLMClient: generate_report_summary(session_data)
        LLMClient->>LLMProv: chat model invocation (structured output)
        LLMProv-->>LLMClient: FinalResult (ai_summary, etc.)
        LLMClient-->>ReportSvc: summary dict
        ReportSvc->>ModelSession: update final_score, final_report, summary, transition to COMPLETED
        ModelSession-->>ReportSvc: updated session
        ReportSvc-->>CeleryReport: done
        CeleryReport->>WS (via channel_layer): group_send interview.report.ready {session_uuid, final_score, message}
        WS-->>Client: report_ready event

        %% Client can now fetch report via REST
        Client->>API: GET /api/v1/interviews/<uuid>/report/
        API->>ModelSession: get session
        ModelSession-->>API: session with final_report
        API-->>Client: 200 OK {report}

        %% Disconnect (optional)
        Client->>WS: WebSocket close
        WS->>WS: group_discard interview_<uuid>
        WS-->>Client: disconnected
    ```

    ### 2.3 Async Task Execution Flow
    ```mermaid
    sequenceDiagram
        participant Caller as Trigger (e.g., OTPService, InterviewConductService)
        participant Celery as Celery Worker
        participant Task as Celery Task Function
        participant Service as Business Service (NotificationService, EvaluationService, ReportService)
        participant External as External System (SMS Provider, LLM, DB)

        %% OTP sending task
        Caller->>Celery: send_otp_notification_task.delay(notification_id)
        Celery->>Task: apps.notifications.tasks.send_otp_notification_task
        Task->>Service: NotificationService.send_notification(notification_id)
        Service->>External: send SMS via Twilio (or console in dev)
        External-->>Service: success/failure
        Service->>Task: update Notification record (SENT/FAILED)
        Task-->>Caller: result

        %% Answer evaluation task
        Caller->>Celery: evaluate_answer_task.delay(answer_id)
        Celery->>Task: apps.interviews.tasks.evaluate_answer_task
        Task->>Service: EvaluationService.evaluate_answer(answer)
        Service->>External: call LLMClient.evaluate -> LLM Provider API
        External-->>Service: evaluation result
        Service->>Task: update UserAnswer (GRADED + fields)
        Task->>Celery: (optional) trigger check_all_evaluated
        Task-->>Caller: result

        %% Report generation task
        Caller->>Celery: generate_report_task.delay(session_id)
        Celery->>Task: apps.interviews.tasks.generate_report_task
        Task->>Service: ReportService.generate_final_report(session)
        Service->>External: call LLMClient.generate_report_summary -> LLM Provider API
        External-->>Service: report summary
        Service->>Task: update InterviewSession (final_score, final_report, COMPLETED)
        Task->>Celery: (optional) push report_ready via channel layer
        Task-->>Caller: result
    ```

    ### 2.4 External API Calls
    ```mermaid
    sequenceDiagram
        participant Service as Business Service (EvaluationService / ReportService)
        participant LLMClient as LLM Client (apps.core.llm.client.LLMClient)
        participant LLMFactory as ProviderFactory
        participant LLMProv as LLM Provider (OpenAI / Anthropic / OpenRouter / Ollama)
        participant HTTP as HTTP Call to Provider API
        participant NotifSvc as NotificationService
        participant NotifProv as Notification Provider (Twilio / Console)

        %% LLM call for answer evaluation
        Service->>LLMClient: evaluate(context)
        LLMClient->>LLMFactory: create provider from settings (singleton)
        LLMFactory-->>LLMClient: provider instance
        LLMClient->>LLMProv: get_chat_model(temperature=0.1) -> ChatModel
        LLMClient->>LLMProv: with_structured_output(EvaluationResult) -> StructuredLLM
        LLMClient->>StructuredLLM: invoke(prompt)
        StructuredLLM->>HTTP: POST to provider endpoint (e.g., api.openai.com/v1/chat/completions)
        HTTP-->>StructuredLLM: JSON response (message.content)
        StructuredLLM-->>LLMClient: parsed EvaluationResult
        LLMClient-->>Service: result dict (score, feedback, etc.)

        %% LLM call for report generation
        Service->>LLMClient: generate_report_summary(session_data)
        LLMClient->>LLMFactory: create provider from settings
        LLMFactory-->>LLMClient: provider instance
        LLMClient->>LLMProv: get_chat_model(temperature=0.2) -> ChatModel
        LLMClient->>LLMProv: with_structured_output(FinalReport) -> StructuredLLM
        LLMClient->>StructuredLLM: invoke(prompt)
        StructuredLLM->>HTTP: POST to provider endpoint
        HTTP-->>StructuredLLM: JSON response
        StructuredLLM-->>LLMClient: parsed FinalReport
        LLMClient-->>Service: summary dict

        %% SMS sending (OTP) external call
        NotifSvc->>NotifProv: send(recipient, body, title)
        NotifProv->>HTTP: POST to Twilio API (messages.json)
        HTTP-->>NotifProv: JSON response (sid, status)
        NotifProv-->>NotifSvc: (success, provider_id, error_message)
        NotifSvc-->>Caller: update Notification record
    ```

    --- 

    *Diagrams reflect the code as of the current repository. Where implementation details are abstracted (e.g., exact JWT issuance), standard library behavior (djangorestframework-simplejwt) is assumed.* 