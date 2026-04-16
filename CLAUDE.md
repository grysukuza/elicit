# Elicit Clinical Decision Support Tool

## Project Overview

A clinical decision support system that takes free text, derives a structured clinical question, queries the Elicit API for relevant research articles, and produces a meta-analysis with probability estimates to assist physicians in a hospital setting.

## Definition of Done

1. **Clinical question extraction** — Given free text, the system asks clarifying questions to define the clinical question using PICO/PICOT framing: Population, Intervention/Therapy or Diagnostic, Comparison, Outcome, and Context (e.g. hospital, clinic, ICU).
2. **Elicit literature retrieval** — Based on the clinical question, the Elicit API is queried to obtain relevant reference articles. Results include clickable links for easy access.
3. **Meta-analysis generation** — A synthesized answer to the clinical question is produced, drawing on the retrieved literature.
4. **Multiple interfaces** — The tool is accessible via:
   - A web UI with a text input field and on-screen output
   - A PDF download link for the generated answer
   - An email input box to send the answer to a recipient
   - Reference links to the source articles
   - A command-line interface (CLI)

## Goal

Produce probability estimates from the meta-analysis to support clinical decision-making:
- Absolute Risk Reduction (ARR)
- Relative Risk Reduction (RRR)
- Positive Predictive Value (PPV)
- Negative Predictive Value (NPV)
- Positive Likelihood Ratio (LR+)
- Negative Likelihood Ratio (LR−)

## Context

- Deployment environment: **hospital setting**
- Users: **physicians** making real-time clinical decisions
- Answers must be clinically rigorous and evidence-based

## Constraints

- All code stays within `/Users/kuzak/Documents/python/elicit`
- Internet access is restricted to `elicit.com` only (for API calls and API documentation)
- No external web searches; rely on Elicit API for literature

## Environment

- API key is in `.env` as `ELICIT_API_KEY`
- Access Elicit API documentation at `https://elicit.com` to understand available endpoints

## Project Steps

1. **Plan** — Define architecture, identify Elicit API endpoints, design data flow
2. **Execute** — Build each component (clinical question parser, Elicit client, meta-analysis engine, probability calculator, web UI, CLI, PDF/email outputs)
3. **Verify subgoals** — Test each component in isolation (API connectivity, question parsing, probability calculations)
4. **Evaluate** — Confirm definition of done and goal (probability estimates) are met end-to-end
5. **Summarize** — Document files changed, open questions, and evidence of working system

## Deliverables

- **Files changed** — listed at end of each work session
- **Summary** — concise description of what was built
- **Open questions** — gaps, limitations, or paths for further advancement
- **Evidence it worked** — test output, screenshots, or sample runs showing the system producing a clinical answer with probability estimates
