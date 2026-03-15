# Signup DB Registration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a user signs up or logs in via Auth0, insert them into the `WebApp` PostgreSQL database (`users` table) and redirect new users to an onboarding page to collect first/last name for the `students` table.

**Architecture:** Three-branch `auth_callback` — new users are inserted into `users` then sent to `/onboarding`; returning users without a `students` row go to `/onboarding`; returning users with a `students` row go to `/dashboard`. A new `GET/POST /onboarding` route handles name collection and `students` insertion. All DB access is consolidated to `WebApp`, replacing `SAT_Database`.

**Tech Stack:** Python 3, Flask, psycopg2 (raw SQL), Auth0 (Authlib), Jinja2 templates.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app.py` | Modify | DB config, DB_ENABLED removal, auth_callback rewrite, new onboarding routes, inject_globals fix |
| `templates/onboarding.html` | Create | Form to collect first/last name |

---

## Chunk 1: DB Consolidation + DB_ENABLED Removal

### Task 1: Replace DB_CONFIG and remove DB_ENABLED

**Files:**
- Modify: `app.py:25-32`

Context: `DB_CONFIG` currently points to `SAT_Database` using `SAT_DB_*` env vars. `DB_ENABLED` gates all DB access. Both must be replaced.

- [ ] **Step 1: Update DB_CONFIG**

In `app.py`, replace lines 25–32:

```python
# OLD — remove this entire block:
DB_CONFIG = {
    "host": os.environ.get("SAT_DB_HOST", "localhost"),
    "port": int(os.environ.get("SAT_DB_PORT", "5432")),
    "user": os.environ.get("SAT_DB_USER", "postgres"),
    "password": os.environ.get("SAT_DB_PASSWORD", "3rdtrail"),
    "dbname": os.environ.get("SAT_DB_NAME", "SAT_Database"),
}
DB_ENABLED = os.environ.get("SAT_DB_ENABLED", "1") not in {"0", "false", "False"}
```

Replace with:

```python
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", "5432")),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "dbname": os.environ.get("DB_NAME", "WebApp"),
}
```

- [ ] **Step 2: Remove DB_ENABLED guard from `_available_database_tests`**

Find this block in `_available_database_tests` (around line 132):

```python
        if not DB_ENABLED:
            return tests
```

Delete those two lines. The `try/except psycopg2.Error` block below it remains unchanged — it already soft-fails with a warning log.

- [ ] **Step 3: Remove DB_ENABLED guard from `_load_database_questions`**

Find this block in `_load_database_questions` (around line 193):

```python
        if not DB_ENABLED:
            raise RuntimeError("Database-backed tests are disabled via configuration.")
```

Delete those two lines. The existing `except psycopg2.Error` block already raises `RuntimeError` — error semantics are unchanged.

- [ ] **Step 4: Remove DB_ENABLED guard from `_persist_submission`**

Find this block in `_persist_submission` (around line 420):

```python
    if not DB_ENABLED:
        return
```

Delete those two lines. The `try/except psycopg2.Error` block below it remains unchanged.

- [ ] **Step 5: Remove DB_ENABLED guard from `_persist_student_and_responses`**

Find this block in `_persist_student_and_responses` (around line 493):

```python
    if not DB_ENABLED:
        return
```

Delete those two lines. The `try/except psycopg2.Error` block below it remains unchanged.

- [ ] **Step 6: Verify no remaining references to DB_ENABLED or SAT_DB_**

Search `app.py` for any remaining occurrences of `DB_ENABLED`, `SAT_DB_`, or `SAT_Database`. There should be none. If any remain, remove them.

- [ ] **Step 7: Verify the app starts without error**

```bash
cd "/Users/majidhasan/Documents/Hasan Tutoring/ClaudeWebApp"
python -c "import app; print('OK')"
```

Expected: `OK` with no import errors.

- [ ] **Step 8: Commit**

```bash
git add app.py
git commit -m "feat: consolidate DB config to WebApp, remove DB_ENABLED"
```

---

### Task 2: Fix inject_globals placement

**Files:**
- Modify: `app.py:775-785`

Context: `inject_globals` is currently defined after `if __name__ == "__main__": app.run(debug=True)`. This is a misplacement — move it above that block.

- [ ] **Step 1: Move inject_globals above the `if __name__` block**

Currently (around line 775):

```python
if __name__ == "__main__":
    app.run(debug=True)
