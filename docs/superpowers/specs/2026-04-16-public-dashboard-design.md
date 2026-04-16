# Public Dashboard Design

**Date:** 2026-04-16  
**Branch:** public_version_dev  
**Status:** Approved

## Overview

Make the homepage (`/`) the dashboard and allow public (unauthenticated) users to go through the full scoring flow — test selection, answer entry, and results — without requiring login.

## Goals

- Remove the login gate from the homepage and the scoring flow
- Public users enter their name manually on the entry page
- Public user submissions are not saved to the database
- Logged-in users retain full existing behavior (DB-backed name pre-fill, persistence)

## Architecture

No new routes, templates, or abstractions are introduced. Three existing routes are modified in `app.py`.

## Changes

### 1. `root()` at `/`

Remove the redirect-to-signup logic. Instead, call `_render_test_selection_page("index.html")` directly — the same function the `/dashboard` route uses. Both authenticated and unauthenticated users see the dashboard at `/`.

### 2. `/dashboard`

Remove the `@_login_required` decorator. The route remains so existing links and bookmarks continue to work.

### 3. `/entry`

Remove the `@_login_required` decorator. For unauthenticated users, `_get_student_name()` returns `("", "")`, so the name fields arrive blank and the user fills them in manually. Existing validation (first and last name required) is unchanged.

### 4. `/results`

Remove the `@_login_required` decorator. Wrap both persistence calls in `if _is_authenticated():` so they are skipped for public users. The score report is still computed and rendered in full.

```python
if _is_authenticated():
    _persist_student_and_responses(...)
    _persist_submission(...)
```

## What does NOT change

- Auth0 login/signup flow and the `/auth/*` routes
- Onboarding flow
- Header login/logout UI (already driven by `is_authenticated` context variable)
- The scoring and report logic
- Any template files
