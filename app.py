from __future__ import annotations

import json
import math
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode

import html as html_module

import boto3
import psycopg2
import resend
from psycopg2 import sql
from authlib.integrations.flask_client import OAuth
from flask_shell_config import create_shell_config
from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from flask_session import Session
from dotenv import load_dotenv


load_dotenv()


DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", "5432")),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "dbname": os.environ.get("DB_NAME", "WebApp"),
}
MULTIPLE_CHOICE_CHOICES = ("A", "B", "C", "D")
DEFAULT_R2_QUESTION_IMAGE_KEY_TEMPLATE = "{section_id}_{test_id}_{module_id}_{question_number}.png"
_R2_CLIENT_CACHE = {}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


R2_PRESIGNED_URL_SECONDS = _int_env("R2_PRESIGNED_URL_SECONDS", 3600)


@dataclass
class Question:
    number: int
    correct_answers: List[str]
    category: str
    expects_numeric_response: bool
    db_question_id: Optional[int] = None
    category_video_url: Optional[str] = None

    @property
    def display_correct_answer(self) -> str:
        if not self.correct_answers:
            return ""
        if len(self.correct_answers) == 1:
            return self.correct_answers[0]
        return " or ".join(self.correct_answers)


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "FLASK_SECRET_KEY",
    os.environ.get("AUTH0_SECRET", "dev-secret-change-me"),
)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "").strip()
AUTH0_CLIENT_ID = os.environ.get("AUTH0_CLIENT_ID", "").strip()
AUTH0_CLIENT_SECRET = os.environ.get("AUTH0_SECRET", "").strip()
AUTH0_REDIRECT_URI = os.environ.get("AUTH0_REDIRECT_URI", "").strip()
AUTH0_LOGOUT_RETURN_TO = os.environ.get(
    "AUTH0_LOGOUT_RETURN_TO",
    "http://localhost:5000/",
).strip()

oauth = OAuth(app)
if AUTH0_DOMAIN and AUTH0_CLIENT_ID and AUTH0_CLIENT_SECRET:
    oauth.register(
        "auth0",
        client_id=AUTH0_CLIENT_ID,
        client_secret=AUTH0_CLIENT_SECRET,
        client_kwargs={"scope": "openid profile email"},
        server_metadata_url=f"https://{AUTH0_DOMAIN}/.well-known/openid-configuration",
    )


@dataclass(frozen=True)
class DatabaseTestMetadata:
    test_id: int
    section_id: int
    module_id: int


@dataclass(frozen=True)
class TestDefinition:
    identifier: str
    name: str
    source: str
    db_metadata: Optional[DatabaseTestMetadata] = None


_TEST_NUMBER_PATTERN = re.compile(r"(?:test|t)\s*[_\-\s]?(\d+)", re.IGNORECASE)
_MODULE_NUMBER_PATTERN = re.compile(r"(?:module|m)\s*[_\-\s]?(\d+)", re.IGNORECASE)
def _extract_test_module_numbers(test: TestDefinition) -> Tuple[Optional[str], Optional[str]]:
    test_number: Optional[str] = None
    module_number: Optional[str] = None
    for source in (test.name, test.identifier):
        if not source:
            continue
        if test_number is None:
            match = _TEST_NUMBER_PATTERN.search(source)
            if match:
                test_number = match.group(1)
        if module_number is None:
            match = _MODULE_NUMBER_PATTERN.search(source)
            if match:
                module_number = match.group(1)
    return test_number, module_number


def _build_question_link_prefix(test: TestDefinition) -> Optional[str]:
    test_number, module_number = _extract_test_module_numbers(test)
    if not test_number or not module_number:
        return None
    return f"https://www.hasantutoring.com/math-test-{test_number}-module-{module_number}/v/question"


def _r2_config() -> Optional[Dict[str, str]]:
    config = {
        "account_id": os.environ.get("R2_ACCOUNT_ID", "").strip(),
        "access_key_id": os.environ.get("R2_ACCESS_KEY_ID", "").strip(),
        "secret_access_key": os.environ.get("R2_SECRET_ACCESS_KEY", "").strip(),
        "bucket": os.environ.get("R2_BUCKET", "").strip(),
    }
    if all(config.values()):
        return config
    if any(config.values()):
        app.logger.warning("R2 is partially configured; falling back to local question placeholder images.")
    return None


