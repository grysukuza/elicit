"""
Meta-analysis engine.

Given a ClinicalQuestion and a list of Elicit papers, this module:
1. Uses Claude to synthesize the evidence into a structured clinical answer.
2. Extracts numerical data and computes probability estimates:
   ARR, RRR, NNT, PPV, NPV, LR+, LR-
3. Returns a MetaAnalysisResult dataclass.
"""

import json
import math
import os
from dataclasses import dataclass, field, asdict
from typing import Optional, List
import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-6"


@dataclass
class ProbabilityEstimates:
    # Therapeutic / RCT metrics
    control_event_rate: Optional[float] = None      # CER
    treatment_event_rate: Optional[float] = None    # EER (experimental event rate)
    arr: Optional[float] = None                     # Absolute Risk Reduction
    rrr: Optional[float] = None                     # Relative Risk Reduction
    nnt: Optional[float] = None                     # Number Needed to Treat

    # Diagnostic test metrics
    sensitivity: Optional[float] = None
    specificity: Optional[float] = None
    prevalence: Optional[float] = None              # pre-test probability
    ppv: Optional[float] = None                     # Positive Predictive Value
    npv: Optional[float] = None                     # Negative Predictive Value
    lr_positive: Optional[float] = None             # Positive Likelihood Ratio
    lr_negative: Optional[float] = None             # Negative Likelihood Ratio
    post_test_prob_positive: Optional[float] = None
    post_test_prob_negative: Optional[float] = None

    notes: str = ""

    def compute_derived(self) -> None:
        """Fill in any computable fields from what is already populated."""
        # --- Therapeutic ---
        cer = self.control_event_rate
        eer = self.treatment_event_rate
        if cer is not None and eer is not None:
            self.arr = round(cer - eer, 4)
            if cer > 0:
                self.rrr = round((cer - eer) / cer, 4)
            if self.arr and self.arr > 0:
                self.nnt = round(1 / self.arr, 1)

        # --- Diagnostic ---
        sens = self.sensitivity
        spec = self.specificity
        prev = self.prevalence

        if sens is not None and spec is not None:
            # LRs
            if spec < 1.0:
                self.lr_positive = round(sens / (1 - spec), 3)
            if sens < 1.0:
                self.lr_negative = round((1 - sens) / spec, 3) if spec > 0 else None

            if prev is not None:
                # Bayes via natural frequency
                tp = sens * prev
                fp = (1 - spec) * (1 - prev)
                tn = spec * (1 - prev)
                fn = (1 - sens) * prev

                if (tp + fp) > 0:
                    self.ppv = round(tp / (tp + fp), 4)
                if (tn + fn) > 0:
                    self.npv = round(tn / (tn + fn), 4)

                # Post-test probabilities via likelihood ratio × pre-test odds
                if self.lr_positive is not None:
                    pre_odds = prev / (1 - prev) if prev < 1 else float("inf")
                    post_odds_pos = pre_odds * self.lr_positive
                    self.post_test_prob_positive = round(
                        post_odds_pos / (1 + post_odds_pos), 4
                    )
                if self.lr_negative is not None:
                    pre_odds = prev / (1 - prev) if prev < 1 else float("inf")
                    post_odds_neg = pre_odds * self.lr_negative
                    self.post_test_prob_negative = round(
                        post_odds_neg / (1 + post_odds_neg), 4
                    )

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class MetaAnalysisResult:
    pico_statement: str
    question_type: str
    summary: str                       # Plain-English answer (2-3 paragraphs)
    clinical_bottom_line: str          # One-sentence take-away
    evidence_quality: str              # e.g. "High (multiple RCTs)", "Low (case series)"
    probability_estimates: ProbabilityEstimates
    papers_used: List[dict] = field(default_factory=list)
    limitations: str = ""
    further_reading: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["probability_estimates"] = self.probability_estimates.to_dict()
        return d


# ─────────────────────────────────────────────────────────────────────────────
# Prompt templates
# ─────────────────────────────────────────────────────────────────────────────

