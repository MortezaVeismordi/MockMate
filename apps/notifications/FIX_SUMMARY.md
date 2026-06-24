# Fix Summary: Notification Service Missing Provider Bug

## Root Cause
In `NotificationService.send_notification()`, when no provider class is found (which occurs for EMAIL and IN_APP notification types in the development environment due to missing provider configuration), the method logs an error and returns early without updating the notification status. This leaves the notification in `PENDING` status indefinitely because:
- No exception is raised, so the Celery task considers the execution successful
- The notification status is not updated to `FAILED`
- The Celery task does not retry on success
- There is no mechanism to retry notifications stuck in `PENDING` due to configuration errors

## Fix Implementation
Modified `apps/notifications/services.py` in the `send_notification` method to mark the notification as failed when no provider is found, before returning.

**Changes:**
```python
# Before
if not provider_class:
    logger.error(f"No valid provider class found or specified for notification {notification_id}")
    return

# After
if not provider_class:
    logger.error(f"No valid provider class found for notification type: {notification.notification_type}")
    notification.mark_as_failed(error=f"No valid provider class found for notification type: {notification.notification_type}")
    return
```

This ensures:
- Notifications with missing providers are marked as `FAILED`
- An appropriate error message is stored in `error_message`
- The Celery task does not retry (since no exception is raised)
- Operational visibility is maintained through the failed status and error message

## Tests Added
Created comprehensive test suite in `apps/notifications/tests/`:
1. `test_models.py` - Notification model tests
2. `test_services.py` - NotificationService tests (including create_notification and send_notification)
3. `test_providers.py` - Provider tests (KavenegarSMSProvider, SmtpEmailProvider, ConsoleSMSProvider, ConsoleEmailProvider)
4. `test_tasks.py` - Celery task tests

**Key test cases covering the fix:**
- `test_send_notification_no_provider_marks_as_failed` - Verifies SMS/email/in_app notifications without providers are marked as failed
- `test_send_notification_no_provider_in_app_marks_as_failed` - Specific test for IN_APP type
- Tests for successful provider delivery, provider failure, and edge cases

## Files Modified
1. `apps/notifications/services.py` - Fixed the missing provider handling
2. `apps/notifications/tests/test_models.py` - New model tests
3. `apps/notifications/tests/test_services.py` - New service tests
4. `apps/notifications/tests/test_providers.py` - New provider tests
5. `apps/notifications/tests/test_tasks.py` - New task tests

## Remaining Risks
1. **Email notifications in development**: The fix resolves the immediate issue, but email notifications will still fail in development until a ConsoleEmailProvider is properly configured in the service auto-selection logic (currently commented out).
2. **IN_APP notifications**: No provider implementation exists for IN_APP notifications, so they will always fail until a provider is implemented.
3. **Retry logic for permanent failures**: The current task retries on any exception from the service, including permanent failures like missing API keys. Consider distinguishing between transient and permanent failures for better retry behavior.
4. **Notification stuck in PENDING**: Other failure scenarios (e.g., database issues during status update) could still leave notifications in PENDING. The task already handles database errors when updating retry count.

## Coverage Improvement
- **Before**: No tests existed for the notifications app
- **After**: Comprehensive test coverage for:
  - Notification model creation, status transitions, and helper methods
  - NotificationService `create_notification` and `send_notification` methods
  - All provider implementations (success and failure scenarios)
  - Celery task execution, retry logic, and error handling
  - Edge cases: missing notifications, already sent notifications, database errors

Estimated coverage improvement: 0% → ~85%+ for the notifications app, covering all critical business flows and failure paths.