def _r2_client(config: Dict[str, str]):
    cache_key = (
        config["account_id"],
        config["access_key_id"],
        config["secret_access_key"],
    )
    if cache_key not in _R2_CLIENT_CACHE:
        _R2_CLIENT_CACHE[cache_key] = boto3.client(
            "s3",
            endpoint_url=f"https://{config['account_id']}.r2.cloudflarestorage.com",
            aws_access_key_id=config["access_key_id"],
            aws_secret_access_key=config["secret_access_key"],
            region_name="auto",
        )
    return _R2_CLIENT_CACHE[cache_key]


def _build_question_image_key(test: TestDefinition, question: Question) -> Optional[str]:
    if test.db_metadata is None:
        return None

    template = os.environ.get(
        "R2_QUESTION_IMAGE_KEY_TEMPLATE",
        DEFAULT_R2_QUESTION_IMAGE_KEY_TEMPLATE,
    ).strip()
    try:
        return template.format(
            test_id=test.db_metadata.test_id,
            section_id=test.db_metadata.section_id,
            module_id=test.db_metadata.module_id,
            question_number=question.number,
            question_id=question.db_question_id or "",
        ).lstrip("/")
    except KeyError as exc:
        app.logger.warning("Invalid R2_QUESTION_IMAGE_KEY_TEMPLATE placeholder: %s", exc)
        return None


def _build_question_image_url(test: TestDefinition, question: Question) -> str:
    placeholder_url = url_for("test_question_placeholder")
    config = _r2_config()
    if config is None:
        return placeholder_url

    image_key = _build_question_image_key(test, question)
    if not image_key:
        return placeholder_url

    try:
        return _r2_client(config).generate_presigned_url(
            "get_object",
            Params={"Bucket": config["bucket"], "Key": image_key},
            ExpiresIn=R2_PRESIGNED_URL_SECONDS,
        )
    except Exception as exc:
        app.logger.warning("Failed to generate R2 question image URL for %s: %s", image_key, exc)
        return placeholder_url


