#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import stat
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


MAX_TRX_BYTES = 16 * 1024 * 1024
REQUIRED_TEST_CLASSES = (
    "Chummer.Tests.ReleaseBundlePromotionServiceTests",
    "Chummer.Tests.ReleaseBundleUploadSessionServiceTests",
    "Chummer.Tests.InternalReleaseBundlesControllerTests",
    "Chummer.Tests.ReleaseUploadRequestGateMiddlewareTests",
)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def read_regular_file(path: Path) -> bytes:
    value = os.lstat(path)
    if not stat.S_ISREG(value.st_mode):
        raise ValueError("TRX result is not a regular file")
    if value.st_size <= 0 or value.st_size > MAX_TRX_BYTES:
        raise ValueError("TRX result size is outside the accepted range")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_TRX_BYTES:
                raise ValueError("TRX result exceeds the accepted size")
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    stable_fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
        raise ValueError("TRX result changed while it was read")
    return b"".join(chunks)


def verify(path: Path) -> dict[str, int]:
    try:
        root = ET.fromstring(read_regular_file(path))
    except (ET.ParseError, OSError, ValueError) as exc:
        raise ValueError(f"release bundle transaction TRX is invalid: {exc}") from exc

    definitions: dict[str, str] = {}
    for unit_test in root.iter():
        if local_name(unit_test.tag) != "UnitTest":
            continue
        test_id = str(unit_test.attrib.get("id") or "").strip()
        methods = [
            child
            for child in unit_test.iter()
            if local_name(child.tag) == "TestMethod"
        ]
        if not test_id or len(methods) != 1 or test_id in definitions:
            raise ValueError("release bundle transaction TRX test definitions are ambiguous")
        class_name = str(methods[0].attrib.get("className") or "").strip()
        if not class_name:
            raise ValueError("release bundle transaction TRX test class is missing")
        definitions[test_id] = class_name

    passed = {class_name: 0 for class_name in REQUIRED_TEST_CLASSES}
    observed_results = 0
    for result in root.iter():
        if local_name(result.tag) != "UnitTestResult":
            continue
        observed_results += 1
        test_id = str(result.attrib.get("testId") or "").strip()
        class_name = definitions.get(test_id)
        if class_name is None:
            raise ValueError("release bundle transaction TRX result has no test definition")
        if class_name not in passed:
            raise ValueError(
                f"release bundle transaction TRX contains unexpected class {class_name}"
            )
        if str(result.attrib.get("outcome") or "").strip() != "Passed":
            raise ValueError(
                f"release bundle transaction TRX contains a non-passing result for {class_name}"
            )
        passed[class_name] += 1

    if observed_results == 0:
        raise ValueError("release bundle transaction TRX contains no test results")
    missing = [class_name for class_name, count in passed.items() if count == 0]
    if missing:
        raise ValueError(
            "release bundle transaction TRX has no passing result for: "
            + ", ".join(missing)
        )
    return passed


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trx", type=Path)
    args = parser.parse_args(argv)
    try:
        counts = verify(args.trx)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    summary = ",".join(
        f"{class_name}={counts[class_name]}" for class_name in REQUIRED_TEST_CLASSES
    )
    print(f"release_bundle_transaction_trx:pass:{summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
