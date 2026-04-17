import pytest
from unittest.mock import Mock, patch
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


def test_root_accessible_without_login(client):
    with patch.object(app_module.question_bank, "available_tests", return_value=[MOCK_TEST]):
        response = client.get("/")
    assert response.status_code == 200


def test_dashboard_accessible_without_login(client):
    with patch.object(app_module.question_bank, "available_tests", return_value=[MOCK_TEST]):
        response = client.get("/dashboard")
    assert response.status_code == 200
    assert b'formaction="/test"' in response.data


def test_dashboard_post_redirects_to_entry_with_submitted_name(client):
    with patch.object(app_module.question_bank, "available_tests", return_value=[MOCK_TEST]), \
         patch.object(app_module.question_bank, "get_test", return_value=MOCK_TEST):
        response = client.post("/dashboard", data={
            "test_id": "db_1_1_1",
            "first_name": "Jane",
            "last_name": "Doe",
        })
    assert response.status_code == 302
    assert response.headers["Location"] == "/entry?test_id=db_1_1_1&first_name=Jane&last_name=Doe"


def test_test_mode_accessible_without_login(client):
    with patch.dict(app_module.os.environ, {
            "R2_ACCOUNT_ID": "",
            "R2_ACCESS_KEY_ID": "",
            "R2_SECRET_ACCESS_KEY": "",
            "R2_BUCKET": "",
        }), \
         patch.object(app_module.question_bank, "get_test", return_value=MOCK_TEST), \
         patch.object(app_module.question_bank, "questions_for", return_value=MOCK_QUESTIONS):
        response = client.get(
            "/test?test_id=db_1_1_1&first_name=Jane&last_name=Doe"
        )
    assert response.status_code == 200
    assert b"Test 1" in response.data
    assert b"Module 1" in response.data
    assert b'name="q_1"' in response.data
    assert b'name="q_2"' in response.data
    assert b"/test-question-placeholder.png" in response.data
    assert b"Generate score report" in response.data


def test_test_mode_uses_r2_presigned_question_images(client):
    mock_r2_client = Mock()
    mock_r2_client.generate_presigned_url.side_effect = [
        "https://r2.example/question-1.png?signature=abc",
        "https://r2.example/question-2.png?signature=def",
    ]

    with patch.dict(app_module.os.environ, {
            "R2_ACCOUNT_ID": "account-id",
            "R2_ACCESS_KEY_ID": "access-key",
            "R2_SECRET_ACCESS_KEY": "secret-key",
            "R2_BUCKET": "mathpapertestimages",
        }), \
         patch.object(app_module, "_r2_client", return_value=mock_r2_client), \
         patch.object(app_module.question_bank, "get_test", return_value=MOCK_TEST), \
         patch.object(app_module.question_bank, "questions_for", return_value=MOCK_QUESTIONS):
        response = client.get(
            "/test?test_id=db_1_1_1&first_name=Jane&last_name=Doe"
        )

    assert response.status_code == 200
    assert b"https://r2.example/question-1.png?signature=abc" in response.data
    assert b"https://r2.example/question-2.png?signature=def" in response.data
    mock_r2_client.generate_presigned_url.assert_any_call(
        "get_object",
        Params={"Bucket": "mathpapertestimages", "Key": "1_1_1_1.png"},
        ExpiresIn=app_module.R2_PRESIGNED_URL_SECONDS,
    )
    mock_r2_client.generate_presigned_url.assert_any_call(
        "get_object",
        Params={"Bucket": "mathpapertestimages", "Key": "1_1_1_2.png"},
        ExpiresIn=app_module.R2_PRESIGNED_URL_SECONDS,
    )


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
