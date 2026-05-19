"""
End-to-end test using mock data (no API keys required).
Verifies: probability calculations, PDF generation, plain-text rendering.
"""

import json
import sys
import os

# ── 1. Probability estimate math ─────────────────────────────────────────────
print("=" * 60)
print("TEST 1: Probability calculations")
print("=" * 60)

from meta_analysis import ProbabilityEstimates, format_probability_table

# Therapeutic example: DOAC vs warfarin
# Typical values from ARISTOTLE trial (apixaban vs warfarin)
# Stroke/SE rate: warfarin 1.60%/yr, apixaban 1.27%/yr
t_est = ProbabilityEstimates(
    control_event_rate=0.0160,   # warfarin stroke rate
    treatment_event_rate=0.0127, # apixaban stroke rate
)
t_est.compute_derived()
print("\nTherapeutic (apixaban vs warfarin, stroke endpoint):")
print(format_probability_table(t_est))
assert t_est.arr is not None,  "ARR not computed"
assert t_est.rrr is not None,  "RRR not computed"
assert t_est.nnt is not None,  "NNT not computed"
assert abs(t_est.arr - 0.0033) < 0.0001, f"ARR wrong: {t_est.arr}"
assert abs(t_est.rrr - 0.2063) < 0.001,  f"RRR wrong: {t_est.rrr}"
print("  ✓ Therapeutic metrics correct")

# Diagnostic example: troponin for ACS
# sensitivity 0.90, specificity 0.85, prevalence 0.20
d_est = ProbabilityEstimates(
    sensitivity=0.90,
    specificity=0.85,
    prevalence=0.20,
)
d_est.compute_derived()
print("\nDiagnostic (high-sensitivity troponin for ACS):")
print(format_probability_table(d_est))
assert d_est.lr_positive  is not None, "LR+ not computed"
assert d_est.lr_negative  is not None, "LR- not computed"
assert d_est.ppv          is not None, "PPV not computed"
assert d_est.npv          is not None, "NPV not computed"
assert abs(d_est.lr_positive  - 6.0)   < 0.1,  f"LR+ wrong: {d_est.lr_positive}"
assert abs(d_est.lr_negative  - 0.118) < 0.01, f"LR- wrong: {d_est.lr_negative}"
print("  ✓ Diagnostic metrics correct")

# ── 2. Build mock result dict ─────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 2: Mock MetaAnalysisResult dict")
print("=" * 60)

mock_result = {
    "pico_statement": (
        "In adults aged ≥65 with non-valvular atrial fibrillation and "
        "CHA2DS2-VASc ≥ 2, does apixaban (DOAC) compared to warfarin "
        "reduce stroke/systemic embolism?"
    ),
    "question_type": "therapeutic",
    "summary": (
        "Multiple large randomised controlled trials (ARISTOTLE, RE-LY, "
        "ROCKET-AF, ENGAGE AF) demonstrate that direct oral anticoagulants "
        "(DOACs) are at least non-inferior to warfarin for stroke prevention "
        "in non-valvular atrial fibrillation, with most showing superiority "
        "for the composite endpoint.\n\n"
        "Apixaban specifically reduced the risk of stroke or systemic embolism "
        "by ~21% relative to warfarin (HR 0.79, 95% CI 0.66–0.95) in the "
        "ARISTOTLE trial of 18,201 patients. Major bleeding was also "
        "significantly lower with apixaban (HR 0.69). All-cause mortality "
        "favoured apixaban (HR 0.89).\n\n"
        "Guidelines from ACC/AHA and ESC recommend DOACs over warfarin for "
        "most patients with non-valvular AF unless contraindicated "
        "(mechanical heart valves, moderate-severe mitral stenosis)."
    ),
    "clinical_bottom_line": (
        "Apixaban is superior to warfarin for stroke prevention in non-valvular "
        "AF with a favourable safety profile; use DOAC unless specifically contraindicated."
    ),
    "evidence_quality": "High (multiple large RCTs, meta-analyses, guideline consensus)",
    "probability_estimates": t_est.to_dict(),
    "limitations": (
        "Trials excluded patients with severe renal impairment (CrCl <25 mL/min), "
        "mechanical valves, and significant mitral stenosis. Estimates may not "
        "apply to those populations."
    ),
    "papers_used": [
        {
            "title": "Apixaban versus Warfarin in Patients with Atrial Fibrillation (ARISTOTLE)",
            "authors": ["Granger CB", "Alexander JH", "McMurray JJ"],
            "year": 2011,
            "venue": "New England Journal of Medicine",
            "abstract": "Apixaban was superior to warfarin in preventing stroke or systemic embolism, caused less bleeding, and resulted in lower mortality.",
            "urls": ["https://doi.org/10.1056/NEJMoa1107039"],
            "pmid": "21870978",
            "doi": "10.1056/NEJMoa1107039",
        },
        {
            "title": "Dabigatran versus Warfarin in Patients with Atrial Fibrillation (RE-LY)",
            "authors": ["Connolly SJ", "Ezekowitz MD", "Yusuf S"],
            "year": 2009,
            "venue": "New England Journal of Medicine",
            "abstract": "High-dose dabigatran was superior to warfarin for stroke prevention with similar major bleeding rates.",
            "urls": ["https://doi.org/10.1056/NEJMoa0905561"],
            "pmid": "19717844",
            "doi": "10.1056/NEJMoa0905561",
        },
        {
            "title": "Rivaroxaban versus Warfarin in Nonvalvular Atrial Fibrillation (ROCKET-AF)",
            "authors": ["Patel MR", "Mahaffey KW", "Garg J"],
            "year": 2011,
            "venue": "New England Journal of Medicine",
            "abstract": "Rivaroxaban was noninferior to warfarin for the prevention of stroke or systemic embolism.",
            "urls": ["https://doi.org/10.1056/NEJMoa1009638"],
            "pmid": "21830957",
            "doi": "10.1056/NEJMoa1009638",
        },
    ],
}

