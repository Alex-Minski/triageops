"""PII masking and prompt-attack detection.

Production path: Amazon Bedrock Guardrails via the ApplyGuardrail API. The
guardrail anonymizes PII (so masked text comes back in `outputs`) and runs the
prompt-attack filter in detect-only mode, so we can flag the ticket for human
review instead of silently dropping it.

Fallback path (no guardrail configured, e.g. local runs and unit tests): a small
regex masker. It is deliberately simple and is NOT a substitute for Guardrails.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_REGEXES = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("IP_ADDRESS", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("PHONE", re.compile(r"(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}\b")),
    ("CREDIT_DEBIT_CARD_NUMBER", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
]

_INJECTION_HINTS = re.compile(
    r"ignore (all |any |the )?(previous|prior|above) (instructions|rules)|"
    r"disregard (your|the) (instructions|system prompt)|you are now|"
    r"set (the )?priority to|mark (this|it) (as )?p[1-4]|system prompt",
    re.IGNORECASE,
)


@dataclass
class GuardrailResult:
    text: str
    intervened: bool = False
    pii_types: list[str] = field(default_factory=list)
    prompt_attack: bool = False
    engine: str = "bedrock-guardrails"


def regex_mask(text: str) -> GuardrailResult:
    found: list[str] = []
    for name, rx in _REGEXES:
        if rx.search(text):
            found.append(name)
            text = rx.sub("{" + name + "}", text)
    attack = bool(_INJECTION_HINTS.search(text))
    return GuardrailResult(text=text, intervened=bool(found) or attack, pii_types=found,
                           prompt_attack=attack, engine="regex-fallback")


def parse_apply_guardrail(original: str, resp: dict) -> GuardrailResult:
    """Turn an ApplyGuardrail response into a GuardrailResult."""
    intervened = resp.get("action") == "GUARDRAIL_INTERVENED"
    outputs = resp.get("outputs") or []
    text = outputs[0]["text"] if intervened and outputs and "text" in outputs[0] else original

    pii: set[str] = set()
    attack = False
    for assessment in resp.get("assessments") or []:
        sip = assessment.get("sensitiveInformationPolicy") or {}
        for ent in sip.get("piiEntities") or []:
            pii.add(ent.get("type", "PII"))
        for rx in sip.get("regexes") or []:
            pii.add(rx.get("name", "REGEX"))
        for flt in (assessment.get("contentPolicy") or {}).get("filters") or []:
            if flt.get("type") == "PROMPT_ATTACK" and (flt.get("detected") or flt.get("action") == "BLOCKED"):
                attack = True
    return GuardrailResult(text=text, intervened=intervened, pii_types=sorted(pii), prompt_attack=attack)


def apply(text: str, guardrail_id: str, guardrail_version: str, client=None) -> GuardrailResult:
    if not guardrail_id:
        return regex_mask(text)
    if client is None:
        from .aws import client as get_client
        client = get_client("bedrock-runtime")
    resp = client.apply_guardrail(
        guardrailIdentifier=guardrail_id,
        guardrailVersion=guardrail_version,
        source="INPUT",
        content=[{"text": {"text": text}}],
    )
    return parse_apply_guardrail(text, resp)
