"""Prompt builders for clinical case analysis modes.

The pipeline ultimately accepts one free-text clinical question.  This module
keeps web and API prompt construction consistent when users enter a longer case
plus choose a specific clinical task button.
"""

from __future__ import annotations

from typing import Mapping


PROMPT_TEMPLATES: dict[str, dict[str, str]] = {
    "evidence": {
        "label": "Evidence answer",
        "description": "Convert the case into a PICO question and summarize the best evidence.",
        "instruction": (
            "Formulate the most answerable PICO question for this case, identify the "
            "population, intervention/exposure/test, comparison, and outcome, then "
            "summarize the best available evidence with absolute risks when possible."
        ),
    },
    "diagnosis": {
        "label": "Diagnostic approach",
        "description": "Focus on differential diagnosis and diagnostic testing strategy.",
        "instruction": (
            "Address the likely differential diagnosis and the highest-yield diagnostic "
            "tests. Prioritize evidence on test accuracy, likelihood ratios, and how "
            "testing changes post-test probability."
        ),
    },
    "treatment": {
        "label": "Treatment options",
        "description": "Compare management options and treatment benefits/harms.",
        "instruction": (
            "Compare reasonable treatment or management options for this patient. "
            "Prioritize evidence on patient-important outcomes, absolute benefit, "
            "harms, contraindications, and number needed to treat or harm when available."
        ),
    },
    "prognosis": {
        "label": "Risk & prognosis",
        "description": "Estimate prognosis, baseline risk, and meaningful risk modifiers.",
        "instruction": (
            "Estimate prognosis and baseline risk for this case. Identify validated "
            "risk factors or prediction tools, expected outcomes over time, and how "
            "the patient-specific details modify risk."
        ),
    },
    "guidelines": {
        "label": "Guideline check",
        "description": "Frame the case around guideline-concordant care and evidence quality.",
        "instruction": (
            "Evaluate guideline-concordant care for this scenario. Compare guideline "
            "recommendations with primary evidence, note evidence quality, and flag "
            "areas where guidelines may not apply to this patient."
        ),
    },
}

DEFAULT_PROMPT_TYPE = "evidence"


def prompt_options() -> list[dict[str, str]]:
    """Return prompt metadata in UI-friendly order."""
    return [
        {"key": key, "label": spec["label"], "description": spec["description"]}
        for key, spec in PROMPT_TEMPLATES.items()
    ]


def build_clinical_prompt(
    *,
    clinical_case: str = "",
    focus_question: str = "",
    prompt_type: str = DEFAULT_PROMPT_TYPE,
    legacy_text: str = "",
) -> str:
    """Build the free-text prompt sent to the evidence pipeline.

    ``legacy_text`` preserves compatibility with existing callers that submit a
    single ``text`` or ``question`` field.  New callers can submit a longer case,
    an optional focus question, and one of the named prompt types.
    """
    clinical_case = (clinical_case or "").strip()
    focus_question = (focus_question or "").strip()
    legacy_text = (legacy_text or "").strip()
    prompt_type = (prompt_type or DEFAULT_PROMPT_TYPE).strip().lower()

    if not clinical_case and not focus_question:
        return legacy_text

    template = PROMPT_TEMPLATES.get(prompt_type, PROMPT_TEMPLATES[DEFAULT_PROMPT_TYPE])
    parts = [
        f"Clinical task: {template['label']}",
        f"Task instructions: {template['instruction']}",
    ]
    if clinical_case:
        parts.append(f"Clinical case:\n{clinical_case}")
    if focus_question:
        parts.append(f"Specific question to answer:\n{focus_question}")
    elif legacy_text:
        parts.append(f"Additional context or original query:\n{legacy_text}")
    parts.append(
        "Return an evidence-based clinical decision support answer. Include PICO "
        "elements, a concise bottom line, probability estimates when supported, "
        "limitations, and key references."
    )
    return "\n\n".join(parts)


def prompt_type_from_payload(payload: Mapping[str, object]) -> str:
    """Extract and normalize prompt_type from a JSON-like payload."""
    raw = payload.get("prompt_type") or payload.get("mode") or DEFAULT_PROMPT_TYPE
    return str(raw).strip().lower() or DEFAULT_PROMPT_TYPE
