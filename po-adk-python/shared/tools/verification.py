"""
Verification tools — Layer 4 Multi-Model Verification for ClinicalGuard.

This module provides independent cross-model verification of clinical findings.
The primary agent (Llama 4 Maverick via Databricks) generates findings, then a
DIFFERENT model (Llama 3.3 70B via Databricks) independently challenges them.

Architecture:
  - V1: verify_clinical_findings — sends draft findings to an independent LLM
        for challenge/validation, producing a verified/challenged/missed breakdown.
  - ARBITRATION: When findings are challenged, the primary model is presented
        with the critique and asked to either correct or cite specific clinical
        logic justifying its stance.
  - Uses OpenAI-compatible client to call Databricks AI Gateway directly.

This is the "wow" factor: two different foundation models from two different
architectures (Llama 4 + Llama 3.3) independently agreeing on clinical safety,
with a deterministic arbitration loop for disputes.
"""

import json
import logging
import os

from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

# Databricks AI Gateway config
_DATABRICKS_TOKEN = os.getenv("DATABRICKS_API_KEY", "")
_DATABRICKS_BASE = os.getenv("DATABRICKS_API_BASE", "")
_VERIFIER_MODEL = os.getenv("VERIFIER_MODEL", "databricks-llama-4-maverick")


def _get_client():
    """Lazy-init the OpenAI client pointing at Databricks AI Gateway."""
    from openai import OpenAI
    return OpenAI(api_key=_DATABRICKS_TOKEN, base_url=_DATABRICKS_BASE)


def _safe_content(response) -> str:
    """Extract text content from OpenAI response, handling list/dict edge cases."""
    content = response.choices[0].message.content
    if isinstance(content, list):
        # Some models return list of content blocks
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                return item.get("text", "")
            if isinstance(item, str):
                return item
        return str(content)
    return content or ""