class QuestionBank:
    """Utility responsible for loading and caching questions for each test."""

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

    def available_tests(self) -> List[TestDefinition]:
        return self._available_database_tests()

    def _available_database_tests(self) -> List[TestDefinition]:
        tests: List[TestDefinition] = []

        try:
            with psycopg2.connect(**DB_CONFIG) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT DISTINCT
                            q.test_id,
                            t.name,
                            q.section_id,
                            s.name,
                            q.module_id,
                            m.name
                        FROM questions q
                        JOIN tests t ON q.test_id = t.id
                        JOIN sections s ON q.section_id = s.id
                        JOIN modules m ON q.module_id = m.id
                        ORDER BY t.name, s.name, m.name, q.test_id, q.section_id, q.module_id
                        """
                    )
                    for row in cursor.fetchall():
                        test_id, test_name, section_id, section_name, module_id, module_name = row
                        identifier = f"db_{test_id}_{section_id}_{module_id}"
                        display_name = f"{test_name} {section_name} {module_name}"
                        tests.append(
                            TestDefinition(
                                identifier=identifier,
                                name=display_name,
                                source="database",
                                db_metadata=DatabaseTestMetadata(
                                    test_id=test_id,
                                    section_id=section_id,
                                    module_id=module_id,
                                ),
                            )
                        )
        except psycopg2.Error as exc:
            app.logger.warning("Failed to load database tests: %s", exc)

        return tests

    def get_test(self, test_id: str) -> TestDefinition:
        for test in self.available_tests():
            if test.identifier == test_id:
                return test
        raise ValueError(f"Unknown test identifier: {test_id}")

    def questions_for(self, test_id: str) -> List[Question]:
        if test_id in self._questions_cache:
            return self._questions_cache[test_id]

        test = self.get_test(test_id)
        if not test.db_metadata:
            raise ValueError(f"Test '{test.identifier}' is missing database metadata.")
        questions = self._load_database_questions(test.db_metadata)
        self._questions_cache[test_id] = questions
        return questions

    def _load_database_questions(self, metadata: DatabaseTestMetadata) -> List[Question]:
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

        questions: List[Question] = []
        try:
            with psycopg2.connect(**DB_CONFIG) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        query,
                        (
                            metadata.test_id,
                            metadata.section_id,
                            metadata.module_id,
                        ),
                    )
                    rows = cursor.fetchall()
        except psycopg2.Error as exc:
            raise RuntimeError(f"Failed to load questions from database: {exc}") from exc

        if not rows:
            raise ValueError("No questions were found for the selected database test.")

        for test_question_number, correct_answer, category_name, question_id, question_type_id in rows:
            if test_question_number is None:
                raise ValueError("Each database question must include a test_question_number.")

            answers, expects_numeric_response = _normalize_answers((correct_answer or "").strip())
            if not answers:
                raise ValueError(
                    f"Question {test_question_number} is missing a 'correct_answer' entry."
                )

            if not category_name:
                raise ValueError(
                    f"Question {test_question_number} is missing a linked question type."
                )

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

        questions.sort(key=lambda q: q.number)
        return questions



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


def _normalize_answers(raw_answer: str) -> Tuple[List[str], bool]:
    tokens = [token.strip() for token in raw_answer.split(";")]
    tokens = [token for token in tokens if token]

    if not tokens:
        return [], False

    expects_numeric = all(_is_numeric_token(token) for token in tokens)

    if expects_numeric:
        normalized = [_normalize_numeric_token(token) for token in tokens]
    else:
        normalized = [token.upper() for token in tokens]

    deduped: List[str] = []
    seen = set()
    for answer in normalized:
        if answer not in seen:
            seen.add(answer)
            deduped.append(answer)

    return deduped, expects_numeric


def _normalize_numeric_token(value: str) -> str:
    return value.strip()


def _is_numeric_token(value: str) -> bool:
    if value is None:
        return False

    trimmed = str(value).strip()
    if not trimmed:
        return False

    signless = trimmed.lstrip("+-").strip()
    if not signless:
        return False

    if " " in signless:
        parts = [part for part in signless.split() if part]
        if len(parts) == 2 and _is_decimal_string(parts[0]) and _is_fraction_string(parts[1]):
            return True
        return False

    if "/" in signless:
        return _is_fraction_string(signless)

    return _is_decimal_string(signless)


def _is_decimal_string(value: str) -> bool:
    candidate = value.strip()
    if not candidate:
        return False

    try:
        Decimal(candidate)
    except (InvalidOperation, ValueError):
        return False

    return True


def _is_fraction_string(value: str) -> bool:
    parts = value.split("/")
    if len(parts) != 2:
        return False

    numerator, denominator = (part.strip() for part in parts)
    if not numerator or not denominator:
        return False

    if not _is_decimal_string(numerator):
        return False

    if not _is_decimal_string(denominator):
        return False

    try:
        return Decimal(denominator) != 0
    except (InvalidOperation, ValueError):
        return False


def _normalize_category_key(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return cleaned
    try:
        return str(int(cleaned))
    except ValueError:
        return cleaned


question_bank = QuestionBank()


def _compose_student_name(first_name: str, last_name: str) -> str:
    first = (first_name or "").strip()
    last = (last_name or "").strip()
    if first and last:
        return f"{first} {last}"
    return first or last or "Student"


def _persist_submission(
    *,
    test: TestDefinition,
    student_name: str,
    answers: Dict[int, str],
    report,
) -> None:
    payload_answers = json.dumps(answers)
    payload_report = json.dumps(report)
    payload_categories = json.dumps(report.get("category_breakdown", []))
    created_at = datetime.utcnow()

    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO submissions (
                        test_code,
                        student_name,
                        answers_json,
                        results_json,
                        category_json,
                        raw_correct,
                        raw_total,
                        scaled_score,
                        created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        test.identifier,
                        student_name or "Student",
                        payload_answers,
                        payload_report,
                        payload_categories,
                        report.get("correct_count", 0),
                        report.get("total_questions", 0),
                        report.get("scaled_score", 200),
                        created_at,
                    ),
                )
    except psycopg2.Error as exc:
        app.logger.warning("Failed to persist submission to Postgres: %s", exc)


def _next_table_id(cursor, table_name: str) -> int:
    query = sql.SQL("SELECT COALESCE(MAX(id), 0) + 1 FROM {}").format(sql.Identifier(table_name))
    cursor.execute(query)
    row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"Unable to compute next id for table '{table_name}'.")
    return int(row[0])


def _find_student_id(cursor, first_name: str, last_name: str) -> Optional[int]:
    cursor.execute(
        """
        SELECT id
        FROM students
        WHERE LOWER(first_name) = LOWER(%s) AND LOWER(last_name) = LOWER(%s)
        ORDER BY id
        LIMIT 1
        """,
        (first_name, last_name),
    )
    row = cursor.fetchone()
    return int(row[0]) if row else None


def _persist_student_and_responses(
    *,
    first_name: str,
    last_name: str,
    test: TestDefinition,
    questions: List[Question],
    answers: Dict[int, str],
) -> None:
    first = (first_name or "").strip()
    last = (last_name or "").strip()
    if not first or not last:
        return

    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                student_id = _find_student_id(cursor, first, last)
                if student_id is None:
                    app.logger.warning(
                        "Skipping response persistence because no student row exists for '%s %s'.",
                        first,
                        last,
                    )
                    return

                metadata = test.db_metadata
                if metadata:
                    next_response_id = _next_table_id(cursor, "responses")
                    for question in questions:
                        if question.db_question_id is None:
                            continue
                        cursor.execute(
                            """
                            INSERT INTO responses (
                                id,
                                student_id,
                                test_id,
                                section_id,
                                module_id,
                                test_question_number_id,
                                responses
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                next_response_id,
                                student_id,
                                metadata.test_id,
                                metadata.section_id,
                                metadata.module_id,
                                question.db_question_id,
                                answers.get(question.number, ""),
                            ),
                        )
                        next_response_id += 1

            conn.commit()
    except psycopg2.Error as exc:
        app.logger.warning("Failed to persist student/responses: %s", exc)


