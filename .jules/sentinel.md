# Sentinel Journal — ERP Codebase

> Only critical security learnings are recorded here. Not routine fixes.

---

## 2026-08-17 - Shared Hardcoded Default Password for All Student Accounts

**Vulnerability:** All student accounts across every tenant (institution) were created with the same hardcoded weak password `"password1232!"` (and staff during setup with `"Setup@12345"`). Anyone who knew a student's roll number — which is often sequential or public — could log in to any student account on the platform. No `password_reset_token` was set, so there was no forced password change on first login.

**Learning:** The staff invite flow in `institution_service.py` already had the right pattern (random token + 7-day reset window), but the student creation paths copied a simpler approach from an early prototype and never got the same treatment. Three separate code paths (`create_student`, `_create_one_student_row`, and `setup_service.materialize`) all shared the same constant, meaning a fix in one place would not protect the other two.

**Prevention:** User accounts that need a human to set a password should NEVER be created with a shared constant default. Use `generate_secure_token()` to mint a unique random initial password per user. The token is computationally unguessable, so even without a forced-reset mechanism the account cannot be accessed until credentials are properly distributed or the reset flow is used.
