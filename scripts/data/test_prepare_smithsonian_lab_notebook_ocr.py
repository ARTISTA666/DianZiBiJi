from prepare_smithsonian_lab_notebook_ocr import candidate_ids, clean_reference_text


def test_candidate_order_is_seeded_and_complete():
    first = candidate_ids(20260713)
    second = candidate_ids(20260713)

    assert first == second
    assert len(first) == 195
    assert len(set(first)) == 195
    assert first != candidate_ids(20260714)


def test_clean_reference_removes_editorial_markup_but_keeps_words():
    raw = (
        "36<BR/>[[underlined]]Experiment[[/underlined]] on water"
        "<br>crossed [[strikethrough]]old[[/strikethrough]] new"
        "<BR/>[[image: apparatus]]"
    )

    assert clean_reference_text(raw) == "36\nExperiment on water\ncrossed old new"
