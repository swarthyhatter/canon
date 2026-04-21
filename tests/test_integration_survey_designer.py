"""
Integration tests for SurveyDesigner.
Hits the live Bonfires agent — requires a populated .env file.
"""
import pytest
from dotenv import load_dotenv

load_dotenv()

from bonfires import BonfiresClient
from harmonica.client import HarmonicaClient
from agent.survey_designer import SurveyDesigner
import store.db as db


REQUIRED_KEYS = ("topic", "goal", "prompt", "questions", "cross_pollination")


@pytest.fixture(scope="module")
def designer():
    bonfire = BonfiresClient()
    harmonica = HarmonicaClient()
    return SurveyDesigner(bonfire, harmonica)


@pytest.fixture(scope="module")
def seeded_topic_id():
    """Insert a minimal topic row so batch-path tests have a valid topic_id."""
    db.init()
    batch_id = db.insert_batch(
        batch_run_id="test-batch-fixture",
        type="discovery",
        query="community governance",
        context_text="",
        raw_response="",
    )
    return db.insert_topic(
        batch_id=batch_id,
        topic="community governance",
        format_suggestion="SWOT",
        template_id=None,
    )


# ---------------------------------------------------------------------------
# Legacy single-shot path: build_survey_params(topic_query)
# ---------------------------------------------------------------------------

class TestBuildSurveyParams:
    def test_returns_all_required_keys(self, designer):
        params = designer.build_survey_params("community governance")
        for key in REQUIRED_KEYS:
            assert key in params, f"Missing key: {key}"

    def test_topic_is_english_string(self, designer):
        params = designer.build_survey_params("community governance")
        assert isinstance(params["topic"], str)
        assert len(params["topic"]) > 0

    def test_goal_is_string(self, designer):
        params = designer.build_survey_params("community governance")
        assert isinstance(params["goal"], str)
        assert len(params["goal"]) > 0

    def test_questions_is_list_of_dicts_with_text(self, designer):
        params = designer.build_survey_params("community governance")
        questions = params["questions"]
        assert isinstance(questions, list)
        assert 2 <= len(questions) <= 4
        for q in questions:
            assert isinstance(q, dict)
            assert "text" in q

    def test_cross_pollination_is_bool(self, designer):
        params = designer.build_survey_params("community governance")
        assert isinstance(params["cross_pollination"], bool)

    def test_required_fields_present_for_create_session(self, designer):
        params = designer.build_survey_params("community governance")
        assert "topic" in params
        assert "goal" in params


# ---------------------------------------------------------------------------
# Batch path: build_survey_params_from_topic(topic_id, n)
# ---------------------------------------------------------------------------

class TestBuildSurveyParamsFromTopic:
    def test_single_variation_returns_list_of_one(self, designer, seeded_topic_id):
        results = designer.build_survey_params_from_topic(seeded_topic_id, n=1)
        assert isinstance(results, list)
        assert len(results) == 1

    def test_batch_returns_correct_count(self, designer, seeded_topic_id):
        results = designer.build_survey_params_from_topic(seeded_topic_id, n=2)
        assert isinstance(results, list)
        assert len(results) == 2

    def test_each_result_has_required_keys(self, designer, seeded_topic_id):
        results = designer.build_survey_params_from_topic(seeded_topic_id, n=1)
        for result in results:
            for key in REQUIRED_KEYS:
                assert key in result, f"Missing key: {key}"

    def test_each_result_has_db_id(self, designer, seeded_topic_id):
        results = designer.build_survey_params_from_topic(seeded_topic_id, n=1)
        for result in results:
            assert "id" in result
            assert isinstance(result["id"], int)

    def test_each_result_has_batch_run_id(self, designer, seeded_topic_id):
        results = designer.build_survey_params_from_topic(seeded_topic_id, n=1)
        for result in results:
            assert "batch_run_id" in result
            assert len(result["batch_run_id"]) > 0

    def test_designs_stored_in_db(self, designer, seeded_topic_id):
        results = designer.build_survey_params_from_topic(seeded_topic_id, n=2)
        for result in results:
            stored = db.get_design(result["id"])
            assert stored is not None
            assert stored["topic_id"] == seeded_topic_id

    def test_batch_variations_differ(self, designer, seeded_topic_id):
        results = designer.build_survey_params_from_topic(seeded_topic_id, n=2)
        assert results[0].get("goal") != results[1].get("goal")
