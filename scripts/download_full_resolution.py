#!/usr/bin/env python3
"""Download the Original file / Full resolution for one Wikimedia Commons File.

Accept a Commons File page URL or a File: title. Uses imageinfo=url|size|mime,
without iiurlwidth/iiurlheight, and downloads only imageinfo.url. Requires Pillow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from find_art_candidates import HTTPClient, FetchError, api_url, candidate, download_candidate


def commons_title(value):
    value = value.strip()
    if value.startswith("https://"):
        parsed = urlparse(value)
        if parsed.hostname != "commons.wikimedia.org":
            raise ValueError("Use a commons.wikimedia.org File page, not a thumbnail/image URL")
        if parsed.path.startswith("/wiki/"):
            title = unquote(parsed.path[len("/wiki/"):])
        elif parsed.path == "/w/index.php":
            title = parse_qs(parsed.query).get("title", [""])[0]
        else:
            raise ValueError("The Commons URL must point to a File page")
    else:
        title = value
    title = title.replace("_", " ")
    if not title.startswith("File:") or not title[len("File:"):].strip() or "|" in title:
        raise ValueError("Supply one File: title or the corresponding Commons File page URL")
    return title


def source_page(title):
    return "https://commons.wikimedia.org/wiki/" + quote(title.replace(" ", "_"), safe=":(),")


def resolve_original(client, title):
    url = api_url("https://commons.wikimedia.org/w/api.php", {
        "action": "query", "prop": "imageinfo", "titles": title,
        "iiprop": "url|size|mime", "format": "json", "formatversion": 2,
        "redirects": 1,
    })
    # Do not add iiurlwidth/iiurlheight or consume thumburl: those request derivatives.
    data = client.json(url)
    if "error" in data:
        raise FetchError("MediaWiki API error: " + json.dumps(data["error"], ensure_ascii=True))
    pages = data.get("query", {}).get("pages", [])
    page = next((entry for entry in pages if entry.get("imageinfo")), None)
    if page is None:
        raise FetchError("Commons did not return imageinfo for this File page")
    info = page["imageinfo"][0]
    original = info.get("url")
    parsed = urlparse(original or "")
    if parsed.scheme != "https" or parsed.hostname != "upload.wikimedia.org" or "/thumb/" in parsed.path:
        raise FetchError("API did not return a trusted Wikimedia original-file URL")
    return page, info, url


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Commons File page HTTPS URL or File: title")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--retries", type=int, choices=range(0, 3), default=1)
    parser.add_argument("--delay", type=float, default=1)
    parser.add_argument("--max-image-mb", type=float, default=100)
    parser.add_argument("--target-width", type=int, default=1920)
    parser.add_argument("--target-height", type=int, default=1080)
    args = parser.parse_args(argv)
    try:
        args.title = commons_title(args.source)
    except ValueError as exc:
        parser.error(str(exc))
    if args.timeout <= 0 or args.max_image_mb <= 0 or not math.isfinite(args.timeout + args.max_image_mb + args.delay):
        parser.error("Timeout and file size must be finite and positive; delay must be finite")
    if min(args.target_width, args.target_height) < 1:
        parser.error("Target dimensions must be positive")
    try:
        import PIL  # noqa: F401
    except ImportError:
        parser.error("Pillow is required: python -m pip install Pillow")
    return args


def main(argv=None):
    args = parse_args(argv)
    client = HTTPClient(args.timeout, args.retries, args.delay)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    page_url = source_page(args.title)
    row = candidate(
        "commons", hashlib.sha256(args.title.encode("utf-8")).hexdigest()[:12],
        args.title, "See source page", "See source page", "See source page",
        page_url, None, None, "original_file_only",
        {"is_public_domain": None, "source_notice": "Read the File page's licensing section; no rights inferred by downloader",
         "policy_url": page_url}, "user-selected File page", None,
    )
    row.update(original_image_url=None, created_at_utc=datetime.now(timezone.utc).isoformat(),
               original_file_verification="unverified", target_pixels={"width": args.target_width, "height": args.target_height})
    try:
        page, info, metadata_url = resolve_original(client, args.title)
        row.update(title=page.get("title", args.title), source_object_id=str(page.get("pageid", "unknown")),
                   artwork_url=info.get("descriptionurl") or source_page(page.get("title", args.title)),
                   metadata_url=metadata_url, image_url=info["url"], original_image_url=info["url"],
                   metadata_pixel_dimensions={"width": info.get("width"), "height": info.get("height")},
                   metadata_byte_size=info.get("size"), metadata_mime=info.get("mime"),
                   source_imageinfo=info)
        if not all(isinstance(value, int) and value > 0 for value in row["metadata_pixel_dimensions"].values()):
            raise FetchError("Original-file dimensions are missing from imageinfo; no thumbnail fallback")
        download_candidate(row, client, output_dir, args.target_width, args.target_height, int(args.max_image_mb * 1024 * 1024))
        if row["download_status"] == "downloaded":
            row["original_file_verification"] = "downloaded_original_matches_source_dimensions"
    except FetchError as exc:
        row.update(download_status="download_failed", manual_download=True,
                   download_error=str(exc), resolution_status="unverified")
    manifest = output_dir / "full-resolution.json"
    manifest.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Status: " + row["download_status"])
    print("File page: " + row["artwork_url"])
    print("Original file: " + (row.get("original_image_url") or "Unavailable; open the File page and choose Original file / Full resolution."))
    print("Manifest: " + str(manifest))
    if row["download_status"] == "downloaded":
        dims = row["pixel_dimensions"]
        print(f"Decoded original: {dims['width']} x {dims['height']} px; {row['byte_size']} bytes; {row['resolution_status']}.")
        print("Local original: " + str(output_dir / row["local_file"]))
        return 0
    print("Download failed; retained links above. No preview or reduced-resolution fallback was downloaded.")
    # JSON escaping avoids terminal encoding failures for source error messages.
    print("Reason: " + json.dumps(row["download_error"], ensure_ascii=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
