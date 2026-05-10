# Security

## Reporting a Vulnerability

If you discover a security issue, please do not open a public GitHub issue. Email the details to yachikanand@gmail.com. You can expect a response within 48 hours.

## Security Features

- **Multi-tenant isolation** — tenant filtering is enforced at the Qdrant and PostgreSQL query layer, not the LLM prompt. Cross-tenant data access is structurally impossible.
- **JWT authentication** — all API endpoints require a signed token. Rotate `JWT_SECRET_KEY` regularly in production.
- **Audit trail** — every query and ingestion event is logged via TraceLog with source grounding and faithfulness scores.
- **Secure SSE** — token streaming is delivered over encrypted channels in production.
- **No host-exposed internal ports** — in production, Qdrant, Redis, and PostgreSQL have no ports exposed to the host. All traffic goes through Nginx.

## Production Hardening Checklist

- [ ] Use HTTPS/SSL (handled by `deploy.sh --ssl-init` via Certbot)
- [ ] Set a strong, unique `JWT_SECRET_KEY` (minimum 64 characters)
- [ ] Set a strong `POSTGRES_PASSWORD`
- [ ] Do not expose `OPENAI_API_KEY` in logs or error responses
- [ ] Enable PostgreSQL encryption at rest for patient-sensitive data
- [ ] Comply with your institution's HIPAA/GDPR requirements before uploading patient records
