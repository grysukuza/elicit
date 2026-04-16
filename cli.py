#!/usr/bin/env python3
"""
Command-line interface for the Clinical Decision Support Tool.

Usage examples:
  python cli.py "Should I use DOAC vs warfarin for a patient with AFib and CHA2DS2-VASc 3?"
  python cli.py --interactive          # multi-turn PICO clarification
  python cli.py --text "..." --pdf report.pdf
  python cli.py --text "..." --email physician@hospital.org
  echo "my question" | python cli.py -
"""

import argparse
import json
import os
import sys
from dotenv import load_dotenv

load_dotenv()


def main():
    parser = argparse.ArgumentParser(
        prog="clinical-dss",
        description="Clinical Decision Support: evidence-based answers with probability estimates.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py "65M with AFib, CHA2DS2-VASc 3: DOAC vs warfarin for stroke prevention?"
  python cli.py --interactive
  python cli.py "..." --pdf report.pdf
  python cli.py "..." --json output.json
  echo "my question" | python cli.py -
""",
    )
    parser.add_argument(
        "text",
        nargs="?",
        help="Clinical question text. Use '-' to read from stdin.",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Enable multi-turn PICO clarification (asks questions interactively).",
    )
    parser.add_argument(
        "--pdf",
        metavar="FILE",
        help="Save the report as a PDF to FILE.",
    )
    parser.add_argument(
        "--json",
        metavar="FILE",
        help="Save full result as JSON to FILE.",
    )
    parser.add_argument(
        "--email",
        metavar="ADDRESS",
        help="Email the PDF report to ADDRESS (requires SMTP settings in .env).",
    )
    parser.add_argument(
        "--max-papers",
        type=int,
        default=20,
        metavar="N",
        help="Maximum papers to retrieve from Elicit (default: 20).",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colour output.",
    )

    args = parser.parse_args()

    # ── Resolve input text ───────────────────────────────────────────────────
    free_text = ""
    if args.text == "-":
        free_text = sys.stdin.read().strip()
    elif args.text:
        free_text = args.text.strip()
    elif args.interactive:
        print("Enter your clinical question (press Enter twice when done):")
        lines = []
        while True:
            line = input()
            if line == "" and lines:
                break
            lines.append(line)
        free_text = " ".join(lines).strip()
    else:
        parser.print_help()
        sys.exit(0)

    if not free_text:
        print("Error: no clinical question provided.", file=sys.stderr)
        sys.exit(1)

    color = not args.no_color and sys.stdout.isatty()

    def c(text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if color else text

    # ── Run pipeline ─────────────────────────────────────────────────────────
    print(c("⚙  Analysing clinical question…", "36"), file=sys.stderr)

    if args.interactive:
        from question_parser import parse_question
        from elicit_client import search_papers
        from meta_analysis import run_meta_analysis, format_probability_table
        from pipeline import _type_tags_for

        clinical_q, _ = parse_question(free_text, interactive=True, max_clarifications=3)
        if clinical_q is None:
            print("Failed to extract clinical question.", file=sys.stderr)
            sys.exit(1)

        print(c("\n⚕  Searching Elicit…", "36"), file=sys.stderr)
        type_tags = _type_tags_for(clinical_q.question_type)
        papers = search_papers(
            query=clinical_q.elicit_search_query,
            max_results=args.max_papers,
            type_tags=type_tags,
        )
        print(c(f"   Retrieved {len(papers)} papers.", "36"), file=sys.stderr)
        print(c("⚕  Running meta-analysis…", "36"), file=sys.stderr)
        result_obj = run_meta_analysis(
            pico_statement=clinical_q.pico_statement,
            question_type=clinical_q.question_type,
            papers=papers,
        )
        output = {
            "clinical_question": clinical_q.to_dict(),
            "result": result_obj.to_dict(),
        }
    else:
        from pipeline import run_pipeline
        output = run_pipeline(free_text, max_papers=args.max_papers)

    result = output["result"]
    cq     = output["clinical_question"]

    # ── Render to stdout ─────────────────────────────────────────────────────
    from meta_analysis import format_probability_table, ProbabilityEstimates

    est_dict = result.get("probability_estimates", {})

    # Build ProbabilityEstimates from the dict
    valid_fields = ProbabilityEstimates.__dataclass_fields__.keys()
    est_kwargs = {k: est_dict.get(k) for k in valid_fields}
    est = ProbabilityEstimates(**est_kwargs)

    sep = c("─" * 70, "90")
    print()
    print(c("CLINICAL DECISION SUPPORT REPORT", "1;34"))
    print(sep)

    print(c("\nCLINICAL QUESTION (PICO)", "1"))
    print(f"  {result.get('pico_statement', '')}")

    print(c("\nPICO BREAKDOWN", "1"))
    for label, key in [
        ("Population",     "population"),
        ("Intervention",   "intervention"),
        ("Comparison",     "comparison"),
        ("Outcome",        "outcome"),
        ("Time frame",     "timeframe"),
        ("Context",        "context"),
        ("Question type",  "question_type"),
    ]:
        val = cq.get(key, "")
        if val:
            print(f"  {label:<16} {val}")

    print(c("\nCLINICAL BOTTOM LINE", "1"))
    print(c(f"  {result.get('clinical_bottom_line', '')}", "32"))

    print(c("\nEVIDENCE SUMMARY", "1"))
    print(c(f"  Quality: {result.get('evidence_quality', '')}", "33"))
    for para in result.get("summary", "").split("\n\n"):
        if para.strip():
            # Word-wrap at ~72 chars
            words = para.split()
            line_buf, lines_out = [], []
            for w in words:
                if sum(len(x) + 1 for x in line_buf) + len(w) > 68:
                    lines_out.append("  " + " ".join(line_buf))
                    line_buf = [w]
                else:
                    line_buf.append(w)
            if line_buf:
                lines_out.append("  " + " ".join(line_buf))
            print("\n".join(lines_out))
            print()

    print(c(format_probability_table(est), "1"))

    lim = result.get("limitations", "")
    if lim:
        print(c("\nLIMITATIONS", "1"))
        print(f"  {lim}")

    papers = result.get("papers_used", [])
    if papers:
        print(c("\nREFERENCES", "1"))
        for i, p in enumerate(papers, 1):
            authors = ", ".join((p.get("authors") or [])[:3])
            if len(p.get("authors") or []) > 3:
                authors += " et al."
            urls = p.get("urls") or []
            url_str = f"\n     {c(urls[0], '36;4')}" if urls else ""
            print(f"  [{i}] {p.get('title', '')} ({authors}, {p.get('year', '')}){url_str}")

    print()
    print(sep)
    print(c("DISCLAIMER: AI-assisted tool. Always verify against primary sources.", "90"))
    print()

    # ── Optional outputs ─────────────────────────────────────────────────────
    if args.pdf:
        from pdf_generator import generate_pdf
        pdf_bytes = generate_pdf(result)
        with open(args.pdf, "wb") as f:
            f.write(pdf_bytes)
        print(c(f"✓  PDF saved to: {args.pdf}", "32"), file=sys.stderr)

    if args.json:
        with open(args.json, "w") as f:
            json.dump(output, f, indent=2)
        print(c(f"✓  JSON saved to: {args.json}", "32"), file=sys.stderr)

    if args.email:
        _send_email_cli(args.email, result, color)


def _send_email_cli(recipient: str, result: dict, color: bool):
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders
    from pdf_generator import generate_pdf

    smtp_host = os.environ.get("SMTP_HOST", "")
    if not smtp_host:
        print("Email not configured. Set SMTP_HOST/SMTP_USER/SMTP_PASS/SMTP_FROM in .env.",
              file=sys.stderr)
        return

    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "").replace(" ", "")  # strip spaces from app password
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)

    pdf_bytes = generate_pdf(result)
    msg = MIMEMultipart("mixed")
    msg["Subject"] = "Clinical Decision Support Report"
    msg["From"] = smtp_from
    msg["To"] = recipient
    msg.attach(MIMEText(result.get("clinical_bottom_line", ""), "plain"))

    part = MIMEBase("application", "pdf")
    part.set_payload(pdf_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename="clinical_report.pdf")
    msg.attach(part)

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, [recipient], msg.as_string())
        print(f"✓  Report emailed to {recipient}", file=sys.stderr)
    except Exception as e:
        print(f"Email failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
