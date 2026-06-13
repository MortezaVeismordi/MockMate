**API Documentation**  
**Mock Interview Platform - AI-Powered Coding Interviews**

---

### 1. Introduction

This API powers a professional AI-driven mock interview platform for software engineering positions. It supports user authentication (OTP-based), question bank management, interview session lifecycle, real-time interview flow (via WebSocket - not documented here), and comprehensive admin/backoffice capabilities.

**Base URL**: `/api/v1/`

**API Style**: RESTful with consistent JSON response format.

---

### 2. Response Format

All responses follow a unified structure:

#### Success Response
```json
{
  "success": true,
  "message": "Operation completed successfully",
  "data": { ... }
}
```

#### Error Response
```json
{
  "success": false,
  "message": "Error description",
  "errors": { ... }     // optional, present on validation errors
}
```

**Status Codes**:
- `200` - Success
- `201` - Created
- `202` - Accepted (async)
- `204` - No Content
- `400` - Bad Request / Validation
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `429` - Too Many Requests
- `500` - Server Error

---

### 3. Authentication

- **Phone Number + OTP** based authentication (Iranian numbers: `09xxxxxxxxx`)
- JWT Tokens (`access` + `refresh`)
- All protected endpoints require `Authorization: Bearer <access_token>`

**Key Auth Endpoints** are under `/api/v1/users/auth/`

---

### 4. Users Module (`/api/v1/users/`)

#### Auth Endpoints

| Method | Endpoint | Description | Permission |
|--------|----------|-------------|----------|
| `POST` | `/auth/send-otp/` | Send OTP for login/register | Public |
| `POST` | `/auth/resend-otp/` | Resend OTP | Public |
| `POST` | `/auth/verify-otp/` | Verify OTP and receive tokens | Public |
| `POST` | `/auth/refresh-token/` | Refresh access token | Public |
| `POST` | `/auth/logout/` | Blacklist refresh token | Authenticated |

#### Profile Endpoints

| Method | Endpoint | Description | Permission |
|--------|----------|-------------|----------|
| `GET` | `/me/` | Get current user profile | Authenticated |
| `PATCH` | `/me/` | Update profile (partial) | Authenticated |
| `POST` | `/me/complete-profile/` | Complete profile (first time) | Authenticated |
| `PUT` | `/me/avatar/` | Upload avatar | Authenticated |
| `DELETE` | `/me/avatar/` | Delete avatar | Authenticated |
| `DELETE` | `/me/delete/` | Soft delete account (requires OTP) | Authenticated |

#### Admin User Management

| Method | Endpoint | Description | Permission |
|--------|----------|-------------|----------|
| `GET` | `/admin/users/` | List users (with filters & search) | Admin |
| `GET` | `/admin/users/<id>/` | User detail | Admin |
| `PATCH` | `/admin/users/<id>/` | Update user | Admin |
| `DELETE` | `/admin/users/<id>/` | Soft delete user | Admin |
| `POST` | `/admin/users/<id>/suspend/` | Suspend user | Admin |
| `POST` | `/admin/users/<id>/unsuspend/` | Unsuspend user | Admin |
| `POST` | `/admin/users/<id>/ban/` | Permanent ban | Admin |
| `GET` | `/admin/otp-history/<user_id>/` | OTP history | Admin |
| `GET` | `/admin/stats/` | Platform statistics | Admin |

---

### 5. Questions Module (`/api/v1/questions/`)

#### Candidate Endpoints

| Method | Endpoint | Description | Permission |
|--------|----------|-------------|----------|
| `GET` | `/` | List questions (with filters) + Pagination | Authenticated |
| `GET` | `/<id>/` | Question detail | Authenticated |
| `GET` | `/random-set/` | Get random interview question set | Authenticated |
| `GET` | `/categories/` | List all categories | Authenticated |

**Query Parameters**:
- `category`, `seniority`, `limit`

#### Admin Endpoints

| Method | Endpoint | Description | Permission |
|--------|----------|-------------|----------|
| `GET` | `/admin/questions/` | List all questions (including inactive) | Admin |
| `POST` | `/admin/questions/` | Create new question | Admin |
| `GET` | `/admin/questions/<id>/` | Question detail | Admin |
| `PUT` | `/admin/questions/<id>/` | Update question | Admin |
| `DELETE` | `/admin/questions/<id>/` | Delete question | Admin |
| `POST` | `/admin/categories/` | Create category | Admin |
| `POST` | `/admin/ingest/github/` | Trigger GitHub question ingestion | Admin |

---

### 6. Interviews Module (`/api/v1/interviews/`)

#### User Session Endpoints

| Method | Endpoint | Description | Permission |
|--------|----------|-------------|----------|
| `POST` | `/` | Create new interview session | Authenticated |
| `GET` | `/` | List user interview sessions | Authenticated |
| `GET` | `/active/` | Get currently active session | Authenticated |
| `GET` | `/stats/` | User interview statistics + trend | Authenticated |
| `GET` | `/<uuid>/` | Session detail | Authenticated |
| `DELETE` | `/<uuid>/` | Abandon active session | Authenticated |
| `GET` | `/<uuid>/report/` | Final interview report (only COMPLETED) | Authenticated |

**Session Creation Payload**:
```json
{
  "target_position": "Senior Backend Developer",
  "seniority_level": "senior",
  "job_description": "...",
  "focus_topics": ["django", "system-design"],
  "total_questions": 10
}
```

#### Admin / Backoffice Endpoints

| Method | Endpoint | Description | Permission |
|--------|----------|-------------|----------|
| `GET` | `/admin/sessions/` | List all sessions (with filters) | Admin |
| `GET` | `/admin/sessions/<uuid>/` | Session full details | Admin |
| `GET` | `/admin/answers/<pk>/` | Answer detail + raw evaluation | Admin |
| `POST` | `/admin/answers/<pk>/retrigger/` | Retrigger AI evaluation | Admin |

---

### 7. Key Models & Statuses

#### InterviewSession Statuses
- `SETUP`
- `IN_PROGRESS`
- `COMPLETED`
- `ABANDONED`
- `EVALUATING`

#### Seniority Levels
`junior`, `mid_level`, `senior`, `lead`

#### Question Types
- Coding
- System Design
- Behavioral
- etc.

---

### 8. WebSocket Integration

- Real-time interview flow: `/ws/interviews/<session_uuid>/`
- Used for streaming questions, user answers, AI feedback, and follow-ups.

---

### 9. Health Check

- `GET /health/` → Returns status of Database, Redis, etc.

---

### 10. Notes & Best Practices

1. All timestamps are in ISO format.
2. Use proper pagination where available.
3. Rate limiting is active on auth endpoints.
4. Soft deletes are used throughout the system.
5. AI evaluation happens asynchronously via Celery tasks.
6. Admin endpoints provide deep debugging capabilities (`raw_evaluation`, `error_log`, etc.).

---

**This documentation is generated based on the current codebase structure.**  
For detailed request/response examples per endpoint, refer to the docstrings in the respective view files.

**Last Updated**: June 2026