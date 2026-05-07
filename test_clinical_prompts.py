from clinical_prompts import build_clinical_prompt, prompt_options, prompt_type_from_payload


def test_legacy_text_passthrough():
    assert build_clinical_prompt(legacy_text="simple question") == "simple question"


def test_case_prompt_includes_selected_template():
    prompt = build_clinical_prompt(
        clinical_case="70-year-old with atrial fibrillation",
        focus_question="DOAC vs warfarin?",
        prompt_type="treatment",
    )
    assert "Clinical task: Treatment options" in prompt
    assert "70-year-old with atrial fibrillation" in prompt
    assert "DOAC vs warfarin?" in prompt
    assert "number needed to treat" in prompt


def test_unknown_prompt_type_falls_back_to_evidence():
    prompt = build_clinical_prompt(
        clinical_case="case",
        prompt_type="not-a-real-mode",
    )
    assert "Clinical task: Evidence answer" in prompt


def test_prompt_options_are_api_friendly():
    options = prompt_options()
    assert options[0]["key"] == "evidence"
    assert all({"key", "label", "description"} <= set(option) for option in options)


def test_prompt_type_from_payload_accepts_mode_alias():
    assert prompt_type_from_payload({"mode": "Diagnosis"}) == "diagnosis"
