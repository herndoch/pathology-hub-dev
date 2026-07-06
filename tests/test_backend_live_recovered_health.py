"""Local /health test for backend/pathology_hub_v04_live_recovered/app.py."""

from __future__ import annotations

from _live_recovered_app_helper import load_app_module


def test_health_returns_v1510_baseline_fields_when_v0_2_disabled():
    module = load_app_module({})  # EVIDENCE_V0_2_ENABLED defaults to false
    module._BASELINE_HEALTH_ENDPOINT_V02 = lambda: {
        "schema_version": "pathology_hub_health.v1.5.10",
        "service": "pathology-hub-v04",
        "version": "1.5.10-html-bundle",
        "loaded": True,
    }
    result = module.health_v02()
    assert result["schema_version"] == "pathology_hub_health.v1.5.10"
    assert result["version"] == "1.5.10-html-bundle"
    assert result["loaded"] is True
    assert result["evidence_v0_2_enabled"] is False
    assert result["evidence_v0_2_module_loaded"] is False


def test_health_reports_v0_2_flags_when_enabled():
    module = load_app_module({"EVIDENCE_V0_2_ENABLED": "true", "EVIDENCE_WHO_RERANK_ENABLED": "false"})
    module._BASELINE_HEALTH_ENDPOINT_V02 = lambda: {"version": "1.5.10-html-bundle", "loaded": True}
    result = module.health_v02()
    assert result["evidence_v0_2_enabled"] is True
    assert result["evidence_v0_2_module_loaded"] is True
    assert result["evidence_query_expansion_enabled"] is True
    assert result["evidence_root_gating_enabled"] is True
    assert result["evidence_who_rerank_enabled"] is False


def test_health_survives_baseline_health_exception():
    module = load_app_module({})

    def _boom():
        raise RuntimeError("index not loaded")

    module._BASELINE_HEALTH_ENDPOINT_V02 = _boom
    result = module.health_v02()
    assert "baseline_health_error" in result
    assert result["evidence_v0_2_enabled"] is False