mock_output = {
    "clinical_question": {
        "population": "adults ≥65 with non-valvular atrial fibrillation",
        "intervention": "apixaban (DOAC)",
        "comparison": "warfarin",
        "outcome": "stroke or systemic embolism",
        "timeframe": "1–3 years",
        "context": "hospital / cardiology",
        "question_type": "therapeutic",
        "pico_statement": mock_result["pico_statement"],
        "elicit_search_query": "DOAC apixaban warfarin atrial fibrillation stroke prevention RCT",
    },
    "result": mock_result,
}

print(json.dumps(mock_output, indent=2)[:500] + "\n  ...[truncated]")
print("  ✓ Mock result dict built")

# ── 3. PDF generation ─────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 3: PDF generation")
print("=" * 60)

from pdf_generator import generate_pdf

pdf_bytes = generate_pdf(mock_result)
pdf_path = os.path.join(os.getcwd(), "sample_report.pdf")
with open(pdf_path, "wb") as f:
    f.write(pdf_bytes)

assert len(pdf_bytes) > 5000, f"PDF too small: {len(pdf_bytes)} bytes"
print(f"  ✓ PDF generated: {len(pdf_bytes):,} bytes → {pdf_path}")

# ── 4. Plain-text rendering ───────────────────────────────────────────────────
print("\n" + "=" * 60)
print("TEST 4: Plain-text output (CLI preview)")
print("=" * 60)

from meta_analysis import ProbabilityEstimates

est_dict = mock_result["probability_estimates"]
valid_fields = ProbabilityEstimates.__dataclass_fields__.keys()
est_kwargs = {k: est_dict.get(k) for k in valid_fields}
est = ProbabilityEstimates(**est_kwargs)

print(f"\n  PICO: {mock_result['pico_statement'][:80]}...")
print(f"  Bottom line: {mock_result['clinical_bottom_line'][:80]}...")
print()
print(format_probability_table(est))
print("  ✓ Plain-text rendering OK")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("ALL TESTS PASSED")
print("=" * 60)
print(f"\nSample PDF written to: {pdf_path}")
print("\nNEXT STEPS TO COMPLETE INTEGRATION:")
print("  1. Add your ANTHROPIC_API_KEY to .env")
print("  2. Verify/regenerate ELICIT_API_KEY at https://elicit.com/settings")
print("  3. Run: python3 cli.py 'your clinical question'")
print("  4. Run: python3 app.py  (then visit http://localhost:5000)")
