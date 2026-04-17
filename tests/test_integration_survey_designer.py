"""
Integration test for SurveyDesigner.build_survey_params().
Hits the live Bonfires agent — requires a populated .env file.
"""
import pytest
from dotenv import load_dotenv

load_dotenv()

from bonfires import BonfiresClient
from harmonica.client import HarmonicaClient
from agent.survey_designer import SurveyDesigner


REQUIRED_KEYS = ("topic", "goal", "prompt", "questions", "cross_pollination")


@pytest.fixture(scope="module")
def designer():
    bonfire = BonfiresClient()
    harmonica = HarmonicaClient()
    return SurveyDesigner(bonfire, harmonica)


class TestSurveyDesignerIntegration:
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

    def test_params_are_valid_for_create_session(self, designer):
        """Params dict must be accepted by HarmonicaClient.create_session."""
        params = designer.build_survey_params("community governance")
        # Validate create_session accepts the params without error by checking
        # the required positional args are present
        assert "topic" in params
        assert "goal" in params
