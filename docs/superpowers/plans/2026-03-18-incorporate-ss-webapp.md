# Incorporate SS_WebApp_Copy into ClaudeWebApp — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ClaudeWebApp's `/dashboard`, `/entry`, and `/results` UI with the richer SS_WebApp_Copy version while keeping ClaudeWebApp's Auth0 header and student-name tracking. All data — questions, video links, auth, students, responses — comes from the single `WebApp` PostgreSQL database via the existing `DB_CONFIG`.

**Architecture:** SS_WebApp_Copy's question-loading logic and richer templates are ported into ClaudeWebApp. No second DB connection is added — the `WebApp` DB already contains all the tables that SS_WebApp_Copy reads from (`questions`, `tests`, `sections`, `modules`, `question_types`, `QType_Vids`). Student name (from Auth0) continues to thread through entry → results as hidden form fields. URL references in adopted templates change from `url_for('index')` to `url_for('dashboard')`.

**Tech Stack:** Python 3, Flask, Jinja2, psycopg2, Auth0/Authlib, PostgreSQL (`WebApp` DB only)

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `ClaudeWebApp/app.py` | Modify | Add `_normalize_category_key`, upgrade `Question`/`QuestionBank`/`build_score_report` |
| `ClaudeWebApp/templates/index.html` | Replace | SS_WebApp_Copy's 3-panel dashboard (instructions + module PDFs + scoring form) |
| `ClaudeWebApp/templates/entry.html` | Replace | SS_WebApp_Copy's entry page, keep student name hidden fields |
| `ClaudeWebApp/templates/results.html` | Replace | SS_WebApp_Copy's richer results page (pie chart + video links + student name) |
| `ClaudeWebApp/static/pdf_icon.jpg` | Copy | PDF icon used by new index.html module grid |

---

## Task 1: Add _normalize_category_key helper to app.py

**Files:** Modify `ClaudeWebApp/app.py`

This helper normalises integer-like strings for dict lookups. It is used by `_load_question_type_video_lookup()` (added in Task 2).

- [ ] **Step 1: Find the insertion point**

Read `app.py` and find the `_is_fraction_string` function and the `question_bank = QuestionBank()` line.

**CRITICAL ordering constraint:** `_normalize_category_key` must be inserted BEFORE `question_bank = QuestionBank()`. `QuestionBank.__init__` will call `_load_question_type_video_lookup()` which calls `_normalize_category_key` — inserting it after instantiation causes `NameError` at startup.

Insert immediately after the closing of `_is_fraction_string` and before `question_bank = QuestionBank()`.

- [ ] **Step 2: Add the helper**

```python
def _normalize_category_key(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return cleaned
    try:
        return str(int(cleaned))
    except ValueError:
        return cleaned
```

- [ ] **Step 3: Verify ordering** — read the surrounding lines and confirm `_normalize_category_key` def appears at a lower line number than `question_bank = QuestionBank()`.

- [ ] **Step 4: Commit**

```bash
cd "/Users/majidhasan/Documents/Hasan Tutoring/ClaudeWebApp"
git add app.py
git commit -m "feat: add _normalize_category_key helper"
```

---

## Task 2: Add category_video_url to Question dataclass

**Files:** Modify `ClaudeWebApp/app.py`

SS_WebApp_Copy's `results.html` renders `row.category_video_url` and `category.category_video_url`. Without this field the template will raise an `UndefinedError`.

- [ ] **Step 1: Find the Question dataclass** (near line 36 in app.py)

- [ ] **Step 2: Add the optional field after `db_question_id`**

Current:
```python
    db_question_id: Optional[int] = None
```

Replace with:
```python
    db_question_id: Optional[int] = None
    category_video_url: Optional[str] = None
```

- [ ] **Step 3: Verify the dataclass looks correct**

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: add category_video_url field to Question dataclass"
```

---

## Task 3: Upgrade QuestionBank to load video URLs from QType_Vids

**Files:** Modify `ClaudeWebApp/app.py`

Three changes inside `QuestionBank`:
1. Add `_load_question_type_video_lookup()` — queries `QType_Vids` table in `WebApp` DB (same `DB_CONFIG`)
2. Call it from `__init__` so video URLs are loaded once at startup
3. Upgrade `_load_database_questions()` — also fetch `question_type_id` per row and attach the video URL to each `Question`

- [ ] **Step 1: Read the current `QuestionBank.__init__`**

It currently reads:
```python
    def __init__(self) -> None:
        self._questions_cache: Dict[str, List[Question]] = {}
