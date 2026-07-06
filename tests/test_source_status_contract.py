"""Verify source_status remains interpretable and warnings stay additive."""

from __future__ import annotations

from _live_recovered_app_helper import baseline_response_stub, load_app_module, make_search_request

VALID_SOURCE_STATUS_VALUES = {"ok", "not_requested", "error", "upstream_error", "vector_error", "error_no_upstream"}


def test_source_status_values_remain_within_known_contract():
    module = load_app_module({"EVIDENCE_V0_2_ENABLED": "true"})
    stub_response = baseline_response_stub(
        source_status={
            "who": "ok",
            "journals": "not_requested",
            "pathout": "error",
            "textbooks": "not_requested",
            "curriculum": "not_requested",
        }
    )
    module._BASELINE_SEARCH_ENDPOINT_V02 = lambda req, request, x_api_key: dict(stub_response)

    req = make_search_request(module, query="LCIS", sources=["who"])
    result = module.search_evidence_v02(req, request=None, x_api_key=None)

    for source, status in result["source_status"].items():
        assert status in VALID_SOURCE_STATUS_VALUES, f"unexpected source_status value: {source}={status}"
    # v0_2 must never rewrite source_status values -- it only adds warnings.
    assert result["source_status"]["pathout"] == "error"


def test_existing_warnings_are_preserved_and_v0_2_warnings_are_additive():
    module = load_app_module({"EVIDENCE_V0_2_ENABLED": "true"})

    def _broken_rerank(response, query=None, expansion=None):
        raise RuntimeError("simulated rerank crash")

    module._v02_rerank_who = _broken_rerank
    stub_response = baseline_response_stub(warnings=["baseline_warning_preexisting"])
    module._BASELINE_SEARCH_ENDPOINT_V02 = lambda req, request, x_api_key: dict(stub_response)

    req = make_search_request(module, query="LCIS", sources=["who"])
    result = module.search_evidence_v02(req, request=None, x_api_key=None)

    assert "baseline_warning_preexisting" in result["warnings"]
    assert any("v0_2_who_rerank_failed" in w for w in result["warnings"])
    assert len(result["warnings"]) == 2


def test_source_unavailable_status_never_flips_to_ok_via_v0_2():
    module = load_app_module({"EVIDENCE_V0_2_ENABLED": "true"})
    stub_response = baseline_response_stub(
        source_status={"who": "upstream_error", "journals": "not_requested", "pathout": "not_requested", "textbooks": "not_requested", "curriculum": "not_requested"},
        who_results=[],
    )
    module._BASELINE_SEARCH_ENDPOINT_V02 = lambda req, request, x_api_key: dict(stub_response)

    req = make_search_request(module, query="LCIS", sources=["who"])
    result = module.search_evidence_v02(req, request=None, x_api_key=None)
    assert result["source_status"]["who"] == "upstream_error"