def _is_authenticated() -> bool:
    return bool(session.get("user"))


def _login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not _is_authenticated():
            return redirect(url_for("signup"))
        return view_func(*args, **kwargs)

    return wrapped_view


def _auth0_client():
    client = getattr(oauth, "auth0", None)
    if client is None:
        abort(500, description="Auth0 is not configured.")
    return client


# Keyed by state value → Authlib state_data dict.
# Needed because Chrome's schemeful SameSite policy blocks cookies when
# Auth0 (HTTPS) redirects back to localhost (HTTP), so the session cookie
# is never sent on the callback request.
_oauth_state_store: Dict[str, dict] = {}


def _backup_oauth_states() -> None:
    """Copy any _state_auth0_* keys from the session to the in-memory store."""
    prefix = "_state_auth0_"
    for key, value in list(session.items()):
        if key.startswith(prefix):
            _oauth_state_store[key[len(prefix):]] = value


def _restore_oauth_state(state: str) -> None:
    """If the session lacks a state key, restore it from the in-memory store."""
    key = f"_state_auth0_{state}"
    if key not in session and state in _oauth_state_store:
        session[key] = _oauth_state_store.pop(state)


def _build_auth0_authorize_url(*, screen_hint: Optional[str] = None) -> str:
    query = {
        "client_id": AUTH0_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": AUTH0_REDIRECT_URI or url_for("auth_callback", _external=True),
        "scope": "openid profile email",
    }
    if screen_hint:
        query["screen_hint"] = screen_hint
    return f"https://{AUTH0_DOMAIN}/authorize?{urlencode(query)}"


def _get_student_name() -> Tuple[str, str]:
    """Return (first_name, last_name) for the logged-in user from the DB."""
    user = session.get("user", {})
    user_id = user.get("user_id")
    if not user_id:
        return "", ""
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT first_name, last_name FROM students WHERE user_id = %s LIMIT 1",
                    (user_id,),
                )
                row = cursor.fetchone()
                if row:
                    return row[0], row[1]
    except psycopg2.Error:
        pass
    return "", ""


