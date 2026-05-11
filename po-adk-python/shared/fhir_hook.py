"""
FHIR context hook — ADK before_model_callback.

When an A2A caller sends FHIR credentials in the message metadata, this hook
extracts them and stores them in session state so that tools can use them at
call time without the credentials ever appearing in the prompt text.

Metadata key convention (must match the AgentExtension URI in app.py):
    "http://<host>/schemas/a2a/v1/fhir-context": {
        "fhirUrl":   "https://fhir.example.org",
        "fhirToken": "<bearer-token>",
        "patientId": "patient-42"
    }

Set LOG_HOOK_RAW_OBJECTS=true in .env to dump the full llm_request and
callback_context objects to the log (useful when developing a new integration).
"""
import json
import logging
import os

from shared.logging_utils import safe_pretty_json, serialize_for_log, token_fingerprint

logger = logging.getLogger(__name__)

LOG_HOOK_RAW_OBJECTS = os.getenv("LOG_HOOK_RAW_OBJECTS", "false").lower() == "true"

# Must match the AgentExtension URI declared in each agent's app.py.
FHIR_CONTEXT_KEY = "fhir-context"


# ── Private helpers ────────────────────────────────────────────────────────────

def _first_non_empty(*values):
    for v in values:
        if v not in (None, ""):
            return v
    return None


def _safe_correlation_ids(callback_context, llm_request) -> dict:
    return {
        "task_id":    _first_non_empty(getattr(llm_request, "task_id", None),    getattr(callback_context, "task_id", None)),
        "context_id": _first_non_empty(getattr(llm_request, "context_id", None),  getattr(callback_context, "context_id", None)),
        "message_id": _first_non_empty(getattr(llm_request, "message_id", None),  getattr(callback_context, "message_id", None)),
    }