SYNTHESIS_SYSTEM = """\
You are an expert clinical epidemiologist and biostatistician embedded in a hospital
decision-support system.  Your audience is the treating physician who needs a rapid,
evidence-based answer at the bedside.

Given a structured PICO clinical question and a set of reference abstracts retrieved
from PubMed/Elicit, you will:

1. Synthesise the evidence into a clear 2-3 paragraph clinical answer.
2. State a one-sentence clinical bottom line.
3. Rate the overall quality of evidence (High/Moderate/Low/Very Low) and explain why.
4. Extract or estimate the key probability metrics from the data.
5. Note important limitations or caveats.

Return ONLY valid JSON matching this schema exactly:
{
  "summary": "...",
  "clinical_bottom_line": "...",
  "evidence_quality": "...",
  "limitations": "...",
  "extracted_data": {
    "question_type": "therapeutic|diagnostic|prognostic|harm",
    "control_event_rate": null,
    "treatment_event_rate": null,
    "sensitivity": null,
    "specificity": null,
    "prevalence": null,
    "data_notes": "..."
  }
}

Rules:
- All numeric values must be proportions (0.0–1.0), NOT percentages.
- Use null for any value you cannot extract or reliably estimate from the abstracts.
- Do NOT fabricate data.  If evidence is insufficient for a metric, say so in data_notes.
- Clinical bottom line must be ≤ 40 words.
"""


def _build_user_message(pico_statement: str, papers: List[dict]) -> str:
    lines = [f"CLINICAL QUESTION: {pico_statement}", "", "REFERENCE ABSTRACTS:", ""]
    for i, p in enumerate(papers[:15], 1):  # cap at 15 to stay within context
        title = p.get("title", "Untitled")
        year = p.get("year", "")
        authors = ", ".join((p.get("authors") or [])[:3])
        if len(p.get("authors") or []) > 3:
            authors += " et al."
        abstract = p.get("abstract") or "No abstract available."
        lines.append(f"[{i}] {title} ({authors}, {year})")
        lines.append(f"    {abstract[:600]}")
        lines.append("")
    return "\n".join(lines)