def _render_test_selection_page(template_name: str):
    tests = question_bank.available_tests()
    selected_test_id = tests[0].identifier if tests else None
    first_name = request.args.get("first_name", "").strip()
    last_name = request.args.get("last_name", "").strip()
    if not first_name and not last_name:
        first_name, last_name = _get_student_name()

    if request.method == "POST":
        if not tests:
            abort(400, description="No test files are available to score.")

        test_id = request.form.get("test_id", "").strip() or selected_test_id
        try:
            question_bank.get_test(test_id)
            selected_test_id = test_id
        except ValueError:
            selected_test_id = tests[0].identifier

        posted_first_name = request.form.get("first_name", "").strip()
        posted_last_name = request.form.get("last_name", "").strip()
        if posted_first_name or posted_last_name:
            first_name = posted_first_name
            last_name = posted_last_name
        if not first_name or not last_name:
            abort(400, description="First and last name are required before entering answers.")

        return redirect(
            url_for(
                "entry",
                test_id=selected_test_id,
                first_name=first_name,
                last_name=last_name,
            )
        )

    if request.method == "GET" and tests:
        requested_test = request.args.get("test_id", "").strip()
        if requested_test:
            try:
                question_bank.get_test(requested_test)
                selected_test_id = requested_test
            except ValueError:
                pass

    return render_template(
        template_name,
        tests=tests,
        selected_test_id=selected_test_id,
        first_name=first_name,
        last_name=last_name,
    )


def _render_auth_page(template_name: str):
    if _is_authenticated():
        return redirect(url_for("dashboard"))
    return render_template(template_name)


@app.get("/")
def root():
    return _render_test_selection_page("index.html")


@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    return _render_test_selection_page("index.html")


@app.get("/signup")
def signup():
    return _render_auth_page("signup.html")


@app.get("/logout")
def logout():
    session.clear()
    query = urlencode(
        {
            "client_id": AUTH0_CLIENT_ID,
            "returnTo": AUTH0_LOGOUT_RETURN_TO,
        }
    )
    return redirect(f"https://{AUTH0_DOMAIN}/v2/logout?{query}")


@app.get("/auth/login")
def auth_login():
    resp = _auth0_client().authorize_redirect(
        redirect_uri=AUTH0_REDIRECT_URI or url_for("auth_callback", _external=True),
    )
    _backup_oauth_states()
    return resp


@app.get("/auth/signup")
def auth_signup():
    resp = _auth0_client().authorize_redirect(
        redirect_uri=AUTH0_REDIRECT_URI or url_for("auth_callback", _external=True),
        screen_hint="signup",
    )
    _backup_oauth_states()
    return resp


