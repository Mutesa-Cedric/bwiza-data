"""Tests for LID wrapper (mocked, no real model needed)."""

from unittest.mock import MagicMock, patch

from apps.common import lid


def test_predict_lang_returns_tuple():
    with patch.object(lid, "_model", None):
        mock_model = MagicMock()
        mock_model.predict.return_value = (["__label__kin_Latn"], [0.95])

        with patch.object(lid, "_load_model", side_effect=lambda: setattr(lid, "_model", mock_model)):
            lang, score, model_name = lid.predict_lang("Muraho neza")
            assert lang == "kin_Latn"
            assert score == 0.95
            assert model_name == "glotlid"


def test_predict_lang_strips_label_prefix():
    with patch.object(lid, "_model", None):
        mock_model = MagicMock()
        mock_model.predict.return_value = (["__label__eng_Latn"], [0.88])

        with patch.object(lid, "_load_model", side_effect=lambda: setattr(lid, "_model", mock_model)):
            lang, score, _ = lid.predict_lang("Hello world")
            assert lang == "eng_Latn"
            assert score == 0.88
