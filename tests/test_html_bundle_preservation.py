"""Verify HTML bundle behavior (render_html) is preserved through the v0_2 wrapper."""

from __future__ import annotations

from fastapi.responses import Response

from _live_recovered_app_helper import load_app_module, make_search_request


def test_render_html_flag_is_forwarded_to_baseline_unchanged():
    module = load_app_module({"EVIDENCE_V0_2_ENABLED": "true"})
    seen = {}

    def _capture(req, request, x_api_key):
        seen["render_html"] = req.render_html
        seen["html_profile"] = req.html_profile
        return {"schema_version": "evidence_search_response.v1.5.10", "html": "<html>stub</html>", "source_status": {}, "warnings": []}

    module._BASELINE_SEARCH_ENDPOINT_V02 = _capture
    req = make_search_request(module, query="LCIS", sources=["who"], render_html=True, html_profile="gallery")
    result = module.search_evidence_v02(req, request=None, x_api_key=None)

    assert seen["render_html"] is True
    assert seen["html_profile"] == "gallery"
    assert result["html"] == "<html>stub</html>"


def test_non_dict_html_response_passed_through_untouched():
    """The real _build_html_bundle_response_v1510 can return a raw Response for
    some profiles; the wrapper must not attempt to mutate non-dict responses."""
    module = load_app_module({"EVIDENCE_V0_2_ENABLED": "true"})
    sentinel = Response(content="<html>raw bundle</html>", media_type="text/html")
    module._BASELINE_SEARCH_ENDPOINT_V02 = lambda req, request, x_api_key: sentinel

    req = make_search_request(module, query="LCIS", sources=["who"], render_html=True)
    result = module.search_evidence_v02(req, request=None, x_api_key=None)
    assert result is sentinel


def test_html_bundle_preserved_when_v0_2_disabled():
    module = load_app_module({})  # v0_2 disabled
    module._BASELINE_SEARCH_ENDPOINT_V02 = lambda req, request, x_api_key: {
        "schema_version": "evidence_search_response.v1.5.10",
        "html": "<html>baseline bundle</html>",
    }
    req = make_search_request(module, query="LCIS", sources=["who"], render_html=True)
    result = module.search_evidence_v02(req, request=None, x_api_key=None)
    assert result["html"] == "<html>baseline bundle</html>"