```

- [ ] **Step 2: Replace `__init__` and add `_load_question_type_video_lookup`**

```python
    def __init__(self) -> None:
        self._questions_cache: Dict[str, List[Question]] = {}
        self._question_type_video_lookup = self._load_question_type_video_lookup()

    def _load_question_type_video_lookup(self) -> Dict[str, str]:
        lookup: Dict[str, str] = {}
        try:
            with psycopg2.connect(**DB_CONFIG) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT question_types_id, video_link
                        FROM "QType_Vids"
                        WHERE video_link IS NOT NULL
                        """
                    )
                    for question_type_id, video_link in cursor.fetchall():
                        if question_type_id is None or not video_link:
                            continue
                        normalized_key = _normalize_category_key(str(question_type_id))
                        cleaned_path = str(video_link).strip().lstrip("/")
                        if cleaned_path:
                            lookup[normalized_key] = f"https://www.hasantutoring.com/{cleaned_path}"
        except psycopg2.Error as exc:
            app.logger.warning("Failed to load question type video links: %s", exc)
        return lookup
```

- [ ] **Step 3: Upgrade `_load_database_questions()` to fetch `question_type_id` and attach video URL**

Find the existing SQL query inside this method:
```python
        query = """
            SELECT
                q.test_question_number,
                q.correct_answer,
                qt.name AS category_name,
                q.id AS question_id
            FROM questions q
            JOIN question_types qt ON q.question_type_id = qt.id
            WHERE q.test_id = %s AND q.section_id = %s AND q.module_id = %s
            ORDER BY q.test_question_number
        """
```

Replace with:
```python
        query = """
            SELECT
                q.test_question_number,
                q.correct_answer,
                qt.name AS category_name,
                q.id AS question_id,
                q.question_type_id
            FROM questions q
            JOIN question_types qt ON q.question_type_id = qt.id
            WHERE q.test_id = %s AND q.section_id = %s AND q.module_id = %s
            ORDER BY q.test_question_number
        """
```

Update the row-unpacking loop from:
```python
        for test_question_number, correct_answer, category_name, question_id in rows:
```
to:
```python
        for test_question_number, correct_answer, category_name, question_id, question_type_id in rows:
```

Update the `Question(...)` instantiation to add `category_video_url`:
```python
            questions.append(
                Question(
                    number=int(test_question_number),
                    correct_answers=answers,
                    category=category_name,
                    expects_numeric_response=expects_numeric_response,
                    db_question_id=question_id,
                    category_video_url=self._question_type_video_lookup.get(
                        _normalize_category_key(str(question_type_id))
                    ),
                )
            )
```

- [ ] **Step 4: Verify**

Read the full `QuestionBank` class and confirm:
- `__init__` stores `self._question_type_video_lookup`
- `_load_question_type_video_lookup` uses `DB_CONFIG` (not any new config)
- `_load_database_questions` unpacks 5 columns and attaches `category_video_url`
- All other methods (`_available_database_tests`, `get_test`, `questions_for`) are unchanged

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: upgrade QuestionBank to load QType_Vids video URLs from WebApp DB"
```

---

## Task 4: Upgrade build_score_report() to include missed breakdown and video URLs

**Files:** Modify `ClaudeWebApp/app.py`

SS_WebApp_Copy's `results.html` template uses `report.missed_question_breakdown`, `report.missed_count`, and `row.category_video_url`. The current `build_score_report` does not produce these keys.

Note: `from collections import defaultdict` is already at line 7 — no import change needed.

- [ ] **Step 1: Read the current `build_score_report` function**

- [ ] **Step 2: Replace the entire function**

```python
def build_score_report(student_answers: Dict[int, str], questions: List[Question]):
    per_question = []
    category_totals: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    category_video_urls: Dict[str, str] = {}
    missed_totals: Dict[str, int] = defaultdict(int)
    correct_count = 0

    for question in questions:
        student_answer = student_answers.get(question.number, "")
        is_correct = student_answer in question.correct_answers

        category_totals[question.category]["total"] += 1
        if question.category_video_url and question.category not in category_video_urls:
            category_video_urls[question.category] = question.category_video_url
        if is_correct:
            correct_count += 1
            category_totals[question.category]["correct"] += 1
        else:
            missed_totals[question.category] += 1

        per_question.append(
            {
                "number": question.number,
                "student_answer": student_answer or "—",
                "raw_student_answer": student_answer,
                "correct_answer": question.display_correct_answer,
                "is_correct": is_correct,
                "category": question.category,
                "category_video_url": question.category_video_url,
            }
        )

    total_questions = len(questions)
    if total_questions:
        accuracy = correct_count / total_questions
        scaled_score = 200 + math.floor(accuracy * 600)
    else:
        accuracy = 0
        scaled_score = 200

    category_breakdown = []
    for category, totals in sorted(category_totals.items()):
        total = totals["total"]
        correct = totals["correct"]
        accuracy_pct = (correct / total * 100) if total else 0
        category_breakdown.append(
            {
                "category": category,
                "correct": correct,
                "total": total,
                "accuracy_pct": accuracy_pct,
                "category_video_url": category_video_urls.get(category),
            }
        )

    total_missed = total_questions - correct_count
    missed_question_breakdown = []
    if total_missed:
        for category, missed_count in sorted(
            missed_totals.items(),
            key=lambda item: (-item[1], item[0].lower()),
        ):
            missed_question_breakdown.append(
                {
                    "category": category,
                    "missed": missed_count,
                    "share_pct": (missed_count / total_missed) * 100,
                }
            )

    return {
        "per_question": per_question,
        "correct_count": correct_count,
        "total_questions": total_questions,
        "accuracy_pct": accuracy * 100 if total_questions else 0,
        "scaled_score": scaled_score,
        "category_breakdown": category_breakdown,
        "missed_question_breakdown": missed_question_breakdown,
        "missed_count": total_missed,
    }
```

- [ ] **Step 3: Verify by reading the updated function**

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: upgrade build_score_report with missed breakdown and video URL fields"
```

---

## Task 5: Copy pdf_icon.jpg static asset

**Files:** Copy `SS_WebApp_Copy/static/pdf_icon.jpg` → `ClaudeWebApp/static/pdf_icon.jpg`

The new `index.html` uses `{{ url_for('static', filename='pdf_icon.jpg') }}` for the module PDF icon grid.

- [ ] **Step 1: Copy the file**

```bash
cp "/Users/majidhasan/Documents/Hasan Tutoring/SS_WebApp_Copy/static/pdf_icon.jpg" \
   "/Users/majidhasan/Documents/Hasan Tutoring/ClaudeWebApp/static/pdf_icon.jpg"
```

- [ ] **Step 2: Verify**

```bash
ls -lh "/Users/majidhasan/Documents/Hasan Tutoring/ClaudeWebApp/static/pdf_icon.jpg"
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/majidhasan/Documents/Hasan Tutoring/ClaudeWebApp"
git add static/pdf_icon.jpg
git commit -m "feat: add pdf_icon.jpg static asset for module grid"
```

---

## Task 6: Replace templates/index.html with SS_WebApp_Copy version

**Files:** Modify `ClaudeWebApp/templates/index.html`

SS_WebApp_Copy's index.html has three panels:
1. **How to use** — explanatory text
2. **SAT Math Modules** — 6×2 grid of PDF icon links (Test 1–6, Module 1–2)
3. **Begin scoring** — test selector form

Only change from the SS source: form action → `url_for('dashboard')` (ClaudeWebApp has no `index` route).

- [ ] **Step 1: Write the new index.html**

```html
{% extends 'base.html' %}
{% block title %}Select Test · SAT Math Score Tool{% endblock %}
{% block content %}
  <style>
    .begin-scoring-panel {
      width: min(980px, 92vw);
      margin: clamp(110px, 13vh, 170px) auto 2rem;
      background: #fff;
      border: 1px solid #e2ddd3;
      border-radius: 1.25rem;
      box-shadow: 0 18px 45px rgba(17, 17, 17, 0.08);
      padding: clamp(1.5rem, 4vw, 2.75rem);
      margin-bottom: 2rem;
    }

    .begin-scoring-panel + .begin-scoring-panel {
      margin-top: 0.5rem;
    }

    .begin-scoring-panel h2 {
      margin-top: 0;
    }

    .begin-scoring-panel .lead {
      margin: 0 0 1.2rem;
    }

    .module-icon-grid {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 1rem;
      align-items: center;
      justify-items: center;
      padding-top: 0.35rem;
    }

    .module-icon-tile {
      width: 100%;
      display: grid;
      place-items: center;
      padding: 0.75rem 0.5rem;
      border-radius: 1rem;
      background: #fbfaf7;
      border: 1px solid #ece5d8;
    }

    .module-icon-link {
      text-decoration: none;
      color: inherit;
      display: grid;
      justify-items: center;
      width: 100%;
    }

    .module-icon-tile img {
      width: min(72px, 100%);
      height: auto;
      display: block;
    }

    .module-icon-label {
      margin-top: 0.65rem;
      text-align: center;
      font-size: 0.95rem;
      font-weight: 600;
      line-height: 1.3;
      color: #27211a;
    }

    .scoring-form-grid {
      display: grid;
      grid-template-columns: 500px auto;
      gap: 1rem 1.25rem;
      align-items: end;
      margin-bottom: 1.5rem;
      justify-content: start;
    }

    .scoring-form-grid .field {
      margin-bottom: 1.2rem;
      display: flex;
      flex-direction: column;
      min-width: 0;
      width: 500px;
      max-width: 100%;
    }

    .scoring-form-grid .field label {
      display: block;
      font-weight: 600;
      letter-spacing: 0.05em;
      margin-bottom: 0.4rem;
      color: #151515;
    }

    .scoring-form-grid select {
      width: 100%;
      max-width: 100%;
      display: block;
      position: static;
      padding: 0.85rem 0.95rem;
      border-radius: 0.85rem;
      border: 1px solid #e2ddd3;
      box-sizing: border-box;
      background: #fbfaf7;
      color: inherit;
      font-size: 1rem;
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }

    .scoring-form-grid select:focus {
      outline: none;
      border-color: #c6a764;
      box-shadow: 0 0 0 3px rgba(198, 167, 100, 0.25);
    }

    .scoring-form-grid select {
      appearance: none;
      background-image: linear-gradient(45deg, transparent 50%, #5f5f5f 50%),
        linear-gradient(135deg, #5f5f5f 50%, transparent 50%);
      background-position: calc(100% - 18px) calc(50% - 4px), calc(100% - 12px) calc(50% - 4px);
      background-size: 6px 6px;
      background-repeat: no-repeat;
    }

    .scoring-form-grid .action-field {
      margin-top: 0;
      padding-top: 1.95rem;
      display: flex;
      align-items: end;
      justify-content: flex-start;
      width: fit-content;
    }

    .scoring-form-grid .action-field .start-answers-btn {
      min-width: 214px;
      min-height: 60px;
    }

    @media (max-width: 960px) {
      .module-icon-grid {
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }

      .scoring-form-grid {
        grid-template-columns: 1fr;
      }

      .scoring-form-grid .action-field {
        margin-top: 0;
      }
    }

    @media (max-width: 640px) {
      .begin-scoring-panel {
        width: 100%;
        margin-top: 110px;
      }

      .module-icon-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .scoring-form-grid .action-field .start-answers-btn {
        width: 100%;
        min-width: 0;
      }
    }
  </style>

  <section class="card begin-scoring-panel">
    <h2>How to use this app</h2>
    <p class="lead">
      Enter your answers to any of the 12 SAT Math modules (provided below), and the app will generate a personalized score report showing your performance question by question, as well as by question type. Each report includes links to video explanations for every question and concept videos for each skill, making it easy to review mistakes and improve efficiently. Hasantutoring members will have access to explanations for all Questions and Question-Types. Non-members can see a limited number of Question-Types and answers to all Questions from Digital Paper Test 1 Module 1.
    </p>
  </section>

  <section class="card begin-scoring-panel">
    <h2>SAT Math Modules</h2>
    <div class="module-icon-grid">
      {% for test_number in range(1, 7) %}
        {% for module_number in range(1, 3) %}
        <div class="module-icon-tile">
          <a
            class="module-icon-link"
            href="https://www.hasantutoring.com/s/SAT-Test-{{ test_number }}-Module-{{ module_number }}.pdf"
            target="_blank"
            rel="noopener noreferrer"
          >
            <img src="{{ url_for('static', filename='pdf_icon.jpg') }}" alt="SAT math module PDF icon" />
            <div class="module-icon-label">Test {{ test_number }}, Module {{ module_number }}</div>
          </a>
        </div>
        {% endfor %}
      {% endfor %}
    </div>
  </section>

  <section class="card begin-scoring-panel">
    <h2>Begin scoring</h2>
    <p class="lead">
      Choose the test you would like to score. You'll enter the question responses on the next screen.
    </p>
    {% if tests %}
      <form method="post" action="{{ url_for('dashboard') }}" class="scoring-form-grid">
        <div class="field">
          <label for="test_id">Choose test</label>
          <select name="test_id" id="test_id">
            {% for test in tests %}
              <option value="{{ test.identifier }}" {% if test.identifier == selected_test_id %}selected{% endif %}>
                {{ test.name }}
              </option>
            {% endfor %}
          </select>
        </div>
        <div class="action-field">
          <div class="sqs-block" data-definition-name="website.components.button">
            <div class="sqs-block-content">
              <div class="sqs-block-button-container sqs-block-button-container--left">
                <div class="sqs-stretched">
                  <button type="submit" class="start-answers-btn btn btn--border theme-btn--primary-inverse sqs-button-element--tertiary">Start entering answers</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </form>
    {% else %}
      <p class="empty-state">No tests are currently available. Check the database connection and question records, then reload the page.</p>
    {% endif %}
  </section>
{% endblock %}
```

- [ ] **Step 2: Verify** — read the written file and confirm 3 panels are present and the form action is `url_for('dashboard')`.

- [ ] **Step 3: Commit**

```bash
cd "/Users/majidhasan/Documents/Hasan Tutoring/ClaudeWebApp"
git add templates/index.html
git commit -m "feat: replace dashboard index.html with SS_WebApp_Copy richer 3-panel version"
```

---

## Task 7: Replace templates/entry.html with SS_WebApp_Copy version (keeping student name fields)

**Files:** Modify `ClaudeWebApp/templates/entry.html`

SS_WebApp_Copy's entry.html lacks student name hidden fields. ClaudeWebApp's `results` route requires `first_name` and `last_name` in the POST body — keep those two hidden inputs. The "Choose a different test" footer link must point to `url_for('dashboard', ...)` with name params.

- [ ] **Step 1: Write the new entry.html**

```html
{% extends 'base.html' %}
{% block title %}Enter Answers · SAT Math Score Tool{% endblock %}
{% block content %}
  <style>
    .entry-scoring-panel {
      width: min(820px, 92vw);
      margin: clamp(110px, 13vh, 170px) auto 2rem;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 1.25rem;
      box-shadow: 0 18px 45px rgba(17, 17, 17, 0.08);
      padding: clamp(1.5rem, 4vw, 2.75rem);
      margin-bottom: 2rem;
    }

    @media (max-width: 640px) {
      .entry-scoring-panel {
        width: 100%;
      }
    }

    .form-actions {
      margin-top: 2rem;
      display: flex;
      justify-content: flex-start;
    }

    button,
    .button,
    .sqs-block-button-element {
      border: 1px solid #111;
      background: #111;
      color: #fff;
      padding: 0.85rem 2rem;
      border-radius: 999px;
      font-size: 0.95rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.18em;
      cursor: pointer;
      transition: background 0.2s ease, transform 0.2s ease, color 0.2s ease;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      min-height: 50px;
    }

    button:hover,
    .button:hover,
    .sqs-block-button-element:hover {
      background: #333;
      color: #fff;
      text-decoration: none;
    }

    button:active,
    .button:active,
    .sqs-block-button-element:active {
      transform: translateY(1px);
    }

    .answer-form {
      border: 1px solid var(--border);
      border-radius: 1rem;
      padding: 1.5rem;
      background: #fffefa;
    }

    @media (min-width: 1100px) {
      .answer-form {
        width: 65%;
        margin-left: auto;
        margin-right: auto;
      }
    }

    .table-wrapper {
      overflow-x: auto;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 480px;
      background: #fff;
      border-radius: 0.85rem;
      overflow: hidden;
      border: 1px solid var(--border);
    }

    table thead {
      background: #f5f1e9;
    }

    table th,
    table td {
      padding: 0.75rem 1rem;
      border-bottom: 1px solid var(--border);
      text-align: left;
    }

    .answer-table th,
    .answer-table td {
      padding: 0.65rem 0.6rem;
    }

    .answer-table th:first-child {
      width: 1%;
      white-space: nowrap;
    }

    .answer-table .choice-heading,
    .answer-table .choice-cell {
      text-align: center;
      padding-left: 0.35rem;
      padding-right: 0.35rem;
    }

    .answer-table .free-response-cell {
      padding: 0.75rem 1rem;
    }

    .free-response-input {
      width: min(220px, 100%);
      padding: 0.65rem 0.75rem;
      border-radius: 0.65rem;
      border: 1px solid var(--border);
      background: #fffefa;
      color: inherit;
    }

    .choice-label,
    .choice-cell label {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      column-gap: 0.35rem;
    }

    .choice-label input[type='radio'] {
      accent-color: var(--accent-muted);
    }

    .entry-footer-link {
      margin-top: 0.9rem;
      margin-bottom: 0;
      font-size: 1.1rem;
      font-weight: 700;
      text-align: left;
    }

    .entry-footer-link a {
      font-weight: 700;
    }

  </style>

  <section class="card entry-scoring-panel">
    <h2>Enter responses</h2>
    <p>
      Scoring {{ student_name or 'Student' }} for {{ test.name }}. Select the answer for each question below. Multiple-choice questions
      use options A–D, while grid-in questions accept a numeric response. Leave a question
      unanswered to mark it as omitted.
    </p>
    <form method="post" action="{{ url_for('results') }}" class="answer-form">
      <input type="hidden" name="test_id" value="{{ test.identifier }}" />
      <input type="hidden" name="first_name" value="{{ first_name }}" />
      <input type="hidden" name="last_name" value="{{ last_name }}" />
      <div class="table-wrapper">
        <table class="answer-table">
          <thead>
            <tr>
              <th scope="col">Question</th>
              {% for choice in multiple_choice_choices %}
                <th scope="col" class="choice-heading">{{ choice }}</th>
              {% endfor %}
            </tr>
          </thead>
          <tbody>
            {% for question in questions %}
              <tr>
                <th scope="row">{{ question.number }}</th>
                {% if question.expects_numeric_response %}
                  <td class="free-response-cell" colspan="{{ multiple_choice_choices|length }}">
                    <input
                      type="text"
                      name="q_{{ question.number }}"
                      id="q_{{ question.number }}"
                      inputmode="decimal"
                      autocomplete="off"
                      class="free-response-input"
                      placeholder="Enter answer"
                    />
                  </td>
                {% else %}
                  {% for choice in multiple_choice_choices %}
                    <td class="choice-cell">
                      <label class="choice-label" for="q_{{ question.number }}_{{ choice }}">
                        <input
                          type="radio"
                          name="q_{{ question.number }}"
                          id="q_{{ question.number }}_{{ choice }}"
                          value="{{ choice }}"
                        />
                      </label>
                    </td>
                  {% endfor %}
                {% endif %}
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      <div class="form-actions">
        <div class="sqs-block" data-definition-name="website.components.button">
          <div class="sqs-block-content">
            <div class="sqs-block-button-container sqs-block-button-container--center">
              <div class="sqs-stretched">
                <button type="submit" class="sqs-block-button-element">Generate score report</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </form>
    <p class="form-footer-note entry-footer-link">
      <a href="{{ url_for('dashboard', test_id=test.identifier, first_name=first_name, last_name=last_name) }}">Choose a different test</a>
    </p>
  </section>
{% endblock %}
```

- [ ] **Step 2: Verify** — confirm hidden fields for `first_name` and `last_name` are present, and the footer link uses `url_for('dashboard')`.

- [ ] **Step 3: Commit**

```bash
cd "/Users/majidhasan/Documents/Hasan Tutoring/ClaudeWebApp"
git add templates/entry.html
git commit -m "feat: replace entry.html with SS_WebApp_Copy version (retaining student name fields)"
```

---

## Task 8: Replace templates/results.html with SS_WebApp_Copy version

**Files:** Modify `ClaudeWebApp/templates/results.html`

SS_WebApp_Copy's results.html adds:
- Pie chart of missed questions by type (SVG, with interactive tooltip)
- Video links on question-number cells and question-type cells
- Hotspot overlay tips (dismissable)
- Richer score report header layout (two-column with chart)

Two adjustments for ClaudeWebApp:
1. Heading uses `student_name`: `<h2><strong>Score Report for {{ student_name }}</strong></h2>`
2. "Score Another Test" href → `url_for('dashboard', test_id=test_id, first_name=first_name, last_name=last_name)`

The `results` route already passes `student_name`, `first_name`, `last_name`, and `test_id` to the template — no route changes needed.

- [ ] **Step 1: Write the new results.html**

Copy the full content of `SS_WebApp_Copy/templates/results.html` and apply the two adjustments:

Change:
```html
        <h2><strong>Score Report</strong></h2>
```
to:
```html
        <h2><strong>Score Report for {{ student_name }}</strong></h2>
```

Change the "Score Another Test" anchor href from:
```
url_for('index', test_id=test_id)
```
to:
```
url_for('dashboard', test_id=test_id, first_name=first_name, last_name=last_name)
```

Keep all pie chart JS, hotspot JS, video link logic, and CSS intact from the SS_WebApp_Copy source.

- [ ] **Step 2: Verify the written file**
  - `student_name` appears in the `<h2>` heading
  - `url_for('dashboard', test_id=test_id, first_name=first_name, last_name=last_name)` is in the "Score Another Test" link
  - `category_video_url` is referenced in the question table rows and category breakdown rows
  - **No `url_for('index')` calls exist** — grep for `url_for('index'` in the file to confirm zero matches

- [ ] **Step 3: Commit**

```bash
cd "/Users/majidhasan/Documents/Hasan Tutoring/ClaudeWebApp"
git add templates/results.html
git commit -m "feat: replace results.html with SS_WebApp_Copy richer version (pie chart + video links)"
```

---

## Task 9: Smoke-test the integrated app

**Files:** No changes — verification only.

- [ ] **Step 1: Start the app**

```bash
cd "/Users/majidhasan/Documents/Hasan Tutoring/ClaudeWebApp"
source .venv/bin/activate
flask --app app run --debug
```

- [ ] **Step 2: Check `/dashboard`** — should show 3 panels: How to use, SAT Math Modules (12 PDF tiles), Begin scoring form with test dropdown.

- [ ] **Step 3: Select a test and click "Start entering answers"** — should redirect to `/entry` with student name pre-filled in the page text.

- [ ] **Step 4: Submit answers** — should render `/results` with:
  - Student name in the heading ("Score Report for ...")
  - Pie chart of missed questions by type
  - Question table with clickable question numbers (linking to hasantutoring.com)
  - Question-Type column with optional video links
  - "Score Another Test" button linking back to `/dashboard`

- [ ] **Step 5: Check auth flow** — logout → login → confirm onboarding still works → confirm redirect to dashboard shows new 3-panel layout.

- [ ] **Step 6: If any errors, common causes**
  - `QType_Vids` table missing in WebApp DB → `_load_question_type_video_lookup` logs a warning and returns `{}` — app still works, video links just won't appear. Confirm table exists with `\dt` in psql.
  - `pdf_icon.jpg` 404 → re-check Task 5 copy step
  - Template `UndefinedError` on `category_video_url` → Task 2 (Question dataclass field) was not applied correctly

---

## Scope Notes

- **`base.html` header is not touched** — Auth0 login/logout/signup buttons remain as-is.
- **`_persist_student_and_responses()`** uses `DB_CONFIG` — student response history preserved.
- **`_persist_submission()`** uses `DB_CONFIG` — submission log preserved.
- **No new DB connection** — everything uses the existing `WebApp` DB via `DB_CONFIG`.
- **SS_WebApp_Copy's CSV fallback** is not ported — ClaudeWebApp is DB-only.
- **SS_WebApp_Copy's `/ss_homepage` route** is not ported — not needed.
