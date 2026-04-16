# Public Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the login gate from the homepage and the full scoring flow so public users can access the dashboard, enter answers, and see results without an account.

**Architecture:** Four targeted edits to `app.py` — change `root()` to render the dashboard directly, remove `@_login_required` from `/dashboard`, `/entry`, and `/results`, and wrap persistence calls in `/results` with an `_is_authenticated()` guard. No template changes needed; the form in `index.html` already posts to `/dashboard`.

**Tech Stack:** Flask, pytest, unittest.mock

---

### Task 1: Add pytest to requirements and create test infrastructure

**Files:**
- Modify: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/test_public_routes.py`

- [ ] **Step 1: Add pytest to requirements.txt**

Add these two lines at the end of `requirements.txt`:

```
pytest>=8.0.0
pytest-mock>=3.12.0
```

- [ ] **Step 2: Create the tests package**

Create an empty file at `tests/__init__.py`.

- [ ] **Step 3: Create the test file with fixtures and shared data**

Create `tests/test_public_routes.py` with this content:

```python
import pytest
from unittest.mock import patch
import app as app_module
from app import app as flask_app, TestDefinition, DatabaseTestMetadata, Question

MOCK_TEST = TestDefinition(
    identifier="db_1_1_1",
    name="Test 1 Math Module 1",
    source="database",
    db_metadata=DatabaseTestMetadata(test_id=1, section_id=1, module_id=1),
)

MOCK_QUESTIONS = [
    Question(number=1, correct_answers=["A"], category="Algebra", expects_numeric_response=False),
    Question(number=2, correct_answers=["B"], category="Algebra", expects_numeric_response=False),
]


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c
```

- [ ] **Step 4: Install pytest**

```bash
pip install pytest>=8.0.0 pytest-mock>=3.12.0
```

---

### Task 2: Write failing tests for public route access

**Files:**
- Modify: `tests/test_public_routes.py`

- [ ] **Step 1: Add four failing tests to `tests/test_public_routes.py`**

Append these tests after the fixture:

```python
def test_root_accessible_without_login(client):
    with patch.object(app_module.question_bank, "available_tests", return_value=[MOCK_TEST]):
        response = client.get("/")
    assert response.status_code == 200


def test_dashboard_accessible_without_login(client):
    with patch.object(app_module.question_bank, "available_tests", return_value=[MOCK_TEST]):
        response = client.get("/dashboard")
    assert response.status_code == 200


def test_entry_accessible_without_login(client):
    with patch.object(app_module.question_bank, "get_test", return_value=MOCK_TEST), \
         patch.object(app_module.question_bank, "questions_for", return_value=MOCK_QUESTIONS):
        response = client.get(
            "/entry?test_id=db_1_1_1&first_name=Jane&last_name=Doe"
        )
    assert response.status_code == 200


def test_results_skips_persistence_without_login(client):
    with patch.object(app_module.question_bank, "get_test", return_value=MOCK_TEST), \
         patch.object(app_module.question_bank, "questions_for", return_value=MOCK_QUESTIONS), \
         patch("app._persist_submission") as mock_submit, \
         patch("app._persist_student_and_responses") as mock_responses:
        response = client.post("/results", data={
            "test_id": "db_1_1_1",
            "first_name": "Jane",
            "last_name": "Doe",
            "q_1": "A",
            "q_2": "B",
        })
    assert response.status_code == 200
    mock_submit.assert_not_called()
    mock_responses.assert_not_called()
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
pytest tests/test_public_routes.py -v
```

Expected: all 4 tests FAIL — `test_root_accessible_without_login` and `test_dashboard_accessible_without_login` get 302 (redirect to signup), `test_entry_accessible_without_login` gets 302, `test_results_skips_persistence_without_login` gets 302.

---

### Task 3: Implement the route changes in `app.py`

**Files:**
- Modify: `app.py:729-739`

- [ ] **Step 1: Change `root()` to render the dashboard directly**

In `app.py`, replace the entire `root()` function (lines 729–733):

```python
@app.get("/")
def root():
    if _is_authenticated():
        return redirect(url_for("dashboard"))
    return redirect(url_for("signup"))
```

with:

```python
@app.get("/")
def root():
    return _render_test_selection_page("index.html")
```

- [ ] **Step 2: Remove `@_login_required` from the `dashboard` route**

In `app.py`, replace:

```python
@app.route("/dashboard", methods=["GET", "POST"])
@_login_required
def dashboard():
    return _render_test_selection_page("index.html")
```

with:

```python
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    return _render_test_selection_page("index.html")
```

- [ ] **Step 3: Remove `@_login_required` from the `entry` route**

In `app.py`, replace:

```python
@app.get("/entry")
@_login_required
def entry():
```

with:

```python
@app.get("/entry")
def entry():
```

- [ ] **Step 4: Remove `@_login_required` from the `results` route and guard persistence**

In `app.py`, replace:

```python
@app.post("/results")
@_login_required
def results():
```

with:

```python
@app.post("/results")
def results():
```

Then find the two persistence calls near the bottom of `results()`:

```python
    _persist_student_and_responses(
        first_name=first_name,
        last_name=last_name,
        test=test,
        questions=questions,
        answers=answers,
    )

    _persist_submission(test=test, student_name=student_name, answers=answers, report=report)
```

and wrap them:

```python
    if _is_authenticated():
        _persist_student_and_responses(
            first_name=first_name,
            last_name=last_name,
            test=test,
            questions=questions,
            answers=answers,
        )
        _persist_submission(test=test, student_name=student_name, answers=answers, report=report)
```

---

### Task 4: Verify tests pass and commit

**Files:**
- No changes

- [ ] **Step 1: Run the full test suite**

```bash
pytest tests/test_public_routes.py -v
```

Expected output:
```
tests/test_public_routes.py::test_root_accessible_without_login PASSED
tests/test_public_routes.py::test_dashboard_accessible_without_login PASSED
tests/test_public_routes.py::test_entry_accessible_without_login PASSED
tests/test_public_routes.py::test_results_skips_persistence_without_login PASSED
4 passed
```

- [ ] **Step 2: Commit**

```bash
git add app.py tests/__init__.py tests/test_public_routes.py requirements.txt
git commit -m "feat: make dashboard and scoring flow public, skip persistence for unauthenticated users"
```
