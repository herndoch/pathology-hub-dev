"""Local /evidence/search contract test for the recovered backend."""

from __future__ import annotations

from _live_recovered_app_helper import baseline_response_stub, load_app_module, make_search_request


def test_search_returns_baseline_response_unmodified_when_v0_2_disabled():
    module = load_app_module({})  # v0_2 disabled by default
    stub_response = baseline_response_stub()
    module._BASELINE_SEARCH_ENDPOINT_V02 = lambda req, request, x_api_key: dict(stub_response)

    req = make_search_request(module)
    result = module.search_evidence_v02(req, request=None, x_api_key=None)

    assert result["schema_version"] == "evidence_search_response.v1.5.10"
    assert result["source_status"]["who"] == "ok"
    assert result["who_results"][0]["title"] == "Lobular carcinoma in situ"
    assert result["warnings"] == []


def test_search_contract_preserves_required_top_level_fields():
    module = load_app_module({"EVIDENCE_V0_2_ENABLED": "true"})
    stub_response = baseline_response_stub()
    module._BASELINE_SEARCH_ENDPOINT_V02 = lambda req, request, x_api_key: dict(stub_response)

    req = make_search_request(module)
    result = module.search_evidence_v02(req, request=None, x_api_key=None)

    for field in ("schema_version", "source_status", "who_results", "warnings"):
        assert field in result, f"missing required field: {field}"
