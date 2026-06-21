from mcm_agent.corpus.taxonomy import problem_type


def test_modern_letters_map_to_types():
    assert problem_type(2024, "A") == "continuous"
    assert problem_type(2024, "B") == "discrete"
    assert problem_type(2024, "C") == "data"
    assert problem_type(2024, "D") == "operations_research"
    assert problem_type(2024, "E") == "sustainability"
    assert problem_type(2024, "F") == "policy"


def test_pre_icm_years_have_no_def_only_ab():
    # Before ICM split, only A/B exist; C was the early ICM problem
    assert problem_type(2001, "A") == "continuous"
    assert problem_type(2001, "B") == "discrete"
    assert problem_type(2001, "C") == "interdisciplinary"


def test_unknown_letter_is_unknown():
    assert problem_type(2024, "Z") == "unknown"
