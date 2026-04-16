# Elicit Clinical Decision Support Tool

## Overview
A Clinical Decision Support System designed for physicians in hospital settings. It automates the process of answering clinical questions by:
1. Parsing raw text into a structured PICO (Population, Intervention, Comparison, Outcome) framework using LLMs.
2. Retrieving relevant academic literature via the Elicit API.
3. Synthesizing a meta-analysis with a "Clinical Bottom Line" and calculated probability estimates (ARR, RRR, NNT, Sensitivity, Specificity).

## Tech Stack
- **Backend:** Python 3.12 with Flask
- **AI/LLM:** Anthropic Claude (claude-sonnet-4-6)
- **External API:** Elicit API for academic literature retrieval
- **PDF Generation:** ReportLab
- **Package Manager:** pip

## Project Structure
- `app.py` - Flask web server (main entry point), serves on port 5000
- `pipeline.py` - Main orchestrator that ties together parser, client, and analysis engine
- `question_parser.py` - Uses Claude to extract PICO elements from free text
- `elicit_client.py` - Handles interaction with the Elicit API
- `meta_analysis.py` - Performs evidence synthesis and calculates statistical metrics
- `pdf_generator.py` - Generates final clinical report in PDF format
- `cli.py` - Command-line interface for interactive use
- `templates/index.html` - Web UI template
- `static/style.css` - Web UI styles
- `requirements.txt` - Python dependencies

## Environment Variables Required
- `ANTHROPIC_API_KEY` - Anthropic Claude API key
- `ELICIT_API_KEY` - Elicit API key
- `FLASK_SECRET_KEY` - Flask session secret (optional, auto-generated if not set)
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` - Email configuration (optional)

## Running the App
```bash
python app.py
```
The app runs on `0.0.0.0:5000` in debug mode.

## Workflow
- **Start application**: `python app.py` on port 5000 (webview)
