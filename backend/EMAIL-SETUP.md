# Email System — Zoho ZeptoMail

The mail transport is selected by `EMAIL_PROVIDER`: use Google SMTP for a
deployment test and ZeptoMail's HTTPS API in production. The app renders every
message locally, so switching transports does not change application code.

## Deployment test — Google SMTP

```bash
EMAIL_PROVIDER=google
EMAIL_FROM=your-google-workspace-address@example.com
GOOGLE_SMTP_HOST=smtp.gmail.com
GOOGLE_SMTP_PORT=587
GOOGLE_SMTP_USER=your-google-workspace-address@example.com
GOOGLE_SMTP_PASSWORD=your-16-character-google-app-password
```

Google requires a Google App Password; do not use the normal account password.

## Production — Zoho ZeptoMail

1. In ZeptoMail, add and verify the sending domain and create an Agent.
2. Open **Agent → SMTP/API → API** and copy the Send Mail Token.
3. Set the deployment environment:

```bash
EMAIL_PROVIDER=zeptomail
EMAIL_FROM=no-reply@yourdomain.com
EMAIL_FROM_NAME="Your ERP"
ZEPTO_MAIL_SEND_TOKEN=your-agent-send-mail-token
ZEPTO_MAIL_API_URL=https://api.zeptomail.com/v1.1/email
```

Use `https://api.zeptomail.in/v1.1/email` for an India data centre.
`EMAIL_REPLY_TO` is optional.

The API request uses `Authorization: Zoho-enczapikey <token>` and JSON fields
`from`, `to`, `subject`, `textbody`, and `htmlbody`. Any 2xx response is
accepted; invalid 4xx responses fail an outbox row immediately, while 429 and
5xx responses remain retryable.

## Development and operations

Use `EMAIL_PROVIDER=console` to log messages without delivery. Existing email
operations are unchanged:

```text
GET  /api/v1/email/status
POST /api/v1/email/test
POST /api/v1/email/outbox/drain
```

Queued emails are delivered after the transaction commits. This prevents an
email outage from rolling back provisioning and retries temporary failures.