@app.context_processor
def inject_globals():
    return {
        "current_year": datetime.utcnow().year,
        "current_user": session.get("user"),
        "is_authenticated": _is_authenticated(),
        "auth0_login_url": _build_auth0_authorize_url(),
        "auth0_signup_url": _build_auth0_authorize_url(screen_hint="signup"),
    }
```

Rewrite as:

```python
@app.context_processor
def inject_globals():
    return {
        "current_year": datetime.utcnow().year,
        "current_user": session.get("user"),
        "is_authenticated": _is_authenticated(),
        "auth0_login_url": _build_auth0_authorize_url(),
        "auth0_signup_url": _build_auth0_authorize_url(screen_hint="signup"),
    }


if __name__ == "__main__":
    app.run(debug=True)
```

- [ ] **Step 2: Verify the app starts without error**

```bash
python -c "import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "fix: move inject_globals above __main__ block"
```

---

## Chunk 2: auth_callback Rewrite

### Task 3: Rewrite auth_callback with three-branch DB logic

**Files:**
- Modify: `app.py` — `auth_callback` function (currently around line 684)

Context: The current `auth_callback` just stores raw Auth0 `userinfo` in the session and redirects to `/dashboard`. It must be replaced with a three-branch flow: new user → insert to `users` → `/onboarding`; returning user without `students` row → update `last_login_at` → `/onboarding`; returning user with `students` row → update `last_login_at` → `/dashboard`.

The session dict changes from raw Auth0 claims to a structured dict: `{user_id, auth0_user_id, email, role}`.

- [ ] **Step 1: Replace auth_callback**

Find the current `auth_callback` (around line 684):

```python
@app.get("/auth/callback")
def auth_callback():
    token = _auth0_client().authorize_access_token()
    userinfo = token.get("userinfo")
    if not userinfo:
        userinfo = _auth0_client().userinfo()
    session["user"] = dict(userinfo)
    return redirect(url_for("dashboard"))
