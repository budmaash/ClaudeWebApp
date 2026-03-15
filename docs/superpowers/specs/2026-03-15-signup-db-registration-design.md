# Signup DB Registration Design

**Date:** 2026-03-15
**Status:** Approved

## Overview

When a user completes Auth0 signup or login, persist their identity to the `WebApp` PostgreSQL database (`users` table) and collect their first/last name to populate the `students` table via an onboarding step.

## Goals

- Insert new users into `users` on first Auth0 callback
- Redirect new users (no `students` row) to `/onboarding` to collect first/last name
- Insert into `students` on onboarding form submit
- Never recreate a student row that already exists
- Consolidate all DB access to a single `WebApp` database (replacing `SAT_Database`)

---

## Database Consolidation

Replace the existing `DB_CONFIG` block in `app.py` with:

```python
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", "5432")),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "dbname": os.environ.get("DB_NAME", "WebApp"),
}
```

**Explicitly:** rename all five `SAT_DB_*` environment variable keys to `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`. Update any `.env` file accordingly. All existing call sites (`available_tests`, `load_questions`, response persistence) continue to use `DB_CONFIG` — only the env var names and target database name change.

**`DB_ENABLED` is removed entirely.** Remove the guard variable and the `SAT_DB_ENABLED` env var. The error handling behavior of existing DB callers after removal is as follows:

- **Auth and onboarding paths** (`auth_callback`, `POST /onboarding`) — fail hard: `abort(500)` on any DB error. These paths cannot succeed without DB access.
- **Question bank** (`_available_database_tests`) — remains soft-fail: catches `psycopg2.Error`, logs a warning, and returns an empty test list. An empty test list is visible to the user and is acceptable degradation.
- **Response persistence** (`_persist_submission`, `_persist_student_and_responses`) — remains soft-fail: catches `psycopg2.Error` and logs a warning. Changing these error semantics is out of scope for this feature.

In all three soft-fail cases, simply remove the `if not DB_ENABLED: return` guard line; the existing `except psycopg2.Error` blocks below each guard are retained unchanged.

- **`_load_database_questions`** — hard-fail by design: remove only the `if not DB_ENABLED:` guard line. The existing `except psycopg2.Error` re-raises as `RuntimeError`, which propagates to the caller and results in a 500. No change to error semantics.

---

## Database Schemas (existing in WebApp)

```sql
-- users
id            SERIAL PRIMARY KEY
auth0_user_id TEXT NOT NULL UNIQUE
email         TEXT NOT NULL UNIQUE
email_verified BOOLEAN NOT NULL DEFAULT false
role          TEXT NOT NULL DEFAULT 'student'
created_at    TIMESTAMP NOT NULL DEFAULT now()
last_login_at TIMESTAMP  -- no default; set explicitly on every login including first

-- students
id         SERIAL PRIMARY KEY
user_id    INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE
first_name TEXT
last_name  TEXT
created_at TIMESTAMP NOT NULL DEFAULT now()
```

---

## Session Structure

`session["user"]` is a dict with exactly these keys, set in `auth_callback` for all three branches:

```python
session["user"] = {
    "user_id": <users.id>,          # integer PK from WebApp users table (from DB)
    "auth0_user_id": <sub>,         # Auth0 subject — sourced from userinfo token in all branches
    "email": <email>,               # sourced from userinfo token in all branches
    "role": <role>,                 # sourced from DB row in all branches
}
```

`user_id` is the canonical key used everywhere (onboarding, `_login_required`, dashboard). `auth0_user_id` and `email` are always read from the Auth0 `userinfo` token payload, not re-fetched from the DB.

---

## Auth Flow