def run_meta_analysis(
    pico_statement: str,
    question_type: str,
    papers: List[dict],
) -> MetaAnalysisResult:
    """
    Run the meta-analysis pipeline using Claude.

    Args:
        pico_statement: The formatted PICO statement string.
        question_type: 'therapeutic' | 'diagnostic' | 'prognostic' | 'harm'
        papers: List of Elicit paper dicts.

    Returns:
        MetaAnalysisResult with populated probability estimates.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    if not papers:
        # No Elicit papers — ask Claude to answer from its own training knowledge
        no_paper_msg = (
            f"CLINICAL QUESTION: {pico_statement}\n\n"
            "No reference abstracts are available from the literature search. "
            "Please answer the clinical question using your own medical knowledge, "
            "citing well-known landmark trials or guidelines where applicable. "
            "Clearly note in evidence_quality that this answer is based on model "
            "knowledge rather than retrieved abstracts."
        )
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYNTHESIS_SYSTEM,
            messages=[{"role": "user", "content": no_paper_msg}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {
                "summary": raw[:2000],
                "clinical_bottom_line": "See summary above.",
                "evidence_quality": "Based on model knowledge (no abstracts retrieved)",
                "limitations": "No reference papers retrieved; answer based on model training data.",
                "extracted_data": {"question_type": question_type, "data_notes": ""},
            }
        ed = parsed.get("extracted_data", {})
        estimates = ProbabilityEstimates(
            control_event_rate=ed.get("control_event_rate"),
            treatment_event_rate=ed.get("treatment_event_rate"),
            sensitivity=ed.get("sensitivity"),
            specificity=ed.get("specificity"),
            prevalence=ed.get("prevalence"),
            notes=ed.get("data_notes", ""),
        )
        estimates.compute_derived()
        return MetaAnalysisResult(
            pico_statement=pico_statement,
            question_type=ed.get("question_type", question_type),
            summary=parsed.get("summary", ""),
            clinical_bottom_line=parsed.get("clinical_bottom_line", ""),
            evidence_quality=parsed.get("evidence_quality", ""),
            probability_estimates=estimates,
            papers_used=[],
            limitations=parsed.get("limitations", ""),
        )

    user_msg = _build_user_message(pico_statement, papers)

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=SYNTHESIS_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Graceful fallback
        parsed = {
            "summary": raw[:2000],
            "clinical_bottom_line": "See summary above.",
            "evidence_quality": "Unknown",
            "limitations": "JSON parsing failed; raw response shown.",
            "extracted_data": {"question_type": question_type, "data_notes": ""},
        }

    ed = parsed.get("extracted_data", {})

    estimates = ProbabilityEstimates(
        control_event_rate=ed.get("control_event_rate"),
        treatment_event_rate=ed.get("treatment_event_rate"),
        sensitivity=ed.get("sensitivity"),
        specificity=ed.get("specificity"),
        prevalence=ed.get("prevalence"),
        notes=ed.get("data_notes", ""),
    )
    estimates.compute_derived()

    # Slim papers for storage (keep only display fields)
    slim_papers = []
    for p in papers:
        urls = p.get("urls") or []
        doi = p.get("doi")
        if doi and not urls:
            urls = [f"https://doi.org/{doi}"]
        slim_papers.append(
            {
                "title": p.get("title", ""),
                "authors": p.get("authors") or [],
                "year": p.get("year"),
                "venue": p.get("venue", ""),
                "abstract": (p.get("abstract") or "")[:2500],
                "urls": urls,
                "pmid": p.get("pmid"),
                "doi": doi,
            }
        )

    return MetaAnalysisResult(
        pico_statement=pico_statement,
        question_type=ed.get("question_type", question_type),
        summary=parsed.get("summary", ""),
        clinical_bottom_line=parsed.get("clinical_bottom_line", ""),
        evidence_quality=parsed.get("evidence_quality", ""),
        probability_estimates=estimates,
        papers_used=slim_papers,
        limitations=parsed.get("limitations", ""),
    )


def format_probability_table(estimates: ProbabilityEstimates) -> str:
    """Return a human-readable text table of probability estimates."""
    rows = []

    def add(label: str, value, fmt: str = ".1%", suffix: str = ""):
        if value is not None:
            if fmt == "nnt":
                rows.append(f"  {label:<40} {value:.1f}{suffix}")
            else:
                rows.append(f"  {label:<40} {value:{fmt}}{suffix}")

    rows.append("PROBABILITY ESTIMATES")
    rows.append("─" * 55)

    # Therapeutic
    add("Control Event Rate (CER)", estimates.control_event_rate)
    add("Treatment Event Rate (EER)", estimates.treatment_event_rate)
    add("Absolute Risk Reduction (ARR)", estimates.arr)
    add("Relative Risk Reduction (RRR)", estimates.rrr)
    add("Number Needed to Treat (NNT)", estimates.nnt, fmt="nnt", suffix=" patients")

    if any(
        v is not None
        for v in [estimates.sensitivity, estimates.lr_positive, estimates.ppv]
    ):
        rows.append("")

    # Diagnostic
    add("Sensitivity", estimates.sensitivity)
    add("Specificity", estimates.specificity)
    add("Pre-test Probability (Prevalence)", estimates.prevalence)
    add("Positive Predictive Value (PPV)", estimates.ppv)
    add("Negative Predictive Value (NPV)", estimates.npv)
    add("Positive Likelihood Ratio (LR+)", estimates.lr_positive, fmt=".2f")
    add("Negative Likelihood Ratio (LR−)", estimates.lr_negative, fmt=".3f")
    add("Post-test Prob (test positive)", estimates.post_test_prob_positive)
    add("Post-test Prob (test negative)", estimates.post_test_prob_negative)

    if estimates.notes:
        rows.append("")
        rows.append(f"  Note: {estimates.notes}")

    if len(rows) <= 2:
        rows.append("  Insufficient numerical data to compute probability estimates.")

    return "\n".join(rows)