def _coerce_fhir_data(value):
    """Accept either a dict or a JSON string; return a dict or None."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _extract_metadata_sources(callback_context, llm_request) -> list:
    """
    Return candidate metadata dicts in priority order.

    ADK can surface the A2A metadata in several places depending on how the
    request flows through the framework; we check all known locations.
    """
    callback_metadata = getattr(callback_context, "metadata", None)

    run_config      = getattr(callback_context, "run_config", None)
    custom_metadata = getattr(run_config, "custom_metadata", None) if run_config else None
    a2a_metadata    = custom_metadata.get("a2a_metadata") if isinstance(custom_metadata, dict) else None

    llm_payload      = serialize_for_log(llm_request)
    contents         = llm_payload.get("contents", []) if isinstance(llm_payload, dict) else []
    content_metadata = None
    if contents and isinstance(contents, list):
        last = contents[-1]
        if isinstance(last, dict):
            content_metadata = last.get("metadata")

    return [
        ("callback_context.metadata",                                  callback_metadata),
        ("callback_context.run_config.custom_metadata.a2a_metadata",   a2a_metadata),
        ("llm_request.contents[-1].metadata",                          content_metadata),
    ]


# ── Public helper (also used by middleware) ────────────────────────────────────

def extract_fhir_from_payload(payload: dict):
    """
    Extract FHIR context from a raw JSON-RPC payload dict.

    Checks params.metadata first, then params.message.metadata as a fallback.
    Returns (key, fhir_data_dict) or (None, None).
    """
    if not isinstance(payload, dict):
        return None, None
    params = payload.get("params")
    if not isinstance(params, dict):
        return None, None

    for metadata in (params.get("metadata"), (params.get("message") or {}).get("metadata")):
        if isinstance(metadata, dict):
            for key, value in metadata.items():
                if FHIR_CONTEXT_KEY in str(key):
                    return key, _coerce_fhir_data(value)

    return None, None


# ── ADK callback ───────────────────────────────────────────────────────────────

def extract_fhir_context(callback_context, llm_request):
    """
    ADK before_model_callback.

    Reads FHIR credentials from the A2A message metadata and writes them into
    callback_context.state so that tools can call the FHIR server.
    Returns None (does not modify the LLM request).
    """
    correlation      = _safe_correlation_ids(callback_context, llm_request)
    metadata_sources = _extract_metadata_sources(callback_context, llm_request)

    # Walk candidate sources in priority order; use the first non-empty one.
    selected_source = "none"
    metadata        = {}
    for source_name, candidate in metadata_sources:
        if isinstance(candidate, dict) and candidate:
            metadata        = candidate
            selected_source = source_name
            break

    metadata_keys = list(metadata.keys())

    if LOG_HOOK_RAW_OBJECTS:
        logger.info("hook_raw_llm_request=\n%s", safe_pretty_json(serialize_for_log(llm_request)))
        logger.info(
            "hook_raw_callback_context=\n%s",
            safe_pretty_json({
                "task_id":    getattr(callback_context, "task_id", None),
                "context_id": getattr(callback_context, "context_id", None),
                "message_id": getattr(callback_context, "message_id", None),
                "metadata":   serialize_for_log(getattr(callback_context, "metadata", None)),
                "state":      serialize_for_log(getattr(callback_context, "state", None)),
            }),
        )

    logger.info(
        "hook_called_enter task_id=%s context_id=%s message_id=%s metadata_source=%s metadata_keys=%s",
        correlation["task_id"], correlation["context_id"], correlation["message_id"],
        selected_source, metadata_keys,
    )

    if not metadata:
        logger.info(
            "hook_called_no_metadata task_id=%s context_id=%s message_id=%s",
            correlation["task_id"], correlation["context_id"], correlation["message_id"],
        )
        return None

    if not isinstance(metadata, dict):
        logger.warning(
            "hook_called_metadata_invalid_shape task_id=%s context_id=%s message_id=%s metadata_type=%s",
            correlation["task_id"], correlation["context_id"], correlation["message_id"],
            type(metadata).__name__,
        )
        return None

    # Find the FHIR entry inside the metadata dict.
    fhir_data = None
    for key, value in metadata.items():
        if FHIR_CONTEXT_KEY in str(key):
            fhir_data = _coerce_fhir_data(value)
            if fhir_data is None:
                logger.warning(
                    "hook_called_fhir_malformed task_id=%s context_id=%s message_id=%s "
                    "metadata_key=%s value_type=%s",
                    correlation["task_id"], correlation["context_id"], correlation["message_id"],
                    key, type(value).__name__,
                )
            break

    if fhir_data:
        callback_context.state["fhir_url"]   = fhir_data.get("fhirUrl",   "")
        callback_context.state["fhir_token"] = fhir_data.get("fhirToken", "")
        callback_context.state["patient_id"] = fhir_data.get("patientId", "")
        logger.info("FHIR_URL_FOUND value=%s",         callback_context.state["fhir_url"]   or "[EMPTY]")
        logger.info("FHIR_TOKEN_FOUND fingerprint=%s", token_fingerprint(callback_context.state["fhir_token"]))
        logger.info("FHIR_PATIENT_FOUND value=%s",     callback_context.state["patient_id"] or "[EMPTY]")
        logger.info(
            "hook_called_fhir_found task_id=%s context_id=%s message_id=%s "
            "patient_id=%s fhir_url_set=%s fhir_token=%s",
            correlation["task_id"], correlation["context_id"], correlation["message_id"],
            callback_context.state["patient_id"],
            bool(callback_context.state["fhir_url"]),
            token_fingerprint(callback_context.state["fhir_token"]),
        )

        # ── PARALLEL LAYER 1 PREFETCH ─────────────────────────────────────
        # Pre-populate the FHIR cache by fetching ALL 10 resources in
        # parallel BEFORE the LLM starts reasoning. This eliminates the
        # latency of sequential tool calls for Layer 1 data gathering.
        _prefetch_fhir_data(callback_context.state)

    else:
        logger.info(
            "hook_called_fhir_not_found task_id=%s context_id=%s message_id=%s metadata_keys=%s",
            correlation["task_id"], correlation["context_id"], correlation["message_id"],
            metadata_keys,
        )

    logger.info(
        "hook_called_exit task_id=%s context_id=%s message_id=%s patient_id=%s",
        correlation["task_id"], correlation["context_id"], correlation["message_id"],
        callback_context.state.get("patient_id", ""),
    )
    return None


# ── Parallel Layer 1 Prefetch ──────────────────────────────────────────────────

def _prefetch_fhir_data(state: dict):
    """
    Execute all Layer 1 FHIR fetches in parallel using ThreadPoolExecutor.
    Results are stored directly into session state using the same cache keys
    that the Layer 1 tools use, so when the LLM calls them they return instantly.

    This is the async/DAG optimization: Layer 1 tools are independent of each
    other (fetching vitals doesn't require knowing allergies), so we fetch all
    10 resources concurrently.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import time

    fhir_url = state.get("fhir_url", "").rstrip("/")
    fhir_token = state.get("fhir_token", "")
    patient_id = state.get("patient_id", "")

    if not all([fhir_url, fhir_token, patient_id]):
        return

    # Skip if already prefetched this session
    if state.get("_fhir_prefetched"):
        logger.info("prefetch_skipped reason=already_done")
        return

    import httpx

    FHIR_TIMEOUT = 15.0
    CACHE_PREFIX = "_fhir_cache_"

    def _fhir_get_raw(path, params=None):
        try:
            resp = httpx.get(
                f"{fhir_url}/{path}",
                params=params,
                headers={
                    "Authorization": f"Bearer {fhir_token}",
                    "Accept": "application/fhir+json",
                },
                timeout=FHIR_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"entry": [], "_error": str(e)}

    # Define all 10 Layer 1 fetches
    fetches = {
        "demographics": ("Patient", {"_id": patient_id}),
        "medications":  ("MedicationRequest", {"patient": patient_id, "status": "active", "_count": "100"}),
        "conditions":   ("Condition", {"patient": patient_id, "clinical-status": "active", "_count": "100"}),
        "obs_laboratory": ("Observation", {"patient": patient_id, "category": "laboratory", "_count": "50"}),
        "obs_vital-signs": ("Observation", {"patient": patient_id, "category": "vital-signs", "_count": "50"}),
        "obs_social-history": ("Observation", {"patient": patient_id, "category": "social-history", "_count": "20"}),
        "allergies":    ("AllergyIntolerance", {"patient": patient_id, "_count": "50"}),
        "immunizations": ("Immunization", {"patient": patient_id, "_count": "50"}),
        "procedures":   ("Procedure", {"patient": patient_id, "_count": "50"}),
        "encounters":   ("Encounter", {"patient": patient_id, "_count": "20"}),
    }

    start = time.time()
    results = {}

    with ThreadPoolExecutor(max_workers=10) as pool:
        future_to_key = {
            pool.submit(_fhir_get_raw, res_type, params): cache_key
            for cache_key, (res_type, params) in fetches.items()
        }
        for future in as_completed(future_to_key):
            cache_key = future_to_key[future]
            try:
                results[cache_key] = future.result()
            except Exception as e:
                results[cache_key] = {"entry": [], "_error": str(e)}

    # Store raw FHIR bundles in state for the Layer 1 tools to find
    # The Layer 1 tools will check for these and skip the HTTP call
    for cache_key, bundle in results.items():
        state[f"_fhir_prefetch_{cache_key}"] = bundle

    state["_fhir_prefetched"] = True
    elapsed = time.time() - start
    logger.info(
        "prefetch_complete resources=%d time_ms=%d errors=%d",
        len(results),
        int(elapsed * 1000),
        sum(1 for b in results.values() if b.get("_error")),
    )

