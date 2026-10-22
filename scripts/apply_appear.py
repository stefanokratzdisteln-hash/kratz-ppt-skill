#!/usr/bin/env python3
"""Apply native PowerPoint Appear effects from an explicit semantic-item manifest.

Requires Windows, desktop Microsoft PowerPoint, and pywin32. Never modifies the
input, never overwrites an output, never guesses paragraph boundaries, and never
quits PowerPoint. Only presentations opened by this invocation are closed.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile


APPEAR = 1                 # MsoAnimEffect.msoAnimEffectAppear
ON_PAGE_CLICK = 1          # MsoAnimTriggerType.msoAnimTriggerOnPageClick
WITH_PREVIOUS = 2          # MsoAnimTriggerType.msoAnimTriggerWithPrevious
LEVEL_NONE = 0             # MsoAnimateByLevel.msoAnimateLevelNone
PPTX_FORMAT = 24           # PpSaveAsFileType.ppSaveAsOpenXMLPresentation
MSO_TRUE = -1
MSO_FALSE = 0
NS = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}


class ManifestError(ValueError):
    pass


def load_manifest(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ManifestError("Manifest must be an object with version: 1.")
    slides = data.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ManifestError("Manifest slides must be a non-empty list.")
    seen_slides = set()
    for record in slides:
        if not isinstance(record, dict):
            raise ManifestError("Each slide record must be an object.")
        index = record.get("slide")
        if type(index) is not int or index < 1 or index in seen_slides:
            raise ManifestError("Slide numbers must be distinct positive integers (1-based).")
        seen_slides.add(index)
        items = record.get("items")
        if not isinstance(items, list) or not items:
            raise ManifestError(f"Slide {index}: items must be a non-empty list.")
        seen_names, seen_ids = set(), set()
        for item in items:
            if not isinstance(item, dict):
                raise ManifestError(f"Slide {index}: each item must be an object.")
            item_id, names = item.get("id"), item.get("shapes")
            if not isinstance(item_id, str) or not item_id.strip() or item_id in seen_ids:
                raise ManifestError(f"Slide {index}: item ids must be distinct non-empty strings.")
            seen_ids.add(item_id)
            if not isinstance(names, list) or not names:
                raise ManifestError(f"Slide {index}, {item_id}: shapes must be a non-empty list.")
            for name in names:
                if not isinstance(name, str) or not name.strip() or name in seen_names:
                    raise ManifestError(f"Slide {index}: shape names must be distinct non-empty strings.")
                seen_names.add(name)
    return slides


def effects_on_slide(slide) -> list[dict]:
    effects = []
    sequences = [("main", slide.TimeLine.MainSequence)]
    interactive = slide.TimeLine.InteractiveSequences
    sequences += [(f"interactive:{i}", interactive.Item(i))
                  for i in range(1, int(interactive.Count) + 1)]
    for sequence_name, sequence in sequences:
        for i in range(1, int(sequence.Count) + 1):
            effect = sequence.Item(i)
            effects.append({
                "sequence": sequence_name,
                "index": i,
                "shape": str(effect.Shape.Name),
                "shape_id": int(effect.Shape.Id),
                "effect_type": int(effect.EffectType),
                "trigger": int(effect.Timing.TriggerType),
                "delay": float(effect.Timing.TriggerDelayTime),
                "exit": int(effect.Exit),
                "after_effect": int(effect.EffectInformation.AfterEffect),
            })
    return effects


def resolve_plan(presentation, records: list[dict]) -> list[dict]:
    """Validate every target before changing anything; leave other slides alone."""
    plan = []
    for record in records:
        index = record["slide"]
        if index > int(presentation.Slides.Count):
            raise ManifestError(f"Slide {index} does not exist.")
        slide = presentation.Slides.Item(index)
        existing = effects_on_slide(slide)
        if existing:
            raise ManifestError(
                f"Slide {index} already has {len(existing)} animation effect(s). "
                "Refusing to append, replace, or clear animations; use the clean "
                "pre-animation source or reconcile this slide explicitly in PowerPoint."
            )
        by_name = {}
        for i in range(1, int(slide.Shapes.Count) + 1):
            shape = slide.Shapes.Item(i)
            by_name.setdefault(str(shape.Name), []).append(shape)
        groups, item_ids = [], []
        for item in record["items"]:
            shapes = []
            for name in item["shapes"]:
                matches = by_name.get(name, [])
                if len(matches) != 1:
                    raise ManifestError(
                        f"Slide {index}: expected exactly one top-level shape named {name!r}; "
                        f"found {len(matches)}. Name objects explicitly during authoring."
                    )
                shape = matches[0]
                if int(shape.Visible) != MSO_TRUE:
                    raise ManifestError(f"Slide {index}: shape {name!r} is hidden; make it visible before applying animation.")
                shapes.append(shape)
            groups.append(shapes)
            item_ids.append(item["id"])
        plan.append({"slide": index, "groups": groups, "item_ids": item_ids})
    return plan


def apply_plan(presentation, plan: list[dict]) -> None:
    for row in plan:
        slide = presentation.Slides.Item(row["slide"])
        sequence = slide.TimeLine.MainSequence
        # The first semantic item deliberately has NO entrance effect.
        for shapes in row["groups"][1:]:
            for index, shape in enumerate(shapes):
                trigger = ON_PAGE_CLICK if index == 0 else WITH_PREVIOUS
                effect = sequence.AddEffect(shape, APPEAR, LEVEL_NONE, trigger, -1)
                effect.Exit = MSO_FALSE
                effect.Timing.TriggerDelayTime = 0
                # Appear is intrinsically instant; do not substitute Fade or a transition.
                # New native effects have ppAfterEffectNone (0); verify this below.


def verify_com(presentation, records: list[dict]) -> list[dict]:
    results = []
    for record in records:
        slide = presentation.Slides.Item(record["slide"])
        actual = effects_on_slide(slide)
        expected = []
        for item in record["items"][1:]:
            for index, name in enumerate(item["shapes"]):
                expected.append((name, ON_PAGE_CLICK if index == 0 else WITH_PREVIOUS))
        if len(actual) != len(expected):
            raise RuntimeError(f"Slide {record['slide']}: effect count mismatch.")
        for effect, (name, trigger) in zip(actual, expected):
            if not (
                effect["sequence"] == "main" and effect["shape"] == name
                and effect["effect_type"] == APPEAR and effect["trigger"] == trigger
                and effect["delay"] == 0 and effect["exit"] == 0
                and effect["after_effect"] == 0
            ):
                raise RuntimeError(f"Slide {record['slide']}: invalid native Appear effect: {effect}")
        first_names = record["items"][0]["shapes"]
        if any(e["shape"] in first_names for e in actual):
            raise RuntimeError(f"Slide {record['slide']}: first item must not animate.")
        results.append({
            "slide": record["slide"],
            "logical_items": len(record["items"]),
            "required_clicks": max(0, len(record["items"]) - 1),
            "initial_item_shapes": first_names,
            "effects": actual,
        })
    return results


def slide_xml_parts(archive: zipfile.ZipFile) -> list[str]:
    # Do not assume physical slide1.xml equals logical slide 1 after editing/reordering.
    presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
    relationships = ET.fromstring(archive.read("ppt/_rels/presentation.xml.rels"))
    mapping = {rel.attrib["Id"]: rel.attrib["Target"] for rel in relationships}
    r_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    from posixpath import normpath, join
    parts = []
    for slide in presentation.findall("p:sldIdLst/p:sldId", NS):
        target = mapping[slide.attrib[f"{{{r_ns}}}id"]]
        parts.append(target.lstrip("/") if target.startswith("/") else normpath(join("ppt", target)))
    return parts


def verify_xml(path: Path, results: list[dict]) -> None:
    with zipfile.ZipFile(path) as archive:
        parts = slide_xml_parts(archive)
        for row in results:
            part = parts[row["slide"] - 1]
            root = ET.fromstring(archive.read(part))
            timing = root.find("p:timing", NS)
            targets = set() if timing is None else {
                int(node.attrib["spid"]) for node in timing.findall(".//p:spTgt", NS)
            }
            expected = {effect["shape_id"] for effect in row["effects"]}
            if targets != expected:
                raise RuntimeError(f"Slide {row['slide']}: saved native timing targets differ: {targets} != {expected}")
            row["xml_part"] = part
            row["native_timing_present"] = timing is not None
            row["xml_target_shape_ids"] = sorted(targets)


def run(input_path: Path, output_path: Path, records: list[dict]) -> dict:
    if os.name != "nt":
        raise RuntimeError("Native animation helper requires Windows desktop PowerPoint and pywin32.")
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise RuntimeError("Missing pywin32. Install with: python -m pip install pywin32") from exc

    pythoncom.CoInitialize()
    app = presentation = verification = None
    staging = None
    working_copy_dir = None
    plan = None
    try:
        # Reuse an existing server without touching its windows/settings; PowerPoint
        # may share one server even for DispatchEx. Therefore never call app.Quit().
        try:
            app = win32com.client.GetActiveObject("PowerPoint.Application")
        except pythoncom.com_error:
            app = win32com.client.DispatchEx("PowerPoint.Application")
        # PowerPoint can reuse an already-open presentation even with Untitled=True.
        # A uniquely named physical copy is required to protect the user's document.
        working_copy_dir = tempfile.TemporaryDirectory(prefix="kratz-appear-source-")
        working_copy = Path(working_copy_dir.name) / "working-copy.pptx"
        shutil.copyfile(input_path, working_copy)
        presentation = app.Presentations.Open(str(working_copy), MSO_TRUE, MSO_FALSE, MSO_FALSE)
        plan = resolve_plan(presentation, records)
        apply_plan(presentation, plan)
        verify_com(presentation, records)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".kratz-appear-", suffix=".pptx", dir=output_path.parent)
        os.close(descriptor)
        staging = Path(name)
        # SaveCopyAs writes the in-memory changes into a different file.
        presentation.SaveCopyAs(str(staging), PPTX_FORMAT)
        presentation.Saved = MSO_TRUE  # discard this invocation's in-memory source edits
        presentation.Close()
        presentation = None
        plan = None
        gc.collect()
        verification = app.Presentations.Open(str(staging), MSO_TRUE, MSO_FALSE, MSO_FALSE)
        results = verify_com(verification, records)
        verification.Close()
        verification = None
        verify_xml(staging, results)
        # Windows Path.rename fails if destination exists: never overwrite user data.
        staging.rename(output_path)
        staging = None
        return {
            "input": str(input_path), "output": str(output_path),
            "verification": "PowerPoint COM after reopen plus saved OOXML timing; no slideshow playback was performed",
            "slides": results,
        }
    finally:
        for opened in (verification, presentation):
            if opened is not None:
                try:
                    opened.Saved = MSO_TRUE
                    opened.Close()
                except Exception:
                    pass
        plan = verification = presentation = app = None
        gc.collect()
        pythoncom.CoUninitialize()
        if staging is not None:
            staging.unlink(missing_ok=True)
        if working_copy_dir is not None:
            working_copy_dir.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="Existing .pptx; opened read-only and never changed")
    parser.add_argument("manifest", type=Path, help="UTF-8 JSON with version:1 and ordered slides/items/shapes")
    parser.add_argument("output", type=Path, help="New .pptx path; must differ from input and must not exist")
    parser.add_argument("--report", type=Path, help="Optional new JSON validation report path; must not exist")
    args = parser.parse_args()
    try:
        input_path, output_path = args.input.resolve(), args.output.resolve()
        if not input_path.is_file() or input_path.suffix.lower() != ".pptx":
            raise ManifestError("Input must be an existing .pptx file.")
        if output_path.suffix.lower() != ".pptx" or input_path == output_path:
            raise ManifestError("Output must be a different .pptx path.")
        if output_path.exists():
            raise ManifestError(f"Output already exists: {output_path}")
        if args.report and args.report.exists():
            raise ManifestError(f"Report already exists: {args.report}")
        if args.report and args.report.resolve() in (input_path, output_path, args.manifest.resolve()):
            raise ManifestError("Report path must differ from input, output, and manifest.")
        records = load_manifest(args.manifest)
        report = run(input_path, output_path, records)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open("x", encoding="utf-8") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
