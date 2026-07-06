from datetime import date, datetime
from typing import Any


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _preferred_names(names: list[dict] | None) -> list[dict]:
    """Order name entries so use=official comes first."""
    if not names:
        return []
    return sorted(names, key=lambda n: n.get("use") != "official")


def _first_name(names: list[dict] | None) -> str:
    for name in _preferred_names(names):
        given = name.get("given") or []
        if given:
            return given[0]
    return ""


def _family_name(names: list[dict] | None) -> str:
    for name in _preferred_names(names):
        family = name.get("family")
        if family:
            return family
    return ""


def _is_mrn(identifier: dict) -> bool:
    codings = (identifier.get("type") or {}).get("coding") or []
    return any(coding.get("code") == "MR" for coding in codings)


def _mrn(identifiers: list[dict] | None) -> str:
    """Prefer the identifier explicitly typed as a Medical Record Number."""
    if not identifiers:
        return ""
    with_value = [i for i in identifiers if i.get("value")]
    for ident in with_value:
        if _is_mrn(ident):
            return ident["value"]
    return with_value[0]["value"] if with_value else ""


def transform_patient(fhir_patient: dict[str, Any]) -> dict[str, Any] | None:
    fhir_id = fhir_patient.get("id")
    if not fhir_id:
        return None

    meta = fhir_patient.get("meta") or {}
    return {
        "fhir_id": fhir_id,
        "given_name": _first_name(fhir_patient.get("name")),
        "family_name": _family_name(fhir_patient.get("name")),
        "birth_date": _parse_date(fhir_patient.get("birthDate")),
        "gender": fhir_patient.get("gender") or "unknown",
        "mrn": _mrn(fhir_patient.get("identifier")),
        "source_updated_at": _parse_datetime(meta.get("lastUpdated")),
    }


def _patient_ref_id(reference: str | None) -> str | None:
    if not reference:
        return None
    if reference.startswith("Patient/"):
        return reference.split("/", 1)[1]
    return reference


def _code_info(code_obj: dict | None) -> tuple[str, str]:
    if not code_obj:
        return "", ""
    text = code_obj.get("text") or ""
    codings = code_obj.get("coding") or []
    if codings:
        coding = codings[0]
        code = coding.get("code") or ""
        # Fall back to CodeableConcept.text, then the raw code, so the UI
        # always has something human-readable.
        display = coding.get("display") or text or code
        return code, display
    return text, text


def _codeable_concept_text(concept: dict | None) -> str:
    if not concept:
        return ""
    if concept.get("text"):
        return concept["text"]
    for coding in concept.get("coding") or []:
        if coding.get("display"):
            return coding["display"]
        if coding.get("code"):
            return coding["code"]
    return ""


def _extract_value(resource: dict[str, Any]) -> tuple[float | None, str, str]:
    """Extract (value_numeric, value_text, unit) from a FHIR value[x] choice."""
    quantity = resource.get("valueQuantity")
    if quantity and quantity.get("value") is not None:
        return quantity["value"], "", quantity.get("unit") or quantity.get("code") or ""

    if resource.get("valueInteger") is not None:
        return float(resource["valueInteger"]), "", ""

    if resource.get("valueString"):
        return None, resource["valueString"], ""

    if resource.get("valueBoolean") is not None:
        return None, str(resource["valueBoolean"]).lower(), ""

    concept_text = _codeable_concept_text(resource.get("valueCodeableConcept"))
    if concept_text:
        return None, concept_text, ""

    # Multi-part observations (e.g. blood pressure) carry values in components.
    parts = []
    for component in resource.get("component") or []:
        _, label = _code_info(component.get("code"))
        num, text, unit = _extract_value(component)
        value = text if num is None else f"{num:g}{f' {unit}' if unit else ''}"
        if value:
            parts.append(f"{label}: {value}" if label else value)
    if parts:
        return None, "; ".join(parts), ""

    return None, "", ""


def transform_observation(
    fhir_observation: dict[str, Any],
) -> dict[str, Any] | None:
    fhir_id = fhir_observation.get("id")
    patient_fhir_id = _patient_ref_id(
        (fhir_observation.get("subject") or {}).get("reference")
    )
    if not fhir_id or not patient_fhir_id:
        return None

    code, display = _code_info(fhir_observation.get("code"))
    meta = fhir_observation.get("meta") or {}

    value_numeric, value_text, unit = _extract_value(fhir_observation)

    effective_at = _parse_datetime(fhir_observation.get("effectiveDateTime"))
    if not effective_at:
        period = fhir_observation.get("effectivePeriod") or {}
        effective_at = _parse_datetime(period.get("start"))

    return {
        "fhir_id": fhir_id,
        "patient_fhir_id": patient_fhir_id,
        "code": code,
        "display": display,
        "value_numeric": value_numeric,
        "value_text": value_text,
        "unit": unit,
        "status": fhir_observation.get("status") or "unknown",
        "effective_at": effective_at,
        "source_updated_at": _parse_datetime(meta.get("lastUpdated")),
    }
