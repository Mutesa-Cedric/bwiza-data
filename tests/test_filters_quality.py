"""Tests for core quality filters."""

from apps.common.config_types import AppConfig
from apps.common.filters.base import clear_registry, run_filters
from apps.common.filters.quality import register_quality_filters


def setup_function():
    clear_registry()
    register_quality_filters()


def _cfg(**overrides) -> AppConfig:
    cfg = AppConfig()
    for k, v in overrides.items():
        section, attr = k.split(".")
        setattr(getattr(cfg, section), attr, v)
    return cfg


def test_passes_good_text():
    sentences = [
        "Umuryango wAbibumbye wafashwe mu mwaka wa 1945 nyuma yintambara.",
        "Intego yayo ni amahoro ku isi yose no gukomeza umutekano.",
        "Abanyarwanda benshi bakunze gukora ubuhinzi cyane mu ntara zose.",
        "Igihugu cyItaliya gifite amateka maremare cyane muri Buraya.",
        "Umujyi wa Kigali ni umurwa mukuru wigihugu cyacu.",
        "Amashuri menshi yakuze cyane mu myaka icumi ishize.",
        "Urubyiruko rugomba gushishikarira kwiga no guteza imbere igihugu.",
        "Imisozi myinshi iri mu Rwanda ikurura abashyitsi benshi buri mwaka.",
        "Ibikorwa byubukungu bigenda bihinduka bitewe na tekinoloji nshya.",
        "Abantu bo mu turere dutandukanye bafite imico itandukanye cyane.",
    ]
    text = " ".join(sentences)
    cfg = _cfg()
    passed, reasons = run_filters(text, cfg)
    assert passed is True


def test_rejects_short_text():
    cfg = _cfg(**{"filters.min_chars": 200})
    passed, reasons = run_filters("short", cfg)
    assert passed is False
    assert "reject.filter.min_chars" in reasons


def test_rejects_high_url_ratio():
    text = "https://example.com/very/long/url " * 20
    cfg = _cfg(**{"filters.max_url_ratio": 0.20})
    passed, reasons = run_filters(text, cfg)
    assert passed is False
    assert "reject.filter.url_ratio" in reasons


def test_rejects_low_alpha_ratio():
    text = "12345 67890 !@#$% " * 30
    cfg = _cfg(**{"filters.min_alpha_ratio": 0.70})
    passed, reasons = run_filters(text, cfg)
    assert passed is False
    assert "reject.filter.alpha_ratio" in reasons


def test_rejects_repetitive_text():
    text = "same line\n" * 20
    cfg = _cfg(**{"filters.max_repeat_line_ratio": 0.30})
    passed, reasons = run_filters(text, cfg)
    assert passed is False
    assert "reject.filter.repetition" in reasons


def test_passes_diverse_lines():
    lines = [
        "Umuryango wAbibumbye wafashwe mu mwaka wa 1945 nyuma yintambara.",
        "Intego yayo ni amahoro ku isi yose no gukomeza umutekano.",
        "Abanyarwanda benshi bakunze gukora ubuhinzi cyane mu ntara zose.",
        "Igihugu cyItaliya gifite amateka maremare cyane muri Buraya.",
        "Umujyi wa Kigali ni umurwa mukuru wigihugu cyacu gikunda cyane.",
        "Amashuri menshi yakuze cyane mu myaka icumi ishize harimo.",
        "Urubyiruko rugomba gushishikarira kwiga no guteza imbere igihugu cyane.",
        "Imisozi myinshi iri mu Rwanda ikurura abashyitsi benshi buri mwaka.",
        "Ibikorwa byubukungu bigenda bihinduka bitewe na tekinoloji nshya cyane.",
        "Abantu bo mu turere dutandukanye bafite imico itandukanye cyane koko.",
        "Ubuhinzi bwigihugu bugomba guhindurwa kugirango butange umusaruro mwiza.",
        "Inyamaswa zo mu mashyamba azwi cyane muri Afurika zikurura abashakashatsi.",
        "Imyidagaduro itandukanye irimo umupira no kwiruka bikunzwe cyane.",
        "Ubuvuzi bwagutse cyane mu myaka mirongo ibiri ishize hano.",
        "Amasomo mashya yatangiye kwigishwa mu mashuri yisumbuye yose neza.",
        "Ikirere cyiza cyo mu Rwanda gikurura abashyitsi benshi buri gihe.",
        "Ubucuruzi hagati ya Afrika yUburasirazuba bugenda bukura vuba cyane.",
        "Ababyeyi bagomba gufasha abana babo kwiga no gukura neza.",
        "Imirimo myinshi irimo gutangwa kubera iterambere rya tekinoloji nshya.",
        "Umuco nyarwanda ufite agaciro kanini muri societe yacu yose.",
    ]
    text = "\n".join(lines)
    cfg = _cfg(**{"filters.min_chars": 10})
    passed, reasons = run_filters(text, cfg)
    assert passed is True


