#!/usr/bin/env python3
"""Build ABPath registry + enrichment human-review package archives."""

from __future__ import annotations

import csv
import hashlib
import json
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_V01 = REPO_ROOT / "06_audits/abpath_content_specs/v0_1"
REVIEW_DIR = AUDIT_V01 / "review_package"
ZIP_PATH = AUDIT_V01 / "abpath_registry_enrichment_v0_1_review_package.zip"
TGZ_PATH = AUDIT_V01 / "abpath_registry_enrichment_v0_1_review_package.tgz"

INCLUDE_ROOTS = (
    REPO_ROOT / "scripts/parse_abpath_ap_content_specs_v0_1.py",
    REPO_ROOT / "scripts/build_abpath_to_curriculum_v0_4_enrichment.py",
    REPO_ROOT / "scripts/build_abpath_enrichment_qa_calibration.py",
    AUDIT_V01,
    REPO_ROOT / "outputs/abpath_registry_v0_1",
)

EXCLUDE_SUFFIXES = {".zip", ".tgz", ".sha256"}
EXCLUDE_NAMES = {
    ZIP_PATH.name,
    TGZ_PATH.name,
}

PROTECTED_V04 = (
    REPO_ROOT / "outputs/curriculum_map_v0_4/curriculum_records_v0_4.jsonl",
    REPO_ROOT / "outputs/curriculum_map_v0_4/curriculum_tag_index_v0_4.sqlite",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fingerprint(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"size": stat.st_size, "mtime": int(stat.st_mtime)}


def should_include(path: Path) -> bool:
    if path.name in EXCLUDE_NAMES:
        return False
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return False
    return True


def iter_package_files() -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    for root in INCLUDE_ROOTS:
        if root.is_file():
            if should_include(root):
                arc = root.relative_to(REPO_ROOT).as_posix()
                files.append((root, arc))
                seen.add(root.resolve())
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or not should_include(path):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append((path, path.relative_to(REPO_ROOT).as_posix()))
    return files


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_zip(files: list[tuple[Path, str]], out_path: Path) -> None:
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for src, arc in files:
            archive.write(src, arcname=arc)


def write_tgz(files: list[tuple[Path, str]], out_path: Path) -> None:
    with tarfile.open(out_path, "w:gz") as archive:
        for src, arc in files:
            archive.add(src, arcname=arc, recursive=False)


def validate(files: list[tuple[Path, str]], before_v04: dict[str, dict[str, int]]) -> dict:
    nested = [arc for _, arc in files if arc.endswith((".zip", ".tgz", ".sha256"))]
    top_level = sorted({arc.split("/")[0] for _, arc in files})
    after_v04 = {str(p): fingerprint(p) for p in PROTECTED_V04}
    required = [
        REVIEW_DIR / "README.md",
        REVIEW_DIR / "MANIFEST.csv",
        AUDIT_V01 / "abpath_ap_content_specs_v0_1_audit.json",
        AUDIT_V01 / "enrichment_to_curriculum_v0_4/abpath_to_curriculum_v0_4_enrichment_audit.json",
        AUDIT_V01 / "enrichment_to_curriculum_v0_4/qa_calibration/abpath_enrichment_high_confidence_sample.csv",
    ]
    return {
        "archives_exist": ZIP_PATH.exists() and TGZ_PATH.exists(),
        "zip_size_bytes": ZIP_PATH.stat().st_size if ZIP_PATH.exists() else 0,
        "tgz_size_bytes": TGZ_PATH.stat().st_size if TGZ_PATH.exists() else 0,
        "file_count": len(files),
        "top_level_entries": top_level,
        "nested_archives_found": nested,
        "review_package_files_present": all(p.exists() for p in required),
        "v0_4_files_modified": before_v04 != after_v04,
        "api_gcs_live_action": False,
    }


def write_manifest(files: list[tuple[Path, str]], manifest_path: Path) -> Path:
    tmp_path = AUDIT_V01 / "_MANIFEST.tmp.csv"
    final_path = AUDIT_V01 / "MANIFEST.csv"
    with tmp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["archive_path", "size_bytes", "sha256"])
        writer.writeheader()
        for src, arc in files:
            writer.writerow(
                {
                    "archive_path": arc,
                    "size_bytes": src.stat().st_size,
                    "sha256": sha256_file(src),
                }
            )
    tmp_path.replace(final_path)
    return final_path


def manifest_archive_entry(manifest_path: Path) -> tuple[Path, str]:
    target_arc = (REVIEW_DIR / "MANIFEST.csv").relative_to(REPO_ROOT).as_posix()
    return manifest_path, target_arc


def main() -> int:
    before_v04 = {str(p): fingerprint(p) for p in PROTECTED_V04}
    files = iter_package_files()
    manifest_path = write_manifest(files, REVIEW_DIR / "MANIFEST.csv")
    manifest_entry = manifest_archive_entry(manifest_path)
    if all(manifest_entry[0] != src for src, _ in files):
        files.append(manifest_entry)
    files = sorted(files, key=lambda item: item[1])
    write_zip(files, ZIP_PATH)
    write_tgz(files, TGZ_PATH)
    ZIP_PATH.with_suffix(ZIP_PATH.suffix + ".sha256").write_text(
        f"{sha256_file(ZIP_PATH)}  {ZIP_PATH.name}\n", encoding="utf-8"
    )
    TGZ_PATH.with_suffix(TGZ_PATH.suffix + ".sha256").write_text(
        f"{sha256_file(TGZ_PATH)}  {TGZ_PATH.name}\n", encoding="utf-8"
    )
    report = validate(files, before_v04)
    report["generated_at_utc"] = utc_now_iso()
    report["zip_sha256"] = sha256_file(ZIP_PATH)
    report["tgz_sha256"] = sha256_file(TGZ_PATH)
    print(json.dumps(report, indent=2))
    if report["nested_archives_found"]:
        raise SystemExit("Nested archives detected in package")
    if report["v0_4_files_modified"]:
        raise SystemExit("Protected v0_4 files changed during packaging")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
