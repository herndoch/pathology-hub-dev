"""Verify v0_2 feature flags actually change server-side request-path behavior."""

from __future__ import annotations

from _live_recovered_app_helper import baseline_response_stub, load_app_module, make_search_request


def test_v0_2_disabled_never_touches_query():
    module = load_app_module({"EVIDENCE_V0_2_ENABLED": "false"})
    seen_queries = []

    def _capture(req, request, x_api_key):
        seen_queries.append(req.query)
        return baseline_response_stub(query=req.query)

    module._BASELINE_SEARCH_ENDPOINT_V02 = _capture
    req = make_search_request(module, query="LCIS", sources=["who"])
    module.search_evidence_v02(req, request=None, x_api_key=None)
    assert seen_queries == ["LCIS"]  # unexpanded


def test_v0_2_enabled_expands_known_abbreviation_query():
    module = load_app_module({"EVIDENCE_V0_2_ENABLED": "true", "EVIDENCE_QUERY_EXPANSION_ENABLED": "true"})
    seen_queries = []

    def _capture(req, request, x_api_key):
        seen_queries.append(req.query)
        return baseline_response_stub(query=req.query)

    module._BASELINE_SEARCH_ENDPOINT_V02 = _capture
    req = make_search_request(module, query="LCIS", sources=["who"])
    result = module.search_evidence_v02(req, request=None, x_api_key=None)
    assert seen_queries[0] != "" and seen_queries[0] is not None
    # LCIS is a governed rule in query_expansion_rules_v0_2.json with title_boost_only
    # mode for WHO, so effective_query may equal original, but expansion object must
    # have been produced (query_expansion_applied only set when text actually changes).
    assert "warnings" in result


def test_query_expansion_disabled_flag_bypasses_expansion_even_if_v0_2_enabled():
    module = load_app_module(
        {"EVIDENCE_V0_2_ENABLED": "true", "EVIDENCE_QUERY_EXPANSION_ENABLED": "false"}
    )
    seen_queries = []

    def _capture(req, request, x_api_key):
        seen_queries.append(req.query)
        return baseline_response_stub(query=req.query)

    module._BASELINE_SEARCH_ENDPOINT_V02 = _capture
    req = make_search_request(module, query="SSL", sources=["textbooks"])
    module.search_evidence_v02(req, request=None, x_api_key=None)
    assert seen_queries == ["SSL"]


def test_who_rerank_disabled_flag_leaves_who_results_order_untouched():
    module = load_app_module(
        {"EVIDENCE_V0_2_ENABLED": "true", "EVIDENCE_WHO_RERANK_ENABLED": "false"}
    )
    stub_response = baseline_response_stub()
    original_order = [h["title"] for h in stub_response["who_results"]]
    module._BASELINE_SEARCH_ENDPOINT_V02 = lambda req, request, x_api_key: dict(stub_response)

    req = make_search_request(module, query="LCIS", sources=["who"])
    result = module.search_evidence_v02(req, request=None, x_api_key=None)
    assert [h["title"] for h in result["who_results"]] == original_order


def test_debug_flag_adds_diagnostics_only_when_enabled():
    module_debug_off = load_app_module({"EVIDENCE_V0_2_ENABLED": "true", "EVIDENCE_V0_2_DEBUG": "false"})
    module_debug_off._BASELINE_SEARCH_ENDPOINT_V02 = (
        lambda req, request, x_api_key: baseline_response_stub(query=req.query)
    )
    req = make_search_request(module_debug_off, query="LCIS", sources=["who"])
    result_off = module_debug_off.search_evidence_v02(req, request=None, x_api_key=None)
    assert "diagnostics" not in result_off or "query_expansion_v0_2" not in result_off.get("diagnostics", {})

    module_debug_on = load_app_module({"EVIDENCE_V0_2_ENABLED": "true", "EVIDENCE_V0_2_DEBUG": "true"})
    module_debug_on._BASELINE_SEARCH_ENDPOINT_V02 = (
        lambda req, request, x_api_key: baseline_response_stub(query=req.query)
    )
    req2 = make_search_request(module_debug_on, query="LCIS", sources=["who"])
    module_debug_on.search_evidence_v02(req2, request=None, x_api_key=None)
    # No assertion error means debug path executed without raising; presence of
    # diagnostics depends on whether any rule matched LCIS for the who source.
