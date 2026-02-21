"""Language identification wrapper (GlotLID / fasttext)."""

from apps.common.logging import get_logger

log = get_logger(__name__)

_model = None
_model_name = "glotlid"


def _patch_fasttext_numpy():
    """Patch fasttext.FastText module to use np.asarray instead of np.array(copy=False)."""
    import fasttext.FastText as ft_module
    import numpy as np

    _orig_array = np.array

    def _compat_array(obj, *args, copy=None, **kwargs):
        if copy is False:
            return np.asarray(obj, *args, **kwargs)
        if copy is not None:
            kwargs["copy"] = copy
        return _orig_array(obj, *args, **kwargs)

    ft_module.np.array = _compat_array


def _load_model():
    global _model
    if _model is not None:
        return

    try:
        import fasttext
        from huggingface_hub import hf_hub_download

        _patch_fasttext_numpy()
        model_path = hf_hub_download(repo_id="cis-lmu/glotlid", filename="model.bin")
        _model = fasttext.load_model(model_path)
        log.info("GlotLID model loaded from %s", model_path)
    except Exception as exc:
        raise RuntimeError(
            "Failed to load GlotLID model. Install: pip install fasttext-wheel huggingface_hub"
        ) from exc


def predict_lang(text: str) -> tuple[str, float, str]:
    """Predict language of text. Returns (lang_code, confidence, model_name)."""
    _load_model()

    # fasttext expects single line
    clean = text.replace("\n", " ")[:5000]
    predictions = _model.predict(clean, k=1)
    label = predictions[0][0]  # e.g. "__label__kin_Latn"
    score = float(predictions[1][0])

    # Extract language code: __label__kin_Latn -> kin_Latn
    lang = label.replace("__label__", "")
    return lang, score, _model_name