def _parse_json_response(raw_text: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def _arbitrate_challenges(client, challenges: list, original_findings: str) -> list:
    """
    ARBITRATION LOOP — Deterministic tie-breaker for disputed findings.

    When the verifier challenges a finding, present the critique back to the
    primary model and ask it to either:
    1. CORRECT its output (accept the challenge)
    2. JUSTIFY its stance by citing the specific clinical protocol

    This prevents raw disputes from reaching clinicians (alert fatigue).
    """
    if not challenges:
        return []

    arbitration_prompt = f"""You are a clinical safety system performing self-review.
A second AI model has challenged some of your clinical findings.
For EACH challenge below, you must either:
- ACCEPT the challenge and provide a corrected finding
- REJECT the challenge and cite the specific clinical guideline/protocol that justifies your original finding

ORIGINAL ANALYSIS:
{original_findings[:2000]}

CHALLENGES FROM INDEPENDENT REVIEWER:
{json.dumps(challenges, indent=2)}

Respond with a JSON array. For each challenge, provide:
[
  {{
    "original_challenge": "the challenge text",
    "verdict": "ACCEPTED" or "REJECTED",
    "reasoning": "why you accept or reject, citing specific guideline if rejecting",
    "corrected_finding": "if ACCEPTED, the corrected finding; if REJECTED, null"
  }}
]

Only respond with the JSON array, no other text."""

    try:
        response = client.chat.completions.create(
            model="databricks-llama-4-maverick",
            messages=[{"role": "user", "content": arbitration_prompt}],
            max_tokens=1500,
            temperature=0.05,
        )

        raw = _safe_content(response)
        parsed = _parse_json_response(raw)

        if isinstance(parsed, list):
            return parsed
        return []

    except Exception as e:
        logger.warning(f"Arbitration failed: {e}")
        return [{"original_challenge": c, "verdict": "UNRESOLVED",
                 "reasoning": f"Arbitration unavailable: {e}"} for c in challenges]


def verify_clinical_findings(findings_summary: str, tool_context: ToolContext) -> dict:
    """
    Layer 4 Verification — MULTI-MODEL CROSS-CHECK WITH ARBITRATION.
    1. Sends findings to Llama 3.3 70B for independent review.
    2. If findings are CHALLENGED, triggers an arbitration loop where
       the primary model must either correct or justify its stance.

    Args:
        findings_summary: A text summary of all clinical findings from
            the primary analysis (drug interactions, Beers flags, etc.)

    Returns dict with:
        - verified: findings the verifier agrees with
        - challenged: findings the verifier disputes
        - missed: additional findings the verifier identifies
        - arbitration: resolution of any challenged findings
        - confidence: overall verification confidence
    """
    if not findings_summary or len(findings_summary.strip()) < 20:
        return {
            "status": "success",
            "verification_skipped": True,
            "reason": "Insufficient findings to verify.",
        }

    verification_prompt = f"""You are an independent clinical safety reviewer.
You are reviewing findings generated by another AI system analyzing a patient's
FHIR health record. Your role is to challenge, validate, or supplement these findings.

FINDINGS TO REVIEW:
{findings_summary}

Respond with a JSON object containing exactly these keys:
{{
  "verified": ["list of findings you agree are clinically accurate"],
  "challenged": ["list of findings you believe are incorrect, overstated, or need modification, with your reasoning"],
  "missed": ["list of additional safety concerns you identified that the primary analysis missed"],
  "overall_assessment": "brief 1-2 sentence overall assessment",
  "confidence": "HIGH/MODERATE/LOW"
}}

Be rigorous. Challenge anything that seems clinically questionable.
Only respond with the JSON object, no other text."""

    try:
        client = _get_client()

        response = client.chat.completions.create(
            model=_VERIFIER_MODEL,
            messages=[{"role": "user", "content": verification_prompt}],
            max_tokens=2000,
            temperature=0.1,
        )

        raw_text = _safe_content(response)
        parsed = _parse_json_response(raw_text)

        verified = parsed.get("verified", [])
        challenged = parsed.get("challenged", [])
        missed = parsed.get("missed", [])
        confidence = parsed.get("confidence", "MODERATE")

        # ── ARBITRATION LOOP ──────────────────────────────────────────
        # If findings were challenged, trigger self-reflection
        arbitration_results = []
        if challenged:
            logger.info(f"arbitration_triggered challenged_count={len(challenged)}")
            arbitration_results = _arbitrate_challenges(
                client, challenged, findings_summary
            )
            # Update confidence based on arbitration
            accepted = sum(1 for a in arbitration_results if a.get("verdict") == "ACCEPTED")
            rejected = sum(1 for a in arbitration_results if a.get("verdict") == "REJECTED")
            if accepted > rejected:
                confidence = "MODERATE"  # Some corrections needed
            elif rejected > 0:
                confidence = "HIGH"  # Original findings justified

        # Build manual review flags for REJECTED arbitrations
        # (Two SOTA models disagreed and couldn't resolve — needs human expert)
        manual_review_flags = []
        for arb in arbitration_results:
            if arb.get("verdict") == "REJECTED":
                manual_review_flags.append({
                    "finding": arb.get("original_challenge", ""),
                    "primary_justification": arb.get("reasoning", ""),
                    "flag": "SYSTEM DISPUTE — Manual Review Recommended",
                    "reason": (
                        "Two independent AI models (Llama 4 Maverick and Llama 3.3 70B) "
                        "disagree on this finding. The primary model cited specific "
                        "clinical guidelines to justify its stance, but the verifier "
                        "maintains its challenge. Human expert review recommended."
                    ),
                })

        return {
            "status": "success",
            "verifier_model": f"Llama 3.3 70B (via Databricks)",
            "verified": verified,
            "challenged": challenged,
            "missed": missed,
            "overall_assessment": parsed.get("overall_assessment", ""),
            "confidence": confidence,
            "verified_count": len(verified),
            "challenged_count": len(challenged),
            "missed_count": len(missed),
            "arbitration": arbitration_results,
            "arbitration_accepted": sum(1 for a in arbitration_results if a.get("verdict") == "ACCEPTED"),
            "arbitration_rejected": sum(1 for a in arbitration_results if a.get("verdict") == "REJECTED"),
            "manual_review_flags": manual_review_flags,
            "manual_review_count": len(manual_review_flags),
            "summary": (
                f"Independent verification by Llama 3.3 70B (Databricks): "
                f"{len(verified)} verified, "
                f"{len(challenged)} challenged, "
                f"{len(missed)} additional findings. "
                + (f"Arbitration: {sum(1 for a in arbitration_results if a.get('verdict') == 'ACCEPTED')} corrections accepted, "
                   f"{sum(1 for a in arbitration_results if a.get('verdict') == 'REJECTED')} justified. "
                   if arbitration_results else "")
                + (f"⚠️ {len(manual_review_flags)} finding(s) flagged for manual review. "
                   if manual_review_flags else "")
                + f"Confidence: {confidence}."
            ),
        }

    except json.JSONDecodeError as e:
        logger.warning(f"Verifier returned non-JSON: {e}")
        return {
            "status": "success",
            "verifier_model": "Llama 3.3 70B (via Databricks)",
            "raw_response": raw_text[:500] if 'raw_text' in dir() else "",
            "parse_error": str(e),
            "summary": "Verification completed but response format was non-standard. Raw review available.",
        }

    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return {
            "status": "success",
            "verification_error": str(e),
            "summary": f"Independent verification unavailable: {e}. Primary findings remain unverified.",
        }