# --- max_chars filter ---


def test_rejects_too_long_text():
    text = "a " * 60_000  # 120K chars
    cfg = _cfg(**{"filters.min_chars": 1, "filters.min_words": 1})
    passed, reasons = run_filters(text, cfg)
    assert "reject.filter.max_chars" in reasons


def test_passes_normal_length_text():
    text = "Muraho neza cyane. " * 100  # ~1900 chars
    cfg = _cfg()
    _, reasons = run_filters(text, cfg)
    assert "reject.filter.max_chars" not in reasons


# --- min_words filter ---


def test_rejects_too_few_words():
    text = "Muraho " * 10  # 10 words, ~70 chars
    cfg = _cfg(**{"filters.min_chars": 1, "filters.min_words": 30})
    _, reasons = run_filters(text, cfg)
    assert "reject.filter.min_words" in reasons


def test_passes_enough_words():
    text = "Muraho neza cyane. " * 20  # 60 words
    cfg = _cfg(**{"filters.min_chars": 1, "filters.min_words": 30})
    _, reasons = run_filters(text, cfg)
    assert "reject.filter.min_words" not in reasons


def test_min_words_kinyarwanda_agglutinative():
    """Kinyarwanda sentences with 7-8 words each; 5 sentences should pass."""
    sentences = [
        "Umuryango wAbibumbye wafashwe mu mwaka wa 1945",
        "Intego yayo ni amahoro ku isi yose",
        "Abanyarwanda benshi bakunze gukora ubuhinzi cyane",
        "Igihugu cyItaliya gifite amateka maremare cyane",
        "Umujyi wa Kigali ni umurwa mukuru wIgihugu",
    ]
    text = ". ".join(sentences) + "."
    cfg = _cfg(**{"filters.min_chars": 1, "filters.min_words": 30})
    _, reasons = run_filters(text, cfg)
    assert "reject.filter.min_words" not in reasons


# --- word n-gram repetition filter ---


def test_rejects_template_repetition():
    template = "Soma byinshi hano kanda hano "
    text = template * 30
    cfg = _cfg(
        **{
            "filters.min_chars": 1,
            "filters.min_words": 1,
            "filters.max_word_ngram_rep_2": 0.20,
        }
    )
    _, reasons = run_filters(text, cfg)
    assert "reject.filter.word_ngram_repetition" in reasons


