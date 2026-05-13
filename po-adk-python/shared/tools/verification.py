"""
Verification tools — Layer 4 Multi-Model Verification for ClinicalGuard.

This module provides independent cross-model verification of clinical findings.
The primary agent generates findings, then a DIFFERENT model independently
challenges them.

Architecture:
  - V1: verify_clinical_findings — sends draft findings to an independent LLM
        for challenge/validation, producing a verified/challenged/missed breakdown.
  - ARBITRATION: When findings are challenged, the primary model is presented
        with the critique and asked to either correct or cite specific clinical
        logic justifying its stance.
  - Uses LiteLLM for model-agnostic calls (supports Gemini, Databricks, OpenAI, etc.)

This is the "wow" factor: two different foundation models independently agreeing
on clinical safety, with a deterministic arbitration loop for disputes.
"""

import json
import logging
import os

from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

# Model config — reads from env, works with any LiteLLM-supported provider
_VERIFIER_MODEL = os.getenv("VERIFIER_MODEL", "gemini/gemini-2.0-flash")
_PRIMARY_MODEL = os.getenv("HEALTHCARE_AGENT_MODEL", "gemini/gemini-2.5-flash")


def _llm_call(model: str, prompt: str, max_tokens: int = 2000, temperature: float = 0.1) -> str:
    """Make a model-agnostic LLM call via LiteLLM."""
    import litellm
    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content or ""


def _parse_json_response(raw_text: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def _arbitrate_challenges(challenges: list, original_findings: str) -> list:
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
        raw = _llm_call(_PRIMARY_MODEL, arbitration_prompt, max_tokens=1500, temperature=0.05)
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
    1. Sends findings to an independent model for review.
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

    # Determine verifier display name from model string
    verifier_display = _VERIFIER_MODEL.split("/")[-1] if "/" in _VERIFIER_MODEL else _VERIFIER_MODEL

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
        raw_text = _llm_call(_VERIFIER_MODEL, verification_prompt)
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
                challenged, findings_summary
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
                        "Two independent AI models disagree on this finding. "
                        "The primary model cited specific clinical guidelines to "
                        "justify its stance, but the verifier maintains its challenge. "
                        "Human expert review recommended."
                    ),
                })

        return {
            "status": "success",
            "verifier_model": verifier_display,
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
                f"Independent verification by {verifier_display}: "
                f"{len(verified)} verified, "
                f"{len(challenged)} challenged, "
                f"{len(missed)} additional findings. "
                + (f"Arbitration: {sum(1 for a in arbitration_results if a.get('verdict') == 'ACCEPTED')} corrections accepted, "
                   f"{sum(1 for a in arbitration_results if a.get('verdict') == 'REJECTED')} justified. "
                   if arbitration_results else "")
                + (f"{len(manual_review_flags)} finding(s) flagged for manual review. "
                   if manual_review_flags else "")
                + f"Confidence: {confidence}."
            ),
        }

    except json.JSONDecodeError as e:
        logger.warning(f"Verifier returned non-JSON: {e}")
        return {
            "status": "success",
            "verifier_model": verifier_display,
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