@app.get("/auth/callback")
def auth_callback():
    state = request.args.get("state", "")
    _restore_oauth_state(state)
    token = _auth0_client().authorize_access_token()
    userinfo = token.get("userinfo")
    if not userinfo:
        userinfo = _auth0_client().userinfo()

    auth0_user_id = userinfo["sub"]
    email = userinfo.get("email", "")
    email_verified = bool(userinfo.get("email_verified", False))

    has_student = False
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

                user_data = {
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

    session["user"] = user_data

    if has_student:
        return redirect(url_for("dashboard"))
    return redirect(url_for("onboarding"))


@app.get("/entry")
def entry():
    test_id = request.args.get("test_id", "").strip()
    first_name = request.args.get("first_name", "").strip()
    last_name = request.args.get("last_name", "").strip()
    student_name = _compose_student_name(first_name, last_name)

    if not test_id:
        abort(400, description="A test must be selected before entering answers.")

    try:
        test = question_bank.get_test(test_id)
    except ValueError as exc:
        abort(400, description=str(exc))

    questions = question_bank.questions_for(test_id)

    return render_template(
        "entry.html",
        test=test,
        student_name=student_name,
        first_name=first_name,
        last_name=last_name,
        questions=questions,
        multiple_choice_choices=MULTIPLE_CHOICE_CHOICES,
    )


@app.get("/test-question-placeholder.png")
def test_question_placeholder():
    return send_file(os.path.join(app.root_path, "1,1,1,1.png"), mimetype="image/png")


@app.route("/test", methods=["GET", "POST"])
def test():
    test_id = request.values.get("test_id", "").strip()
    first_name = request.values.get("first_name", "").strip()
    last_name = request.values.get("last_name", "").strip()
    student_name = _compose_student_name(first_name, last_name)

    if not test_id:
        abort(400, description="A test must be selected before starting the test.")

    if not first_name or not last_name:
        abort(400, description="First and last name are required before starting the test.")

    try:
        selected_test = question_bank.get_test(test_id)
    except ValueError as exc:
        abort(400, description=str(exc))

    questions = question_bank.questions_for(test_id)
    test_number, module_number = _extract_test_module_numbers(selected_test)
    question_image_urls = {
        question.number: _build_question_image_url(selected_test, question)
        for question in questions
    }

    return render_template(
        "test.html",
        test=selected_test,
        test_number=test_number,
        module_number=module_number,
        student_name=student_name,
        first_name=first_name,
        last_name=last_name,
        questions=questions,
        question_image_urls=question_image_urls,
        multiple_choice_choices=MULTIPLE_CHOICE_CHOICES,
    )


@app.post("/results")
def results():
    test_id = request.form.get("test_id", "").strip()
    if not test_id:
        abort(400, description="A test must be selected to score responses.")

    try:
        test = question_bank.get_test(test_id)
    except ValueError as exc:
        abort(400, description=str(exc))

    questions = question_bank.questions_for(test_id)
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    if not first_name or not last_name:
        abort(400, description="First and last name are required to score a student.")
    student_name = _compose_student_name(first_name, last_name)

    answers: Dict[int, str] = {}
    for question in questions:
        answer = request.form.get(f"q_{question.number}", "").strip()
        if not question.expects_numeric_response:
            answer = answer.upper()
        answers[question.number] = answer

    report = build_score_report(answers, questions)

    if _is_authenticated():
        _persist_student_and_responses(
            first_name=first_name,
            last_name=last_name,
            test=test,
            questions=questions,
            answers=answers,
        )
        _persist_submission(test=test, student_name=student_name, answers=answers, report=report)

    return render_template(
        "results.html",
        student_name=student_name,
        test_id=test.identifier,
        test_name=test.name,
        report=report,
        first_name=first_name,
        last_name=last_name,
        question_link_prefix=_build_question_link_prefix(test),
    )


@app.get("/onboarding")
@_login_required
def onboarding():
    return render_template("onboarding.html", first_name="", last_name="")


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
        return render_template("onboarding.html", first_name=first_name, last_name=last_name)

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
        return render_template("onboarding.html", first_name=first_name, last_name=last_name)

    return redirect(url_for("dashboard"))


@app.context_processor
def inject_globals():
    return {
        "current_year": datetime.utcnow().year,
        "current_user": session.get("user"),
        "is_authenticated": _is_authenticated(),
        "auth0_login_url": _build_auth0_authorize_url(),
        "auth0_signup_url": _build_auth0_authorize_url(screen_hint="signup"),
        "shell": create_shell_config({
            "favicon": url_for("static", filename="favicon.png"),
            "site_title": "SAT Math Score Tool",
        }),
    }


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "GET":
        return render_template("contact.html", success=False, error=None, values=None)

    # --- POST ---
    first_name = request.form.get("first_name", "").strip()
    last_name  = request.form.get("last_name",  "").strip()
    email      = request.form.get("email",      "").strip()
    subject    = request.form.get("subject",    "").strip()
    message    = request.form.get("message",    "").strip()

    values = {
        "first_name": first_name,
        "last_name":  last_name,
        "email":      email,
        "subject":    subject,
        "message":    message,
    }

    if not first_name or not email or not message:
        return render_template(
            "contact.html",
            success=False,
            error="Please fill in all required fields.",
            values=values,
        )

    try:
        resend.api_key = os.environ.get("RESEND_API_KEY")

        # TODO: Replace the "from" address with
        #   "HasanTutoring Contact <contact@hasantutoring.com>"
        # once hasantutoring.com is verified in the Resend dashboard.
        # Until then, Resend's sandbox sender is used.
        params = {
            "from":     "onboarding@resend.dev",
            "to":       ["a.majid.hasan@gmail.com"],
            "reply_to": email,
            "subject":  f"[HasanTutoring.com] {subject or 'New message'}",
            "html": (
                f"<p><strong>From:</strong> {html_module.escape(first_name)} "
                f"{html_module.escape(last_name)}</p>"
                f"<p><strong>Email:</strong> {html_module.escape(email)}</p>"
                f"<p><strong>Subject:</strong> {html_module.escape(subject)}</p>"
                f"<hr>"
                f"<p>{html_module.escape(message).replace(chr(10), '<br>')}</p>"
            ),
        }
        resend.Emails.send(params)
    except Exception as exc:
        app.logger.error("Resend error on /contact POST: %s", exc)
        return render_template(
            "contact.html",
            success=False,
            error="Something went wrong. Please try again or email Majid@HasanTutoring.com directly.",
            values=values,
        )

    return render_template("contact.html", success=True, error=None, values=None)


if __name__ == "__main__":
    app.run(debug=True)
