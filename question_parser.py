"""
Clinical question parser.

Takes free text and uses Claude to:
1. Ask clarifying questions to pin down PICO elements.
2. Return a structured ClinicalQuestion with a search query for Elicit.
"""

import json
import os
from typing import Optional, List, Tuple
import anthropic
from dataclasses import dataclass, asdict
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
You are a clinical informaticist helping physicians formulate structured clinical questions
for evidence-based medicine using the PICO framework:

  P – Patient / Population
  I – Intervention (therapy, drug, procedure) OR Index test (for diagnostic questions)
  C – Comparison (standard of care, placebo, or alternative test)
  O – Outcome (clinical endpoint that matters)
  T – Time frame (optional)
  Context – Clinical setting (ICU, general ward, outpatient clinic, emergency dept, etc.)
  Question type – Therapeutic, Diagnostic, Prognostic, or Harm

Your job:
1. Extract the PICO elements from the user's text as precisely as possible.
2. If any element is missing or ambiguous, identify it and formulate a single clarifying
   question to resolve the most important gap. Do NOT ask multiple questions at once.
3. Once all elements are sufficiently clear, produce a final structured JSON output.

Always respond with valid JSON in one of two forms:

A) When clarification is needed:
{
  "status": "needs_clarification",
  "identified": {
    "population": "...",
    "intervention": "...",
    "comparison": "...",
    "outcome": "...",
    "timeframe": "...",
    "context": "...",
    "question_type": "..."
  },
  "clarifying_question": "..."
}

B) When the question is complete:
{
  "status": "complete",
  "population": "...",
  "intervention": "...",
  "comparison": "...",
  "outcome": "...",
  "timeframe": "...",
  "context": "...",
  "question_type": "therapeutic|diagnostic|prognostic|harm",
  "pico_statement": "In [P], does [I] compared to [C] reduce/improve [O] within [T]?",
  "elicit_search_query": "..."
}

The elicit_search_query should be a concise natural-language string optimised for
semantic search over 138 million academic papers.
"""


@dataclass
class ClinicalQuestion:
    population: str
    intervention: str
    comparison: str
    outcome: str
    timeframe: str
    context: str
    question_type: str
    pico_statement: str
    elicit_search_query: str

    def to_dict(self) -> dict:
        return asdict(self)


def parse_question(
    free_text: str,
    interactive: bool = True,
    max_clarifications: int = 3,
) -> Tuple[Optional["ClinicalQuestion"], List[dict]]:
    """
    Parse free text into a structured ClinicalQuestion.

    Args:
        free_text: The physician's raw clinical query.
        interactive: If True, print clarifying questions to stdout and read
                     answers from stdin. If False, proceed with best guess.
        max_clarifications: Maximum clarifying rounds before forcing completion.

    Returns:
        (ClinicalQuestion, conversation_history)
        ClinicalQuestion is None only if the model cannot produce a complete
        question after max_clarifications rounds.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    messages: list[dict] = [{"role": "user", "content": free_text}]
    history: list[dict] = list(messages)

    for round_num in range(max_clarifications + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        raw = response.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: ask the model to return JSON only
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": "Please return ONLY valid JSON, no other text.",
                }
            )
            history.append({"role": "assistant", "content": raw})
            continue

        history.append({"role": "assistant", "content": raw})

        if parsed.get("status") == "complete":
            q = ClinicalQuestion(
                population=parsed.get("population", ""),
                intervention=parsed.get("intervention", ""),
                comparison=parsed.get("comparison", ""),
                outcome=parsed.get("outcome", ""),
                timeframe=parsed.get("timeframe", ""),
                context=parsed.get("context", "hospital"),
                question_type=parsed.get("question_type", "therapeutic"),
                pico_statement=parsed.get("pico_statement", ""),
                elicit_search_query=parsed.get("elicit_search_query", free_text),
            )
            return q, history

        if parsed.get("status") == "needs_clarification":
            clarifying_q = parsed.get("clarifying_question", "")
            if not clarifying_q or not interactive or round_num >= max_clarifications:
                # Force completion on final round
                force_msg = (
                    "Based on the information available, please now produce the "
                    "complete structured JSON (status: complete) using your best "
                    "clinical judgement for any missing elements."
                )
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": force_msg})
                history.append({"role": "user", "content": force_msg})
                continue

            print(f"\nClarification needed: {clarifying_q}")
            answer = input("Your answer: ").strip()
            if not answer:
                answer = "Not specified."

            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": answer})
            history.append({"role": "user", "content": answer})

    return None, history


def parse_question_non_interactive(free_text: str) -> ClinicalQuestion:
    """
    Parse free text without interaction — uses Claude's best clinical judgement
    for any missing PICO elements.  Used by the web API and CLI non-interactive mode.
    """
    q, _ = parse_question(free_text, interactive=False, max_clarifications=2)
    if q is None:
        # Last-resort fallback
        q = ClinicalQuestion(
            population="patients",
            intervention=free_text,
            comparison="standard care",
            outcome="clinical outcome",
            timeframe="",
            context="hospital",
            question_type="therapeutic",
            pico_statement=f"What is the evidence regarding: {free_text}",
            elicit_search_query=free_text,
        )
    return q
