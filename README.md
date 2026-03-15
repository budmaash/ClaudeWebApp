# SAT Math Score Tool

This project provides a lightweight web application for entering student responses to SAT Math practice tests and instantly generating a detailed score report. The tool highlights correct and incorrect answers and aggregates performance by College Board skill categories.

## Features

- Start by selecting the test and entering the student's first and last name, then record answers using a multiple-choice or numeric-entry web form
- Handle grid-in questions with alternate numeric answers (e.g. `5;5.0`)
- Instant score report with estimated scaled SAT Math score
- Category breakdown driven by `question_types` in the database
- Quickly rescore another student without reloading the page
- Score reports and responses are persisted to the database for external analytics

## Project structure

```
.
├── app.py                # Flask application with scoring logic
├── static/
│   └── styles.css        # Styling for the UI
└── templates/
    ├── base.html         # Shared layout
    ├── index.html        # Test and student selector
    ├── entry.html        # Answer entry form
    └── results.html      # Score report view
```

## Getting started

1. **Install dependencies**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure the database** (see below)

3. **Run the development server**

   ```bash
   flask --app app run --debug
   ```

4. **Open the app**

   Visit <http://127.0.0.1:5000> in your browser.

## Database setup

The app requires a PostgreSQL database. All question data, test definitions, and results are read from and written to the database.

Set connection details via environment variables (or a `.env` file):

| Variable | Default | Description |
|---|---|---|
| `DB_HOST` | `localhost` | Postgres host |
| `DB_PORT` | `5432` | Postgres port |
| `DB_NAME` | `WebApp` | Database name |
| `DB_USER` | `postgres` | Database user |
| `DB_PASSWORD` | *(none)* | Database password |

### Expected schema

The app reads from the following tables:

```sql
-- Test hierarchy
tests    (id, name)
sections (id, name)
modules  (id, name)

-- Questions
questions (id, test_id, section_id, module_id, test_question_number, correct_answer, question_type_id)
question_types (id, name)

-- Students roster (looked up by first/last name)
students (id, first_name, last_name)
```

And writes to:

```sql
-- Full submission record with scoring
CREATE TABLE IF NOT EXISTS submissions (
  id SERIAL PRIMARY KEY,
  test_code TEXT NOT NULL,
  student_name TEXT NOT NULL,
  answers_json JSONB NOT NULL,
  results_json JSONB NOT NULL,
  category_json JSONB NOT NULL,
  raw_correct INTEGER NOT NULL,
  raw_total INTEGER NOT NULL,
  scaled_score INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_submissions_test_code ON submissions (test_code);

-- Per-question responses
CREATE TABLE IF NOT EXISTS responses (
  id INTEGER PRIMARY KEY,
  student_id INTEGER NOT NULL REFERENCES students(id),
  test_id INTEGER NOT NULL,
  section_id INTEGER NOT NULL,
  module_id INTEGER NOT NULL,
  test_question_number_id INTEGER NOT NULL REFERENCES questions(id),
  responses TEXT
);
```

### How tests are discovered

Each distinct `(test_id, section_id, module_id)` combination present in the `questions` table is surfaced as a selectable test in the UI. The display name is assembled from the corresponding `tests`, `sections`, and `modules` rows (e.g. `Digital Paper Test 1 Math Module 1`).

## How scoring works

- Accuracy is calculated as the percentage of correct responses.
- The SAT Math scaled score is estimated using a simple linear mapping between the raw score and the 200–800 scale. Replace the `build_score_report` helper in `app.py` if you have a more precise conversion chart.
