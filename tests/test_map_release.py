"""Regression checks against the actual map inputs and delivered browse identifiers."""
import importlib.util
import json
import unittest
import threading
import tempfile
import urllib.request
import urllib.error
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "frontend/pathology_hub_map_hub_v0_1"
spec = importlib.util.spec_from_file_location("map_builder", ROOT / "scripts/build_unified_content_map_v0_1.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
server_spec = importlib.util.spec_from_file_location("map_server", MAP / "serve.py")
server = importlib.util.module_from_spec(server_spec)
server_spec.loader.exec_module(server)
package_spec = importlib.util.spec_from_file_location("map_package", ROOT / "scripts/package_hub_maps.py")
packager = importlib.util.module_from_spec(package_spec)
package_spec.loader.exec_module(packager)


def walk(node):
    yield node
    for child in node.get("children", []):
        yield from walk(child)


class MapReleaseTests(unittest.TestCase):
    def test_shared_provenance_survives_build(self):
        roots = {}
        builder.add_journals(roots, {"roots": [{"children": [{"kind": "leaf", "tag": "Skin::Test", "label": "Test", "provenance": "both"}]}]})
        leaf = next(n for n in walk(roots["Skin"]) if n["kind"] == "leaf")
        self.assertIsNotNone(leaf["who"])
        self.assertIsNotNone(leaf["pathout"])

    def test_branch_and_topic_remain_independently_addressable(self):
        for reverse in (False, True):
            roots = {}
            paths = [["Skin", "SCC"], ["Skin", "SCC", "Subtype"]]
            for parts in paths[:: -1 if reverse else 1]:
                builder.place_by_parts(roots, parts, parts[-1])
            builder.finalize(roots["Skin"])
            nodes = list(walk(roots["Skin"]))
            self.assertEqual(len(nodes), len({n["node_id"] for n in nodes}))
            self.assertEqual({n["kind"] for n in nodes if n["path"] == "Skin::SCC"}, {"branch", "leaf"})

    def test_delivered_map_preserves_all_shared_sources_and_counts(self):
        data = json.loads((MAP / "content/data/unified_content_map_v0_1.json").read_text())
        nodes = [n for root in data["roots"] for n in walk(root)]
        leaves = [n for n in nodes if n["kind"] == "leaf"]
        self.assertEqual(len(nodes), len({n["node_id"] for n in nodes}))
        self.assertEqual(len(leaves), 5554)
        self.assertEqual(sum(bool(n["who"] and n["pathout"]) for n in leaves), 540)
        self.assertEqual(sum(bool(n["pathout"]) for n in leaves), 2618)
        self.assertEqual(sum(bool(n["who"]) for n in leaves), 1920)
        self.assertEqual(sum(r["id"] == "Cytopathology" for r in data["roots"]), 1)

    def test_original_collision_topics_keep_children_and_samples(self):
        data = json.loads((MAP / "content/data/unified_content_map_v0_1.json").read_text())
        nodes = [n for root in data["roots"] for n in walk(root)]
        for path in ("Skin::Epidermal_Neoplasm::Squamous_Cell_Carcinoma", "Skin::Inflammatory::Granulomatous"):
            pair = {n["kind"]: n for n in nodes if n["path"] == path}
            self.assertTrue(pair["branch"]["children"])
            self.assertTrue(pair["leaf"]["textbook_items"] or pair["leaf"]["who"] or pair["leaf"]["pathout"])
            if path.endswith("Granulomatous"):
                self.assertEqual(len(pair["leaf"]["textbook_items"]), 8)


class DeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), partial(server.Handler, directory=str(MAP)))
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.http.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()

    def test_legacy_routes_open_the_canonical_filters(self):
        for old, target in [("/textbooks/", "/content/"), ("/journals/", "/content/?source=references")]:
            with urllib.request.urlopen(self.base + old) as response:
                self.assertEqual(response.url, self.base + target)
                self.assertEqual(response.status, 200)

    def test_health_and_head(self):
        with urllib.request.urlopen(self.base + "/health") as response:
            self.assertEqual(json.load(response)["status"], "ok")
        for route in ("/", "/health", "/content/", "/videos/"):
            with urllib.request.urlopen(urllib.request.Request(self.base + route, method="HEAD")) as response:
                self.assertEqual(response.read(), b"")
                self.assertEqual(response.status, 200)

    def test_videos_route_and_shared_navigation(self):
        with urllib.request.urlopen(self.base + "/videos/") as response:
            body = response.read().decode()
        self.assertEqual(response.status, 200)
        self.assertIn("/static/navigation.js", body)
        self.assertIn("/static/tokens.css", body)
        for page in ("index.html", "content/index.html", "lectures/index.html", "videos/index.html"):
            self.assertIn("/static/tokens.css", (MAP / page).read_text(), page)

    def test_private_paths_and_directory_indexes_not_served(self):
        for route in ("/.env", "/serve.py", "/static/", "/content/../.env"):
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(self.base + route)
            self.assertEqual(error.exception.code, 404)
            error.exception.close()

    def test_portable_package_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = packager.package(Path(tmp) / "hub.zip")
        names = set(manifest["files"])
        self.assertIn("serve.py", names)
        self.assertIn("content/data/unified_content_map_v0_1.json", names)
        self.assertFalse(any(n.startswith(("textbooks/", "journals/")) for n in names))


if __name__ == "__main__":
    unittest.main()
