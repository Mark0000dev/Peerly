"""Synthetic installed metadata only; never compiles or installs an SDK."""

import hashlib
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from xml.etree import ElementTree as ET

from native_android_sdk_preflight import (
    MAX_RECORD,
    MAX_XML,
    SDKPreflightError,
    inspect_sdk,
    parse_metadata,
)


class InstalledLicenseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def make_sdk(self, platform_text: str, tools_text: str | None = None) -> None:
        texts = (platform_text, platform_text if tools_text is None else tools_text)
        hashes = {
            hashlib.sha1(text.encode(), usedforsecurity=False).hexdigest()
            for text in texts
        }
        record = self.root / "licenses/android-sdk-license"
        record.parent.mkdir(parents=True)
        record.write_text("\n" + "\n".join(sorted(hashes)) + "\n")
        for directory, package, terms, properties in [
            (
                "platforms/android-36",
                "platforms;android-36",
                texts[0],
                "AndroidVersion.ApiLevel=36\n",
            ),
            (
                "build-tools/36.0.0",
                "build-tools;36.0.0",
                texts[1],
                "Pkg.Revision=36.0.0\n",
            ),
        ]:
            target = self.root / directory
            target.mkdir(parents=True)
            metadata = ET.Element("repository")
            ET.SubElement(
                metadata, "license", {"id": "android-sdk-license", "type": "text"}
            ).text = terms
            local = ET.SubElement(metadata, "localPackage", {"path": package})
            ET.SubElement(local, "uses-license", {"ref": "android-sdk-license"})
            ET.ElementTree(metadata).write(target / "package.xml", encoding="utf-8")
            (target / "source.properties").write_text(properties)
        (self.root / "platforms/android-36/android.jar").write_bytes(
            b"synthetic, never compiled"
        )
        for name in ("aapt2", "apksigner"):
            path = self.root / "build-tools/36.0.0" / name
            path.write_text("synthetic, never executed")
            path.chmod(448)

    def test_old_installed_accepted_terms_do_not_require_online_new_terms(self) -> None:
        self.make_sdk("Synthetic old installed terms")
        report = inspect_sdk(self.root)
        if not report.accepted:
            raise AssertionError("SDK provenance expectation failed")
        if not all(package.metadata_sha256 for package in report.packages):
            raise AssertionError("SDK provenance expectation failed")
        if not all(
            check.accepted for package in report.packages for check in package.licenses
        ):
            raise AssertionError("SDK provenance expectation failed")

    def test_new_installed_accepted_terms_are_checked_the_same_way(self) -> None:
        self.make_sdk("Synthetic new installed terms")
        if not inspect_sdk(self.root).accepted:
            raise AssertionError("SDK provenance expectation failed")

    def test_each_installed_package_hash_must_be_recorded(self) -> None:
        self.make_sdk("Old platform terms", "New build tools terms")
        if not inspect_sdk(self.root).accepted:
            raise AssertionError("SDK provenance expectation failed")
        path = self.root / "licenses/android-sdk-license"
        path.write_text(
            hashlib.sha1(b"Old platform terms", usedforsecurity=False).hexdigest()
            + "\n"
        )
        report = inspect_sdk(self.root)
        if report.accepted:
            raise AssertionError("SDK provenance expectation failed")
        if not report.packages[0].licenses[0].accepted:
            raise AssertionError("SDK provenance expectation failed")
        if report.packages[1].licenses[0].accepted:
            raise AssertionError("SDK provenance expectation failed")

    def test_mismatched_record_is_not_an_old_hash_allowlist(self) -> None:
        self.make_sdk("Installed terms")
        (self.root / "licenses/android-sdk-license").write_text(
            "24333f8a63b6825ea9c5514f83c2829b004d1fee\n"
        )
        if inspect_sdk(self.root).accepted:
            raise AssertionError("SDK provenance expectation failed")

    def test_license_text_is_exact_not_trimmed_or_whitespace_collapsed(self) -> None:
        self.make_sdk(" \nExact & decoded terms\n ")
        if not inspect_sdk(self.root).accepted:
            raise AssertionError("SDK provenance expectation failed")
        digest = hashlib.sha1(
            b"Exact & decoded terms", usedforsecurity=False
        ).hexdigest()
        (self.root / "licenses/android-sdk-license").write_text(digest + "\n")
        if inspect_sdk(self.root).accepted:
            raise AssertionError("SDK provenance expectation failed")
        exact = hashlib.sha1(
            b" \nExact & decoded terms\n ", usedforsecurity=False
        ).hexdigest()
        for record in [" " + exact + "\n", exact + "\u2028not-a-java-line"]:
            (self.root / "licenses/android-sdk-license").write_text(record)
            if inspect_sdk(self.root).accepted:
                raise AssertionError(
                    "Whitespace or Unicode separator bypassed exact record match"
                )

    def test_missing_license_reference_or_text_fails_closed(self) -> None:
        self.make_sdk("Installed terms")
        path = self.root / "platforms/android-36/package.xml"
        original = path.read_bytes()
        for replacement in [
            b'<repository><localPackage path="platforms;android-36"/></repository>',
            (
                b'<repository><localPackage path="platforms;android-36">'
                b'<uses-license ref="unknown"/></localPackage></repository>'
            ),
        ]:
            with self.subTest(metadata=replacement[:20]):
                path.write_bytes(replacement)
                if inspect_sdk(self.root).accepted:
                    raise AssertionError("SDK provenance expectation failed")
        path.write_bytes(original)
        (self.root / "licenses/android-sdk-license").unlink()
        if inspect_sdk(self.root).accepted:
            raise AssertionError("SDK provenance expectation failed")

    def test_dtd_entities_malformed_and_oversized_metadata_rejected(self) -> None:
        for data in [
            b'<!DOCTYPE repository [<!ENTITY external SYSTEM "file:///never/read">]><repository/>',
            b'<!ENTITY x "value"><repository/>',
            b"<malformed",
            b"\x00<repository/>",
            b"x" * (MAX_XML + 1),
        ]:
            with self.subTest(size=len(data)):
                try:
                    parse_metadata(data)
                except SDKPreflightError as error:
                    if not str(error):
                        raise AssertionError(
                            "Expected a fixed rejection code"
                        ) from error
                else:
                    raise AssertionError("Malformed/declarative XML was accepted")

    def test_safe_diagnostic_contains_hashes_not_license_contents_or_urls(self) -> None:
        terms = "SYNTHETIC_LICENSE_CANARY https://never-output.invalid/body"
        self.make_sdk(terms)
        (self.root / "licenses/android-sdk-license").write_text(
            "SYNTHETIC_RECORD_CANARY\n"
        )
        report = inspect_sdk(self.root)
        text = json.dumps(asdict(report))
        if report.accepted:
            raise AssertionError("SDK provenance expectation failed")
        if not "CANARY" not in text:
            raise AssertionError("SDK provenance expectation failed")
        if not "https://" not in text:
            raise AssertionError("SDK provenance expectation failed")
        if not all(package.metadata_sha256 for package in report.packages):
            raise AssertionError("SDK provenance expectation failed")
        if not report.packages[0].licenses[0].record_sha256 is not None:
            raise AssertionError("SDK provenance expectation failed")

    def test_metadata_drift_is_bound_and_missing_package_cannot_borrow_license(
        self,
    ) -> None:
        self.make_sdk("Installed terms")
        before = inspect_sdk(self.root)
        path = self.root / "platforms/android-36/package.xml"
        path.write_text(path.read_text() + "\n")
        after = inspect_sdk(self.root)
        if not after.accepted:
            raise AssertionError("SDK provenance expectation failed")
        if not before.packages[0].metadata_sha256 != after.packages[0].metadata_sha256:
            raise AssertionError("SDK provenance expectation failed")
        path.unlink()
        if inspect_sdk(self.root).accepted:
            raise AssertionError("SDK provenance expectation failed")

    def test_namespaced_installed_package_metadata(self) -> None:
        self.make_sdk("Installed namespaced terms")
        for package in ("platforms/android-36", "build-tools/36.0.0"):
            path = self.root / package / "package.xml"
            path.write_text(
                path.read_text().replace(
                    "<repository>", '<repository xmlns="urn:synthetic-sdk">', 1
                )
            )
        if not inspect_sdk(self.root).accepted:
            raise AssertionError("Namespaced installed package was rejected")

    def test_file_bounds_and_missing_tools_fail_closed(self) -> None:
        self.make_sdk("Installed terms")
        path = self.root / "platforms/android-36/package.xml"
        original = path.read_bytes()
        path.write_bytes(b"x" * (MAX_XML + 1))
        if inspect_sdk(self.root).accepted:
            raise AssertionError("Oversized metadata was accepted")
        path.write_bytes(original)
        (self.root / "licenses/android-sdk-license").write_bytes(
            b"x" * (MAX_RECORD + 1)
        )
        if inspect_sdk(self.root).accepted:
            raise AssertionError("Oversized record was accepted")
        (self.root / "build-tools/36.0.0/aapt2").unlink()
        if inspect_sdk(self.root).accepted:
            raise AssertionError("Missing build tool was accepted")

    def test_license_symlink_cannot_read_outside_sdk(self) -> None:
        self.make_sdk("Installed terms")
        with tempfile.TemporaryDirectory() as outside:
            private = Path(outside) / "synthetic-private.txt"
            private.write_text("SYNTHETIC_SECRET_CANARY")
            record = self.root / "licenses/android-sdk-license"
            record.unlink()
            record.symlink_to(private)
            report = inspect_sdk(self.root)
            if report.accepted or "CANARY" in json.dumps(asdict(report)):
                raise AssertionError("Out-of-SDK license path was accepted or exposed")


if __name__ == "__main__":
    unittest.main()