```

Replace with:

```python
@app.get("/auth/callback")
def auth_callback():
    token = _auth0_client().authorize_access_token()
    userinfo = token.get("userinfo")
    if not userinfo:
        userinfo = _auth0_client().userinfo()

    auth0_user_id = userinfo["sub"]
    email = userinfo.get("email", "")
    email_verified = bool(userinfo.get("email_verified", False))

    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                # Look up existing user
                cursor.execute(
                    "SELECT id, role FROM users WHERE auth0_user_id = %s",
                    (auth0_user_id,),
                )
                row = cursor.fetchone()

                if row is None:
                    # New user — insert, then re-select to get id
                    cursor.execute(
                        """
                        INSERT INTO users (auth0_user_id, email, email_verified, role, last_login_at)
                        VALUES (%s, %s, %s, 'student', now())
                        ON CONFLICT (auth0_user_id) DO NOTHING
                        """,
                        (auth0_user_id, email, email_verified),
                    )
                    conn.commit()
                    cursor.execute(
                        "SELECT id, role FROM users WHERE auth0_user_id = %s",
                        (auth0_user_id,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        app.logger.error(
                            "auth_callback: user row missing after insert for sub=%s", auth0_user_id
                        )
                        abort(500)
                else:
                    # Returning user — update last_login_at
                    cursor.execute(
                        "UPDATE users SET last_login_at = now() WHERE id = %s",
                        (row[0],),
                    )
                    conn.commit()

                user_id, role = row

                session["user"] = {
                    "user_id": user_id,
                    "auth0_user_id": auth0_user_id,
                    "email": email,
                    "role": role,
                }

                # Check for existing students row
                cursor.execute(
                    "SELECT 1 FROM students WHERE user_id = %s",
                    (user_id,),
                )
                has_student = cursor.fetchone() is not None

    except psycopg2.OperationalError as exc:
        app.logger.error("auth_callback: DB connection failed: %s", exc)
        abort(500)
    except psycopg2.Error as exc:
        app.logger.error("auth_callback: DB error: %s", exc)
        abort(500)

    if has_student:
        return redirect(url_for("dashboard"))
    return redirect(url_for("onboarding"))
```

- [ ] **Step 2: Verify the app starts without syntax errors**

```bash
python -c "import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Manual smoke test — new user flow**

Start the app:
```bash
flask run
```

1. Visit `http://localhost:5000/` unauthenticated → should redirect to `/signup`
2. Click Sign Up → Auth0 signup page opens (no name fields required)
3. Complete Auth0 signup with a fresh email
4. Should land on `/onboarding` (page will 404 until Task 4 — that's expected here)
5. Check the `WebApp` database:
```sql
SELECT * FROM users ORDER BY created_at DESC LIMIT 1;
```
Expected: a row with your Auth0 `sub`, email, `role='student'`, and `last_login_at` set.

- [ ] **Step 4: Manual smoke test — returning user with student row**

If you have a user in `users` who also has a `students` row:
1. Log in via Auth0
2. Should redirect to `/dashboard` (not `/onboarding`)

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: rewrite auth_callback to insert user into WebApp DB"
```

---

## Chunk 3: Onboarding Routes and Template

### Task 4: Add onboarding routes to app.py

**Files:**
- Modify: `app.py` — add `GET /onboarding` and `POST /onboarding` before the `inject_globals` context processor

- [ ] **Step 1: Add onboarding routes**

Insert the following two routes directly before the `@app.context_processor` line for `inject_globals`:

```python
@app.get("/onboarding")
@_login_required
def onboarding():
    return render_template("onboarding.html")


@app.post("/onboarding")
@_login_required
def onboarding_post():
    try:
        user_id = session["user"]["user_id"]
    except (KeyError, TypeError):
        return redirect(url_for("signup"))

    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()

    errors = []
    if not first_name:
        errors.append("First name is required.")
    elif len(first_name) > 255:
        errors.append("First name must be 255 characters or fewer.")
    if not last_name:
        errors.append("Last name is required.")
    elif len(last_name) > 255:
        errors.append("Last name must be 255 characters or fewer.")

    if errors:
        for error in errors:
            flash(error, "error")
        return render_template("onboarding.html")

    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO students (user_id, first_name, last_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (user_id, first_name, last_name),
                )
            conn.commit()
    except psycopg2.OperationalError as exc:
        app.logger.error("onboarding_post: DB connection failed: %s", exc)
        abort(500)
    except psycopg2.Error as exc:
        app.logger.error("onboarding_post: DB error: %s", exc)
        flash("Something went wrong saving your information. Please try again.", "error")
        return render_template("onboarding.html")

    return redirect(url_for("dashboard"))
```

Note: Flask maps `GET /onboarding` to `onboarding` and `POST /onboarding` to `onboarding_post`. The `url_for("onboarding")` reference in `auth_callback` (Task 3) resolves to the GET handler.

- [ ] **Step 2: Verify the app starts without errors**

```bash
python -c "import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add GET/POST /onboarding routes"
```

---

### Task 5: Create onboarding.html template

**Files:**
- Create: `templates/onboarding.html`

Context: `base.html` already renders Flask flash messages (in `get_flashed_messages()` inside `<main>`), so no extra flash rendering is needed in this template.

- [ ] **Step 1: Create the template**

Create `templates/onboarding.html` with content that matches the visual style of `signup.html` (same card/panel structure):

```html
{% extends 'base.html' %}
{% block title %}Welcome · SAT Math Score Tool{% endblock %}
{% block content %}
  <style>
    .onboarding-panel {
      width: min(600px, 92vw);
      margin: clamp(110px, 13vh, 170px) auto 2rem;
      background: #fff;
      border: 1px solid #e2ddd3;
      border-radius: 1.25rem;
      box-shadow: 0 18px 45px rgba(17, 17, 17, 0.08);
      padding: clamp(1.5rem, 4vw, 2.75rem);
    }

    .onboarding-panel h2 {
      margin-top: 0;
      font-size: 2rem;
      color: #151515;
    }

    .onboarding-panel p {
      color: #4f4f4f;
      margin: 0 0 1.5rem;
    }

    .onboarding-field {
      display: flex;
      flex-direction: column;
      margin-bottom: 1.2rem;
    }

    .onboarding-field label {
      font-weight: 600;
      letter-spacing: 0.05em;
      margin-bottom: 0.4rem;
      color: #151515;
    }

    .onboarding-field input {
      padding: 0.85rem 0.95rem;
      border-radius: 0.85rem;
      border: 1px solid #e2ddd3;
      background: #fbfaf7;
      font-size: 1rem;
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }

    .onboarding-field input:focus {
      outline: none;
      border-color: #c6a764;
      box-shadow: 0 0 0 3px rgba(198, 167, 100, 0.25);
    }

    .onboarding-actions {
      margin-top: 1.5rem;
    }

    @media (max-width: 640px) {
      .onboarding-panel {
        width: 100%;
        margin-top: 110px;
      }
    }
  </style>

  <section class="card onboarding-panel">
    <h2>Welcome! Tell us your name.</h2>
    <p>We need your name to track your progress.</p>

    <form method="post" action="{{ url_for('onboarding_post') }}">
      <div class="onboarding-field">
        <label for="first_name">First Name</label>
        <input
          type="text"
          id="first_name"
          name="first_name"
          placeholder="First name"
          maxlength="255"
          required
          autofocus
        />
      </div>

      <div class="onboarding-field">
        <label for="last_name">Last Name</label>
        <input
          type="text"
          id="last_name"
          name="last_name"
          placeholder="Last name"
          maxlength="255"
          required
        />
      </div>

      <div class="onboarding-actions">
        <button
          type="submit"
          class="btn btn--border theme-btn--primary-inverse sqs-button-element--tertiary"
          style="width: 214px; height: 60px;"
        >
          Continue
        </button>
      </div>
    </form>
  </section>
{% endblock %}
```

- [ ] **Step 2: Verify the template renders**

With the app running:
```
GET http://localhost:5000/onboarding
```
(You'll be redirected to `/signup` if not logged in — that's correct. Log in first, then visit `/onboarding` directly.)

Expected: Form with First Name, Last Name fields and a Continue button.

- [ ] **Step 3: End-to-end manual test — new signup**

1. Clear session / use incognito
2. Visit `http://localhost:5000/` → redirects to `/signup`
3. Click Sign Up → Auth0 signup page
4. Sign up with a new email
5. Should land on `/onboarding` with the name form
6. Enter first and last name, click Continue
7. Should redirect to `/dashboard`
8. Check DB:
```sql
SELECT u.email, s.first_name, s.last_name
FROM users u
JOIN students s ON s.user_id = u.id
ORDER BY u.created_at DESC LIMIT 1;
```
Expected: Your email and the names you entered.

- [ ] **Step 4: End-to-end manual test — returning user**

1. Log out and log back in with the same account
2. Should redirect directly to `/dashboard` (skipping `/onboarding`)
3. Check `last_login_at` was updated:
```sql
SELECT last_login_at FROM users WHERE email = 'your@email.com';
```

- [ ] **Step 5: Test validation**

1. Visit `/onboarding` while logged in
2. Submit with empty first name → should flash "First name is required." and re-render form
3. Submit with empty last name → should flash "Last name is required." and re-render form
4. Submit with both filled → should redirect to `/dashboard`

- [ ] **Step 6: Test idempotency**

1. After completing onboarding, navigate back to `/onboarding` directly
2. Submit the form again with the same or different names
3. Should redirect to `/dashboard` without error (ON CONFLICT DO NOTHING)
4. DB should still have the original names

- [ ] **Step 7: Test unauthenticated access**

1. Visit `http://localhost:5000/dashboard` without being logged in → should redirect to `/signup`
2. Visit `http://localhost:5000/onboarding` without being logged in → should redirect to `/signup`

- [ ] **Step 8: Commit**

```bash
git add templates/onboarding.html
git commit -m "feat: add onboarding template for first/last name collection"
```

---

## Final Verification Checklist

- [ ] `python -c "import app"` runs clean
- [ ] `DB_CONFIG` points to `WebApp`, no `SAT_DB_*` vars remain
- [ ] `DB_ENABLED` is fully removed from `app.py`
- [ ] `inject_globals` is above the `if __name__` block
- [ ] New signup → `users` row created → `/onboarding` → `students` row created → `/dashboard`
- [ ] Returning user with student row → `/dashboard` directly
- [ ] `last_login_at` updated on every login
- [ ] Validation rejects empty names, flashes error, re-renders form
- [ ] Unauthenticated visits to `/dashboard`, `/onboarding`, `/entry`, `/results` redirect to `/signup`