```
GET /  (unauthenticated) → /signup
  Sign Up button → Auth0 (screen_hint=signup)
  Log In button  → Auth0 (login)

Auth0 → /auth/callback
  ├── 1. Get userinfo from token (sub, email, email_verified)
  │
  ├── 2. SELECT id, role FROM users WHERE auth0_user_id = <sub>
  │
  ├── New user (no row found)
  │     → INSERT INTO users (auth0_user_id, email, email_verified, role, last_login_at)
  │          VALUES (<sub>, <email>, <email_verified>, 'student', now())
  │          ON CONFLICT (auth0_user_id) DO NOTHING
  │     → Re-SELECT id, role FROM users WHERE auth0_user_id = <sub>
  │          → If still None: log error + abort(500)   ← handles race/delete edge case
  │     → session["user"] = {user_id, auth0_user_id, email, role}
  │     → redirect /onboarding
  │
  ├── Returning user, no students row
  │     → UPDATE users SET last_login_at = now() WHERE id = <user_id>
  │     → session["user"] = {user_id, auth0_user_id, email, role}
  │     → redirect /onboarding
  │
  └── Returning user, has students row
        → UPDATE users SET last_login_at = now() WHERE id = <user_id>
        → session["user"] = {user_id, auth0_user_id, email, role}
        → redirect /dashboard
```

`last_login_at = now()` is set on every login including first (included in the INSERT).

---

## Routes

### `GET /onboarding` — new, `@_login_required`

Renders `onboarding.html` with a form (POST to `/onboarding`) containing:
- First Name text input
- Last Name text input
- Submit button

If an already-onboarded user lands here (e.g. back button), the form renders and re-submit is harmless via `ON CONFLICT DO NOTHING`. No redirect guard is added.

`base.html` already renders Flask flash messages; `onboarding.html` inherits this automatically via `{% extends 'base.html' %}`.

### `POST /onboarding` — new, `@_login_required`

1. Read `user_id` from `session["user"]["user_id"]`. If missing: redirect to `/signup`.
2. Read `first_name` and `last_name` from form data.
3. Strip leading/trailing whitespace from both.
4. Validate: both non-empty after stripping, max 255 chars each. On failure: flash error message, re-render form.
5. `INSERT INTO students (user_id, first_name, last_name) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO NOTHING`
6. Redirect to `/dashboard`.

---

## Existing Code Changes

### `_find_student_id` and `_persist_student_and_responses`

Left unchanged. Students inserted via onboarding will have `first_name` and `last_name` set, so name-based lookup continues to work. Updating this flow to use `user_id` is out of scope.

### `inject_globals` placement

`inject_globals` is currently defined after the `if __name__ == "__main__":` block (a pre-existing misplacement). Move it above that block as part of this feature's `app.py` changes. This is in scope.

All new routes (`GET /onboarding`, `POST /onboarding`) are also added before the `if __name__` block.

---

## Error Handling

| Location | Error type | Handling |
|---|---|---|
| `auth_callback` — user INSERT | Unique constraint (`auth0_user_id`) | Resolved by re-SELECT after `ON CONFLICT DO NOTHING` |
| `auth_callback` — re-SELECT returns None | Row deleted between INSERT and SELECT | Log + `abort(500)` |
| `auth_callback` — DB connectivity | `psycopg2.OperationalError` | `abort(500)` |
| `auth_callback` — other DB error | `psycopg2.Error` | Log + `abort(500)` |
| POST `/onboarding` — validation failure | Empty/too-long name | Flash error + re-render form |
| POST `/onboarding` — students INSERT conflict | `psycopg2.IntegrityError` (unique) | Silent — `ON CONFLICT DO NOTHING` handles it |
| POST `/onboarding` — DB connectivity | `psycopg2.OperationalError` | `abort(500)` |
| POST `/onboarding` — other DB error | `psycopg2.Error` | Log + flash error + re-render form |
| POST `/onboarding` — missing `user_id` in session | `KeyError` | Redirect to `/signup` |

---

## New File

### `templates/onboarding.html`

Extends `base.html` (which handles flash message rendering). Simple card with first name and last name inputs, submitting POST to `/onboarding`.

---

## Idempotency Summary

- `users` insert: `ON CONFLICT (auth0_user_id) DO NOTHING` + re-SELECT ensures exactly one row per Auth0 user.
- `students` insert: `ON CONFLICT (user_id) DO NOTHING` makes re-submitting the onboarding form safe.
- Returning users with an existing `students` row bypass `/onboarding` entirely via the callback check.

---

## Out of Scope

- Editing profile (name changes) after onboarding
- Role management beyond the default `'student'`
- Migrating historical data from `SAT_Database`
- CSRF protection on onboarding form
- Updating `_find_student_id` to use `user_id` lookup
