"""Verify figure/page image URL behavior is preserved through the v0_2 wrapper."""

from __future__ import annotations

from _live_recovered_app_helper import baseline_response_stub, load_app_module, make_search_request


FIGURE_URLS = [
    "https://storage.googleapis.com/pathology_hub/figures/example1.jpg",
    "https://storage.googleapis.com/pathology_hub/figures/example2.jpg",
]


def test_figures_pass_through_unchanged_when_v0_2_enabled():
    module = load_app_module({"EVIDENCE_V0_2_ENABLED": "true"})
    stub_response = baseline_response_stub(
        figures=[{"image_url": u, "caption": "test figure"} for u in FIGURE_URLS]
    )
    module._BASELINE_SEARCH_ENDPOINT_V02 = lambda req, request, x_api_key: dict(stub_response)

    req = make_search_request(module, query="LCIS", sources=["who"], include_figures=True, max_figures=5)
    result = module.search_evidence_v02(req, request=None, x_api_key=None)

    returned_urls = [f["image_url"] for f in result["figures"]]
    assert returned_urls == FIGURE_URLS


def test_no_figures_leak_when_include_figures_false():
    module = load_app_module({"EVIDENCE_V0_2_ENABLED": "true"})
    stub_response = baseline_response_stub(figures=[])
    module._BASELINE_SEARCH_ENDPOINT_V02 = lambda req, request, x_api_key: dict(stub_response)

    req = make_search_request(module, query="LCIS", sources=["who"], include_figures=False, max_figures=0)
    result = module.search_evidence_v02(req, request=None, x_api_key=None)
    assert result["figures"] == []


def test_who_rerank_does_not_alter_figures_field():
    module = load_app_module({"EVIDENCE_V0_2_ENABLED": "true"})
    stub_response = baseline_response_stub(
        figures=[{"image_url": FIGURE_URLS[0], "caption": "unchanged"}]
    )
    module._BASELINE_SEARCH_ENDPOINT_V02 = lambda req, request, x_api_key: dict(stub_response)

    req = make_search_request(module, query="LCIS", sources=["who"], include_figures=True, max_figures=5)
    result = module.search_evidence_v02(req, request=None, x_api_key=None)
    assert result["figures"] == [{"image_url": FIGURE_URLS[0], "caption": "unchanged"}]
