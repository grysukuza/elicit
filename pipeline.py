"""
Main pipeline: ties together question_parser → elicit_client → meta_analysis.
Used by both the web app and the CLI.
"""

import logging

from question_parser import parse_question_non_interactive, ClinicalQuestion
from elicit_client import search_papers
from meta_analysis import run_meta_analysis, MetaAnalysisResult

logger = logging.getLogger(__name__)


def run_pipeline(free_text: str, max_papers: int = 12, on_stage=None) -> dict:
    """
    Full pipeline from raw text to MetaAnalysisResult dict.

    Args:
        free_text: Physician's raw query.
        max_papers: How many Elicit papers to retrieve (max 100 on Pro plan).
        on_stage:  Optional callback ``on_stage(name, info=None)`` invoked at
                   the boundary of each major step. ``name`` is one of
                   ``"parsing"`` (Claude), ``"searching"`` (Elicit),
                   ``"synthesizing"`` (Claude). ``info`` is an optional dict
                   with additional context (e.g. paper count for
                   ``"synthesizing"``).

    Returns:
        dict with keys: clinical_question, result, elicit_error (if any)
        where result is MetaAnalysisResult.to_dict()
    """
    def _emit(name, info=None):
        if on_stage:
            try:
                on_stage(name, info or {})
            except Exception:
                logger.exception("on_stage callback failed for %s", name)

    # 1. Parse clinical question (Claude)
    _emit("parsing")
    clinical_q: ClinicalQuestion = parse_question_non_interactive(free_text)

    # 2. Search Elicit — prefer high-quality study types
    _emit("searching", {"max_papers": max_papers})
    elicit_error = None
    papers = []
    try:
        type_tags = _type_tags_for(clinical_q.question_type)
        papers = search_papers(
            query=clinical_q.elicit_search_query,
            max_results=max_papers,
            type_tags=type_tags,
        )
    except Exception as exc:
        elicit_error = str(exc)
        logger.warning("Elicit search failed: %s — proceeding with Claude knowledge only.", exc)

    # 3. Meta-analysis (works even with 0 papers — Claude uses its own knowledge)
    _emit("synthesizing", {"paper_count": len(papers)})
    result: MetaAnalysisResult = run_meta_analysis(
        pico_statement=clinical_q.pico_statement,
        question_type=clinical_q.question_type,
        papers=papers,
    )

    _emit("done")
    out = {
        "clinical_question": clinical_q.to_dict(),
        "result": result.to_dict(),
    }
    if elicit_error:
        out["elicit_error"] = elicit_error
    return out


def _type_tags_for(question_type: str) -> list[str]:
    """Return preferred Elicit type tags based on question type."""
    if question_type == "therapeutic":
        return ["RCT", "Meta-Analysis", "Systematic Review"]
    if question_type == "diagnostic":
        return ["Systematic Review", "Meta-Analysis", "Review"]
    if question_type == "prognostic":
        return ["Longitudinal", "Systematic Review", "Meta-Analysis"]
    return ["Meta-Analysis", "Systematic Review", "RCT"]
