"""Tests for language-section extraction from multilingual documents."""

from unittest.mock import patch

from apps.books_corpus.lang_split import extract_lang_sections

# Simulate a trilingual gazette: Kinyarwanda, English, French sections
TRILINGUAL_TEXT = (
    "Iteka rya Perezida ryemeza burundu amasezerano "
    "y'Umuryango w'Abibumbye yerekeranye n'amasezerano ku bucuruzi "
    "mpuzamahanga yemerejwe i Vienna. Minisitiri w'Intebe, Minisitiri "
    "w'Ubucuruzi n'Inganda bashinzwe gushyira mu bikorwa iri teka. "
    "Iri teka ritangira gukurikizwa ku munsi ritangarijweho mu "
    "Igazeti ya Leta ya Repubulika y'u Rwanda."
    "\n\n"
    "Presidential Order ratifying the United Nations Convention on "
    "contracts for the international sale of goods adopted in Vienna. "
    "The Prime Minister and the Minister of Trade and Industry are "
    "entrusted with the implementation of this Order. This Order "
    "comes into force on the date of its publication in the Official "
    "Gazette of the Republic of Rwanda."
    "\n\n"
    "Arrêté Présidentiel portant ratification de la convention des "
    "Nations Unies sur les contrats de vente internationale de "
    "marchandises adoptée à Vienne. Le Premier Ministre et le "
    "Ministre du Commerce et de l'Industrie sont chargés de "
    "l'exécution du présent arrêté. Le présent arrêté entre en "
    "vigueur le jour de sa publication au Journal Officiel."
    "\n\n"
    "Ingingo ya mbere: Kwemeza burundu amasezerano yerekeranye "
    "n'imicungire y'ubucuruzi mpuzamahanga. Amasezerano yose "
    "yemejwe burundu kandi atangiye gukurikizwa mu ngingo zayo "
    "zose. Abashinzwe gushyira mu bikorwa iri teka ni Minisitiri "
    "w'Intebe na Minisitiri w'Ubucuruzi."
    "\n\n"
    "Article One: Ratification of the convention related to "
    "international trade management. All conventions are hereby "
    "ratified and become fully effective. The authorities responsible "
    "for the implementation of this Order are the Prime Minister "
    "and the Minister of Trade."
    "\n\n"
    "Article premier: Ratification de la convention relative à la "
    "gestion du commerce international. Toutes les conventions sont "
    "ratifiées et sortent leur plein et entier effet. Les autorités "
    "chargées de l'exécution sont le Premier Ministre et le Ministre "
    "du Commerce."
)

ALL_ENGLISH_TEXT = (
    "The United Nations Convention on contracts for the international "
    "sale of goods was adopted in Vienna on April 11, 1980. "
    "This convention establishes a comprehensive code of legal rules "
    "governing the formation of contracts for the international sale "
    "of goods, the obligations of the buyer and seller, remedies for "
    "breach of contract, and other aspects of the contract."
    "\n\n"
    "The convention applies to contracts of sale of goods between "
    "parties whose places of business are in different States when "
    "the States are Contracting States. It does not apply to sales "
    "of goods bought for personal, family or household use."
)

KIN_ONLY_TEXT = (
    "Mu Rwanda, uburezi ni ingenzi cyane ku iterambere ry'igihugu. "
    "Abanyarwanda bose bagomba kubona uburezi bwiza kandi bukwiye. "
    "Guverinoma yashyizeho politiki zitandukanye zo guteza imbere "
    "uburezi mu gihugu hose. Ibi birimo gushyiraho amashuri mashya "
    "no guteza imbere ikoranabuhanga mu mashuri. Abarimu bakora "
    "umurimo ukomeye wo kwigisha abana amasomo yose akenewe. "
    "Ababyeyi nabo bafasha abana babo kwiga mu rugo. Igihugu "
    "cyose kigomba gufatanya kugira ngo uburezi burusheho kuba bwiza."
)


@patch("apps.books_corpus.lang_split.predict_lang")
def test_extracts_kin_from_trilingual(mock_lid):
    """Trilingual text should yield only Kinyarwanda blocks."""

    def _mock_predict(text):
        t = text.lower()
        if "iteka" in t or "ingingo" in t or "minisitiri" in t:
            return ("kin_Latn", 0.85, "glotlid")
        if "arrêté" in t or "convention" in t and "ratification" in t:
            return ("fra_Latn", 0.90, "glotlid")
        return ("eng_Latn", 0.95, "glotlid")

    mock_lid.side_effect = _mock_predict

    result = extract_lang_sections(TRILINGUAL_TEXT, block_size=200)
    assert result is not None
    # Should contain Kinyarwanda content
    assert "Iteka" in result or "Ingingo" in result
    # Should NOT contain English or French
    assert "Presidential Order" not in result
    assert "Arrêté Présidentiel" not in result


@patch("apps.books_corpus.lang_split.predict_lang")
def test_returns_none_when_no_target_lang(mock_lid):
    """All-English text should return None."""
    mock_lid.return_value = ("eng_Latn", 0.95, "glotlid")

    result = extract_lang_sections(ALL_ENGLISH_TEXT)
    assert result is None


@patch("apps.books_corpus.lang_split.predict_lang")
def test_returns_none_when_below_min_chars(mock_lid):
    """Very short target-language content should return None."""
    # Use small block_size to ensure the Kinyarwanda fragment
    # ends up in its own block, separate from English text.
    mock_lid.return_value = ("eng_Latn", 0.95, "glotlid")

    # Tiny Kinyarwanda fragment surrounded by English
    short_kin = ALL_ENGLISH_TEXT + "\n\nIteka rya Perezida.\n\n" + ALL_ENGLISH_TEXT
    result = extract_lang_sections(short_kin, min_result_chars=500)
    assert result is None


@patch("apps.books_corpus.lang_split.predict_lang")
def test_preserves_monolingual_kin_text(mock_lid):
    """Pure Kinyarwanda text should be returned in full."""
    mock_lid.return_value = ("kin_Latn", 0.92, "glotlid")

    result = extract_lang_sections(KIN_ONLY_TEXT, block_size=200)
    assert result is not None
    # All content should be preserved
    assert "uburezi" in result
    assert "Abanyarwanda" in result


@patch("apps.books_corpus.lang_split.predict_lang")
def test_respects_min_confidence(mock_lid):
    """Blocks below min_confidence should be excluded."""
    # Return kin_Latn but with low confidence
    mock_lid.return_value = ("kin_Latn", 0.40, "glotlid")

    result = extract_lang_sections(KIN_ONLY_TEXT, min_confidence=0.60)
    assert result is None


@patch("apps.books_corpus.lang_split.predict_lang")
def test_skips_very_short_blocks(mock_lid):
    """Blocks shorter than 50 chars should be skipped entirely."""
    mock_lid.return_value = ("kin_Latn", 0.90, "glotlid")

    text = "Short.\n\n" + KIN_ONLY_TEXT
    result = extract_lang_sections(text, block_size=200)
    assert result is not None
    # The "Short." block should not trigger a predict_lang call
    # (it's under 50 chars), but the main text should be kept
    assert "uburezi" in result