def test_passes_diverse_ngrams():
    lines = [
        "Umuryango wAbibumbye wafashwe mu mwaka wa 1945 nyuma yintambara.",
        "Intego yayo ni amahoro ku isi yose no gukomeza umutekano.",
        "Abanyarwanda benshi bakunze gukora ubuhinzi cyane mu ntara zose.",
        "Igihugu cyItaliya gifite amateka maremare cyane muri Buraya.",
        "Umujyi wa Kigali ni umurwa mukuru wigihugu cyacu gikunda.",
        "Amashuri menshi yakuze cyane mu myaka icumi ishize harimo.",
        "Urubyiruko rugomba gushishikarira kwiga no guteza imbere igihugu.",
        "Imisozi myinshi iri mu Rwanda ikurura abashyitsi benshi mwaka.",
        "Ibikorwa byubukungu bigenda bihinduka bitewe na tekinoloji nshya.",
        "Abantu bo mu turere dutandukanye bafite imico itandukanye koko.",
        "Ubuhinzi bwigihugu bugomba guhindurwa kugirango butange umusaruro mwiza.",
        "Inyamaswa zo mu mashyamba azwi muri Afurika zikurura abashakashatsi.",
        "Imyidagaduro itandukanye irimo umupira no kwiruka bikunzwe cyane.",
        "Ubuvuzi bwagutse cyane mu myaka mirongo ibiri ishize hano.",
        "Amasomo mashya yatangiye kwigishwa mu mashuri yisumbuye yose neza.",
        "Ikirere cyiza cyo mu Rwanda gikurura abashyitsi buri gihe.",
        "Ubucuruzi hagati ya Afrika yUburasirazuba bugenda bukura vuba cyane.",
        "Ababyeyi bagomba gufasha abana babo kwiga no gukura neza.",
        "Imirimo myinshi irimo gutangwa kubera iterambere rya tekinoloji.",
        "Umuco nyarwanda ufite agaciro kanini muri societe yacu yose.",
        "Ibihugu byAfurika bigomba gukorana kugirango bibashe gutera imbere.",
        "Amazi meza ni ingenzi cyane kubuzima bwabantu bose ku isi.",
        "Ibihe byiza biragaruka kubanyarwanda bose nyuma yiminsi mibi.",
        "Uburezi bwiza ni inkingi yiterambere mu gihugu icyo aricyo cyose.",
        "Abakozi bakora mu biro byubuyobozi bafite inshingano zikomeye cyane.",
        "Imbuga nkoranyambaga zagize uruhare rukomeye mu iterambere ryisi.",
        "Imyaka myinshi ishize hagati yubukoloni nibyo byabaye nyuma yacyo.",
        "Ubumenyi bwa siyansi bugenda bukura kandi bugafasha abantu benshi.",
        "Ingabo zIgihugu zirinda umutekano wabaturage bose ku butaka bwose.",
        "Abana bakwiye kwiga indimi zose kugirango babashe gukorana neza.",
    ]
    text = "\n".join(lines)
    cfg = _cfg(
        **{
            "filters.min_chars": 1,
            "filters.min_words": 1,
            "filters.max_word_ngram_rep_2": 0.20,
        }
    )
    _, reasons = run_filters(text, cfg)
    assert "reject.filter.word_ngram_repetition" not in reasons


def test_ngram_skips_short_text():
    text = "Muraho neza cyane"
    cfg = _cfg(
        **{
            "filters.min_chars": 1,
            "filters.min_words": 1,
            "filters.max_word_ngram_rep_2": 0.20,
        }
    )
    _, reasons = run_filters(text, cfg)
    assert "reject.filter.word_ngram_repetition" not in reasons


# --- mixed_script filter ---


def test_rejects_mixed_script():
    text = "Muraho " * 20 + "\u0410\u0411\u0412 " * 20  # 50% Cyrillic
    cfg = _cfg(
        **{
            "filters.min_chars": 1,
            "filters.min_words": 1,
            "filters.max_non_latin_alpha_ratio": 0.10,
        }
    )
    _, reasons = run_filters(text, cfg)
    assert "reject.filter.mixed_script" in reasons


def test_passes_pure_latin():
    text = "Muraho neza cyane. " * 20
    cfg = _cfg(
        **{
            "filters.min_chars": 1,
            "filters.min_words": 1,
            "filters.max_non_latin_alpha_ratio": 0.10,
        }
    )
    _, reasons = run_filters(text, cfg)
    assert "reject.filter.mixed_script" not in reasons


def test_mixed_script_allows_small_non_latin():
    latin_words = "Muraho " * 95
    non_latin = "\u0410 " * 5  # ~5% Cyrillic, under 10% threshold
    text = latin_words + non_latin
    cfg = _cfg(
        **{
            "filters.min_chars": 1,
            "filters.min_words": 1,
            "filters.max_non_latin_alpha_ratio": 0.10,
        }
    )
    _, reasons = run_filters(text, cfg)
    assert "reject.filter.mixed_script" not in reasons
