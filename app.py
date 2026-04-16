"""
Flask web application for the Clinical Decision Support Tool.

Routes:
  GET  /           — Main UI (text input form)
  POST /analyze    — Run pipeline, return JSON
  GET  /download   — Download PDF of last result (session-stored)
  POST /send-email — Email result to provided address
"""

import io
import json
import os
import smtplib
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    session,
    redirect,
    url_for,
)
from dotenv import load_dotenv

from pipeline import run_pipeline
from pdf_generator import generate_pdf

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24).hex())

# In-memory result store keyed by session result_id (avoids large session cookies)
_result_store: dict[str, dict] = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True) or {}
    free_text = (data.get("text") or "").strip()

    if not free_text:
        return jsonify({"error": "No text provided."}), 400

    try:
        output = run_pipeline(free_text)
    except Exception as exc:
        app.logger.exception("Pipeline error")
        return jsonify({"error": str(exc)}), 500

    # Store result and hand back a token
    result_id = uuid.uuid4().hex
    _result_store[result_id] = output
    session["result_id"] = result_id

    return jsonify({"result_id": result_id, **output})


@app.route("/download")
def download():
    result_id = request.args.get("result_id") or session.get("result_id")
    if not result_id or result_id not in _result_store:
        return "No result available. Run an analysis first.", 404

    output = _result_store[result_id]
    pdf_bytes = generate_pdf(output["result"])

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="clinical_report.pdf",
    )


@app.route("/send-email", methods=["POST"])
def send_email():
    data = request.get_json(silent=True) or {}
    recipient = (data.get("email") or "").strip()
    result_id = data.get("result_id") or session.get("result_id")

    if not recipient:
        return jsonify({"error": "No email address provided."}), 400
    if not result_id or result_id not in _result_store:
        return jsonify({"error": "No result available. Run an analysis first."}), 404

    output = _result_store[result_id]
    result = output["result"]

    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "").replace(" ", "")  # strip spaces from app password
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)

    if not smtp_host:
        return jsonify(
            {"error": "Email not configured. Set SMTP_HOST/SMTP_USER/SMTP_PASS in .env."}
        ), 503

    try:
        pdf_bytes = generate_pdf(result)
        msg = MIMEMultipart("mixed")
        msg["Subject"] = f"Clinical Decision Support Report"
        msg["From"] = smtp_from
        msg["To"] = recipient

        body_text = _result_to_plain_text(result)
        msg.attach(MIMEText(body_text, "plain"))

        part = MIMEBase("application", "pdf")
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition", "attachment", filename="clinical_report.pdf"
        )
        msg.attach(part)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, [recipient], msg.as_string())

        return jsonify({"message": f"Report emailed to {recipient}."})
    except Exception as exc:
        app.logger.exception("Email error")
        return jsonify({"error": str(exc)}), 500


def _result_to_plain_text(result: dict) -> str:
    from meta_analysis import format_probability_table, ProbabilityEstimates
    est_dict = result.get("probability_estimates", {})
    est = ProbabilityEstimates(**{k: est_dict.get(k) for k in ProbabilityEstimates.__dataclass_fields__})

    lines = [
        "CLINICAL DECISION SUPPORT REPORT",
        "=" * 60,
        "",
        "CLINICAL QUESTION",
        result.get("pico_statement", ""),
        "",
        "CLINICAL BOTTOM LINE",
        result.get("clinical_bottom_line", ""),
        "",
        "EVIDENCE SUMMARY",
        f"Quality: {result.get('evidence_quality', '')}",
        "",
        result.get("summary", ""),
        "",
        format_probability_table(est),
        "",
        "LIMITATIONS",
        result.get("limitations", ""),
        "",
        "REFERENCES",
    ]
    for i, p in enumerate(result.get("papers_used", []), 1):
        authors = ", ".join((p.get("authors") or [])[:3])
        urls = p.get("urls") or []
        url_str = f"  {urls[0]}" if urls else ""
        lines.append(f"[{i}] {p.get('title', '')} ({authors}, {p.get('year', '')}){url_str}")

    lines += [
        "",
        "─" * 60,
        "DISCLAIMER: AI-assisted tool. Not a substitute for professional medical advice.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
