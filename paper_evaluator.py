"""
Critical appraisal of individual reference papers using established
evidence-based medicine frameworks.

Frameworks applied (chosen by study design):
  - Oxford CEBM Levels of Evidence (1a-5)
  - GRADE quality assessment (High / Moderate / Low / Very Low)
  - Jadad scale (RCTs, 0-5)
  - QUADAS-2 domains (diagnostic accuracy studies)
  - AMSTAR-2 summary (systematic reviews / meta-analyses)
  - Newcastle-Ottawa Scale (cohort / case-control)
"""

import json
import os
from typing import Optional
import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-6"


APPRAISAL_SYSTEM = """\
You are an expert clinical epidemiologist performing a critical appraisal of a
single research paper based on its title and abstract. Your appraisal must be
rigorous, evidence-based, and use established frameworks.

Steps:
1. Identify the study design (RCT, systematic review, meta-analysis, cohort,
   case-control, cross-sectional, diagnostic accuracy, case series, narrative
   review, guideline, other).
2. Assign an Oxford CEBM Level of Evidence (1a, 1b, 2a, 2b, 3a, 3b, 4, 5).
3. Assign a GRADE quality rating (High, Moderate, Low, Very Low).
4. Apply the design-appropriate appraisal tool:
   - RCT  → Jadad scale (0-5) AND Cochrane RoB-2 domains.
   - Diagnostic accuracy → QUADAS-2 domain judgments.
   - Systematic review / meta-analysis → AMSTAR-2 critical-domain summary.
   - Cohort / case-control → Newcastle-Ottawa Scale (max 9).
   - Other → narrative risk-of-bias summary.
5. Summarise strengths, weaknesses, and bedside applicability.

Return ONLY valid JSON matching this schema EXACTLY:
{
  "study_design": "...",
  "oxford_cebm_level": "...",
  "grade_quality": "High|Moderate|Low|Very Low",
  "grade_rationale": "...",
  "jadad_score": null,
  "jadad_breakdown": null,
  "newcastle_ottawa_score": null,
  "amstar2_summary": null,
  "quadas2_summary": null,
  "risk_of_bias_domains": [
    {"domain": "...", "judgment": "Low|Some concerns|High|Unclear", "rationale": "..."}
  ],
  "sample_size": null,
  "primary_outcome": "...",
  "key_findings": "...",
  "strengths": ["..."],
  "weaknesses": ["..."],
  "applicability": "...",
  "bottom_line": "..."
}

Rules:
- Use null for fields that do not apply to the study design.
- jadad_score: integer 0-5 (only for RCTs). jadad_breakdown: short text explaining points.
- newcastle_ottawa_score: integer 0-9 (only for cohort/case-control).
- risk_of_bias_domains: 3-7 entries, design-appropriate.
- sample_size: integer if reported, else null.
- strengths and weaknesses: 2-5 short bullet points each.
- bottom_line: ≤ 35 words clinical takeaway from THIS paper.
- Do not fabricate data. If the abstract is too sparse, say so in rationales.
"""


def evaluate_paper(paper: dict) -> dict:
    """
    Run a critical appraisal on a single paper dict (Elicit format).

    Args:
        paper: Dict with keys title, authors, year, venue, abstract, doi, pmid.

    Returns:
        Dict with the appraisal JSON.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    title = paper.get("title", "Untitled")
    year = paper.get("year", "")
    venue = paper.get("venue", "")
    authors = ", ".join((paper.get("authors") or [])[:5])
    if len(paper.get("authors") or []) > 5:
        authors += " et al."
    abstract = paper.get("abstract") or "No abstract available."

    user_msg = (
        f"TITLE: {title}\n"
        f"AUTHORS: {authors}\n"
        f"YEAR: {year}\n"
        f"VENUE: {venue}\n\n"
        f"ABSTRACT:\n{abstract}\n"
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=APPRAISAL_SYSTEM,
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
        parsed = {
            "study_design": "Unknown",
            "oxford_cebm_level": "5",
            "grade_quality": "Very Low",
            "grade_rationale": "Could not parse appraisal output.",
            "risk_of_bias_domains": [],
            "strengths": [],
            "weaknesses": ["Appraisal output was not valid JSON."],
            "applicability": "",
            "bottom_line": raw[:200],
        }

    return parsed


# ─────────────────────────────────────────────────────────────────────────────
# Reference export helpers
# ─────────────────────────────────────────────────────────────────────────────

def _slug(s: str, n: int = 20) -> str:
    keep = []
    for ch in s:
        if ch.isalnum():
            keep.append(ch)
        if len(keep) >= n:
            break
    return "".join(keep) or "ref"


def papers_to_bibtex(papers: list[dict]) -> str:
    """Export reference list as a BibTeX string."""
    out = []
    for i, p in enumerate(papers, 1):
        first_author = (p.get("authors") or ["anon"])[0]
        last = first_author.split()[-1] if first_author else "anon"
        key = f"{_slug(last, 12)}{p.get('year') or ''}_{i}"

        authors_str = " and ".join(p.get("authors") or [])
        fields = {
            "title": (p.get("title") or "").replace("{", "").replace("}", ""),
            "author": authors_str,
            "year": str(p.get("year") or ""),
            "journal": p.get("venue") or "",
        }
        if p.get("doi"):
            fields["doi"] = p["doi"]
        if p.get("pmid"):
            fields["pmid"] = str(p["pmid"])
        urls = p.get("urls") or []
        if urls:
            fields["url"] = urls[0]

        out.append(f"@article{{{key},")
        for k, v in fields.items():
            if v:
                out.append(f"  {k} = {{{v}}},")
        out.append("}\n")
    return "\n".join(out)


def papers_to_ris(papers: list[dict]) -> str:
    """Export reference list as RIS format (for EndNote/Zotero/Mendeley)."""
    out = []
    for p in papers:
        out.append("TY  - JOUR")
        for a in (p.get("authors") or []):
            out.append(f"AU  - {a}")
        if p.get("year"):
            out.append(f"PY  - {p['year']}")
        if p.get("title"):
            out.append(f"TI  - {p['title']}")
        if p.get("venue"):
            out.append(f"JO  - {p['venue']}")
        if p.get("doi"):
            out.append(f"DO  - {p['doi']}")
        if p.get("pmid"):
            out.append(f"AN  - {p['pmid']}")
        for u in (p.get("urls") or []):
            out.append(f"UR  - {u}")
        if p.get("abstract"):
            out.append(f"AB  - {p['abstract']}")
        out.append("ER  - \n")
    return "\n".join(out)
