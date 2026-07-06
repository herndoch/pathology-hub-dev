"""Verify baseline search always still returns results if v0_2 fails internally.

Mission requirement: "if v0_2 fails for any reason, baseline search must still
return results with an explicit warning field -- no source becomes unavailable
solely because v0_2 fails."
"""

from __future__ import annotations

from _live_recovered_app_helper import baseline_response_stub, load_app_module, make_search_request


def test_v0_2_module_import_failure_falls_back_to_baseline_with_warning():
    module = load_app_module({"EVIDENCE_V0_2_ENABLED": "true"})
    # Simulate an import failure discovered at runtime (e.g. corrupted module).
    module._V02_MODULE_LOADED = False
    module._V02_IMPORT_ERROR = "simulated_import_failure_for_test"
    stub_response = baseline_response_stub()
    module._BASELINE_SEARCH_ENDPOINT_V02 = lambda req, request, x_api_key: dict(stub_response)

    req = make_search_request(module, query="LCIS", sources=["who"])
    result = module.search_evidence_v02(req, request=None, x_api_key=None)

    assert result["source_status"]["who"] == "ok"
    assert result["who_results"], "baseline results must still be returned"
    assert any("v0_2_unavailable_baseline_used" in w for w in result["warnings"])


def test_query_expansion_exception_falls_back_to_original_query_with_warning():
    module = load_app_module({"EVIDENCE_V0_2_ENABLED": "true"})

    def _broken_preprocess(payload, config=None):
        raise RuntimeError("simulated expansion crash")

    module._v02_preprocess = _broken_preprocess
    seen_queries = []

    def _capture(req, request, x_api_key):
        seen_queries.append(req.query)
        return baseline_response_stub(query=req.query)

    module._BASELINE_SEARCH_ENDPOINT_V02 = _capture
    req = make_search_request(module, query="LCIS", sources=["who"])
    result = module.search_evidence_v02(req, request=None, x_api_key=None)

    assert seen_queries == ["LCIS"], "must dispatch with original query on expansion failure"
    assert any("v0_2_query_expansion_failed_using_baseline_query" in w for w in result["warnings"])
    assert result["who_results"], "results must still be returned"


def test_expanded_query_dispatch_failure_retries_original_query():
    module = load_app_module({"EVIDENCE_V0_2_ENABLED": "true"})
    calls = []

    def _flaky_baseline(req, request, x_api_key):
        calls.append(req.query)
        if len(calls) == 1:
            raise RuntimeError("simulated dispatch failure on expanded query")
        return baseline_response_stub(query=req.query)

    module._BASELINE_SEARCH_ENDPOINT_V02 = _flaky_baseline
    req = make_search_request(module, query="LCIS", sources=["who"])
    result = module.search_evidence_v02(req, request=None, x_api_key=None)

    assert len(calls) == 2, "must retry once with original query after dispatch failure"
    assert result["who_results"], "a source must never become unavailable solely because v0_2 failed"
    assert any("v0_2_expanded_query_dispatch_failed_retried_original_query" in w for w in result["warnings"])


def test_who_rerank_exception_still_returns_baseline_results_with_warning():
    module = load_app_module({"EVIDENCE_V0_2_ENABLED": "true"})

    def _broken_rerank(response, query=None, expansion=None):
        raise RuntimeError("simulated rerank crash")

    module._v02_rerank_who = _broken_rerank
    stub_response = baseline_response_stub()
    module._BASELINE_SEARCH_ENDPOINT_V02 = lambda req, request, x_api_key: dict(stub_response)

    req = make_search_request(module, query="LCIS", sources=["who"])
    result = module.search_evidence_v02(req, request=None, x_api_key=None)

    assert result["who_results"], "results must survive a rerank crash"
    assert any("v0_2_who_rerank_failed_baseline_ranking_used" in w for w in result["warnings"])
