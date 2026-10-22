#!/usr/bin/env python3
"""Find public-domain oil/tempera candidates using official museum APIs.

Metadata needs Python 3.10+. --download additionally requires Pillow.
No keyword search establishes thematic relevance: a human/agent must curate it.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


class FetchError(RuntimeError):
    pass


class HTTPClient:
    """One request at a time; bounded payload, timeout, retries and rate."""

    def __init__(self, timeout=20.0, retries=1, delay=1.0):
        self.timeout = timeout
        self.retries = retries
        self.delay = max(1.0, delay)
        self.last_request = 0.0

    def fetch(self, url, max_bytes):
        if urlparse(url).scheme != "https":
            raise FetchError("Only HTTPS URLs are accepted")
        for attempt in range(self.retries + 1):
            time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            started = self.last_request
            try:
                request = Request(url, headers={
                    "User-Agent": "KratzPPTArtCandidates/1.0 (personal presentation research)",
                    "Accept": "application/json,image/*;q=0.9,*/*;q=0.5",
                })
                with urlopen(request, timeout=self.timeout) as response:
                    length = response.headers.get("Content-Length")
                    if length and int(length) > max_bytes:
                        raise FetchError(f"Content-Length exceeds {max_bytes} bytes")
                    pieces, size = [], 0
                    while True:
                        piece = response.read(min(65536, max_bytes + 1 - size))
                        if not piece:
                            break
                        pieces.append(piece)
                        size += len(piece)
                        if size > max_bytes:
                            raise FetchError(f"Download exceeds {max_bytes} bytes")
                        if time.monotonic() - started > self.timeout * 2:
                            raise FetchError("Response exceeded the total transfer deadline")
                    return b"".join(pieces)
            except HTTPError as exc:
                # 401/403/404 are not transient: retain links and let the user act.
                if exc.code not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    raise FetchError(f"HTTP {exc.code}: {exc.reason}") from exc
                retry_after = exc.headers.get("Retry-After", "")
                if retry_after.isdigit() and int(retry_after) > 30:
                    raise FetchError(f"HTTP {exc.code}: server requested a long retry delay") from exc
                time.sleep(max(2 ** attempt, int(retry_after) if retry_after.isdigit() else 0))
            except (URLError, TimeoutError, OSError) as exc:
                if attempt == self.retries:
                    raise FetchError(str(exc)) from exc
                time.sleep(2 ** attempt)
        raise FetchError("No response")

    def json(self, url):
        try:
            return json.loads(self.fetch(url, 8 * 1024 * 1024))
        except (ValueError, UnicodeDecodeError) as exc:
            raise FetchError(f"Invalid JSON: {exc}") from exc


def api_url(base, params):
    return base + "?" + urlencode(params)


def eligible_medium(medium, object_type=""):
    """Conservative text filter, not a visual guess about the medium."""
    value = (medium or "").lower()
    if not re.search(r"\b(?:oil|oils|tempera)\b", value):
        return False
    if re.search(r"\b(?:oilcloth|oil-based|oilskin)\b", value):
        return False
    kind = (object_type or "").lower()
    if re.search(r"\b(?:print|prints|photograph|photographs|textile|textiles)\b", kind):
        return False
    return bool(re.search(r"\btempera\b|\boils?\s+(?:on|and|over|paint)\b", value)
                or (re.search(r"\boils?\b", value) and "painting" in kind))


def candidate(source, identity, title, artist, medium, date, page, image, preview,
              image_kind, rights, query, metadata_url):
    return {
        "id": f"{source}-{identity}", "source": source, "source_object_id": str(identity),
        "title": title or "Unknown title", "artist": artist or "Unknown artist",
        "medium": medium, "date": date or "Unknown", "artwork_url": page,
        "image_url": image or None, "preview_url": preview or None,
        "image_url_kind": image_kind, "metadata_url": metadata_url,
        "rights": rights, "matched_queries": [query],
        "theme_relevance": "requires_agent_review",
        "pixel_dimensions": None, "dimension_evidence": "not_measured",
        "resolution_status": "unverified", "download_status": "not_requested",
        "manual_download": False, "local_file": None, "preview_file": None,
        "download_error": None,
    }


def search_artic(client, query, scan_limit, errors):
    fields = "id,title,artist_display,medium_display,date_display,image_id,is_public_domain,artwork_type_title,copyright_notice"
    page, scanned = 1, 0
    while scanned < scan_limit:
        url = api_url("https://api.artic.edu/api/v1/artworks/search", {
            "q": query, "query[term][is_public_domain]": "true",
            "limit": min(100, scan_limit - scanned), "page": page, "fields": fields,
        })
        try:
            data = client.json(url)
        except FetchError as exc:
            errors.append({"source": "artic", "url": url, "error": str(exc)})
            return
        rows = data.get("data") or []
        if not rows:
            return
        iiif = data.get("config", {}).get("iiif_url")
        for row in rows:
            scanned += 1
            medium = row.get("medium_display", "")
            if not row.get("is_public_domain") or not eligible_medium(medium, row.get("artwork_type_title")):
                continue
            identity = row["id"]
            image_base = f"{iiif}/{row['image_id']}" if iiif and row.get("image_id") else None
            result = candidate(
                "artic", identity, row.get("title"), row.get("artist_display"), medium,
                row.get("date_display"), f"https://www.artic.edu/artworks/{identity}",
                f"{image_base}/full/1686,/0/default.jpg" if image_base else None,
                f"{image_base}/full/843,/0/default.jpg" if image_base else None,
                "official_1686px_rendition_not_original",
                {"is_public_domain": True, "source_notice": row.get("copyright_notice"),
                 "policy_url": "https://www.artic.edu/open-access/open-access-images"},
                query, f"https://api.artic.edu/api/v1/artworks/{identity}",
            )
            result["original_image_url"] = None
            result["source_dimension_note"] = "1686px rendition; obtain a larger image from the official artwork page if required."
            yield result
        pagination = data.get("pagination", {})
        if page >= pagination.get("total_pages", page):
            return
        page += 1


def search_met(client, query, scan_limit, errors):
    scanned, offset = 0, 0
    while scanned < scan_limit:
        url = api_url("https://collectionapi.metmuseum.org/public/collection/v1.1/search", {
            "q": query, "hasImages": "true", "medium": "Paintings",
            "offset": offset, "limit": min(100, scan_limit - scanned),
        })
        try:
            data = client.json(url)
        except FetchError as exc:
            errors.append({"source": "met", "url": url, "error": str(exc)})
            return
        ids = data.get("objectIDs") or []
        if not ids:
            return
        for identity in ids:
            scanned += 1
            detail_url = f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{identity}"
            try:
                row = client.json(detail_url)
            except FetchError as exc:
                errors.append({"source": "met", "url": detail_url, "error": str(exc)})
                continue
            medium = row.get("medium", "")
            kind = row.get("classification") or row.get("objectName", "")
            if not row.get("isPublicDomain") or not eligible_medium(medium, kind):
                continue
            original, small = row.get("primaryImage"), row.get("primaryImageSmall")
            result = candidate(
                "met", identity, row.get("title"), row.get("artistDisplayName"), medium,
                row.get("objectDate"), row.get("objectURL") or f"https://www.metmuseum.org/art/collection/search/{identity}",
                original or small, small,
                "official_original_unverified" if original else "preview_only",
                {"is_public_domain": True, "source_notice": "Met API isPublicDomain=true",
                 "policy_url": "https://www.metmuseum.org/policies/image-resources"},
                query, detail_url,
            )
            result["original_image_url"] = original or None
            yield result
        offset += len(ids)
        if offset >= data.get("total", 0) or offset >= 10000:
            return


def identity_key(row):
    # Cross-provider dedup only when attribution is known; never merge unknown artists.
    normalize = lambda s: re.sub(r"\W+", "", s.casefold())
    if row["artist"] == "Unknown artist":
        return row["id"]
    return (normalize(row["artist"]), normalize(row["title"]), normalize(row["date"]))


def download_candidate(row, client, output_dir, target_width, target_height, max_bytes):
    """Retain original bytes; local previews are separate and never called originals."""
    from PIL import Image

    # A preview can be large enough for HD yet still be a downsampled derivative.
    # Only the source's explicit original-file URL is permitted for PPT assets.
    url = row.get("original_image_url")
    if not url:
        row.update(download_status="manual_download", manual_download=True,
                   resolution_status="unverified",
                   download_error="No original-file URL in the source metadata; preview/rendition download deliberately skipped")
        return
    try:
        raw = client.fetch(url, max_bytes)
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            width, height = img.size
            row.update(pixel_dimensions={"width": width, "height": height},
                       dimension_evidence="Pillow decoded downloaded original file",
                       downloaded_url=url, byte_size=len(raw))
            expected_dimensions = row.get("metadata_pixel_dimensions")
            if expected_dimensions:
                row["metadata_dimensions_match"] = expected_dimensions == row["pixel_dimensions"]
                if not row["metadata_dimensions_match"]:
                    raise FetchError("Decoded dimensions differ from the source's original-file metadata")
            if row.get("metadata_byte_size") is not None:
                row["metadata_byte_size_match"] = row["metadata_byte_size"] == len(raw)
                if not row["metadata_byte_size_match"]:
                    raise FetchError("Downloaded byte count differs from the source's original-file metadata")
            expected_mime = row.get("metadata_mime")
            if expected_mime:
                row["decoded_mime"] = Image.MIME.get(img.format)
                row["metadata_mime_match"] = expected_mime == row["decoded_mime"]
                if not row["metadata_mime_match"]:
                    raise FetchError("Decoded image MIME type differs from original-file metadata")
            sufficient = width >= target_width and height >= target_height
            row["resolution_status"] = "verified_hd" if sufficient else "too_small"
            row["manual_download"] = not sufficient
            extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "TIFF": ".tif"}.get(img.format)
            if not extension:
                raise FetchError(f"Unsupported image format: {img.format}")
            relative = Path("images") / (row["id"] + extension)
            (output_dir / relative).parent.mkdir(parents=True, exist_ok=True)
            (output_dir / relative).write_bytes(raw)
            row["local_file"] = relative.as_posix()
            row["sha256"] = hashlib.sha256(raw).hexdigest()
            thumbnail = img.convert("RGB")
            thumbnail.thumbnail((700, 420))
            preview = Path("previews") / (row["id"] + ".jpg")
            (output_dir / preview).parent.mkdir(parents=True, exist_ok=True)
            thumbnail.save(output_dir / preview, "JPEG", quality=88)
            row["preview_file"] = preview.as_posix()
            row["download_status"] = "downloaded"
    except Exception as exc:
        row.update(download_status="download_failed", manual_download=True,
                   resolution_status="unverified",
                   download_error=f"{type(exc).__name__}: {exc}")


def write_outputs(output_dir, report):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "candidates.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    escape = lambda value: html.escape(str(value), quote=True)
    cards = []
    for index, row in enumerate(report["candidates"], 1):
        # Offline portable when --download succeeded; otherwise links only (no hotlink dependency).
        preview = f'<img loading="lazy" src="{escape(row["preview_file"])}" alt="{escape(row["title"])}">' if row["preview_file"] else '<div class="missing">Preview not downloaded — open museum/image links below.</div>'
        dims = row["pixel_dimensions"]
        dimensions = f'{dims["width"]} × {dims["height"]} px' if dims else "Unknown / not measured"
        image_link = f'<a href="{escape(row["image_url"])}">Image URL ({escape(row["image_url_kind"])})</a>' if row["image_url"] else 'No image URL; use museum page.'
        original = row.get("original_image_url")
        original_note = "Original URL not supplied; use the museum page to obtain a larger image." if not original else "Original URL supplied by the museum; pixel dimensions require verification."
        cards.append(f'''<article><h2>{index:02d}. {escape(row["title"])}</h2>{preview}
<p>{escape(row["artist"])} · {escape(row["date"])}</p><p>{escape(row["medium"])}</p>
<p><b>{escape(row["resolution_status"])}</b> · {escape(dimensions)} · {escape(row["download_status"])}</p>
<p><a href="{escape(row["artwork_url"])}">Official artwork page</a><br>{image_link}</p>
<p>{escape(original_note)}</p><p>Theme relation: requires agent review.</p>
<p>Rights: public-domain flag from {escape(row["source"])}. <a href="{escape(row["rights"]["policy_url"])}">Source policy</a></p>
<p class="error">{escape(row["download_error"] or "")}</p></article>''')
    s = report["summary"]
    document = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Painting background candidates</title><style>body{{font:16px Georgia,serif;margin:30px;background:#f3efe7;color:#202020}}h1{{font-size:30px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:22px}}article{{padding:20px;background:white;border:1px solid #d3ccbd}}img{{width:100%;height:260px;object-fit:contain;background:#222}}h2{{font-size:20px}}p{{line-height:1.5;overflow-wrap:anywhere}}a{{color:#225c88}}.error{{color:#8b2424}}.missing{{height:130px;background:#eee;padding:20px}}.note{{padding:18px;border-left:5px solid #775938;background:#fff}}</style>
<h1>Painting background candidates</h1><p>Queries: {escape(', '.join(report["queries"]))}</p>
<p class="note">{s["candidate_count"]} distinct candidates; {s["verified_hd_count"]} downloaded images meet {report["target_pixels"]["width"]} × {report["target_pixels"]["height"]} pixels before cropping. Required shortlist: {report["minimum_required"]}.<br>HD quota status: <b>{escape(s["hd_quota_status"])}</b>. Search results still need theme and visual review. No final background has been selected.</p>
<div class="grid">{''.join(cards)}</div><p>See candidates.json for acquisition errors, source metadata and provenance.</p></html>'''
    (output_dir / "candidates.html").write_text(document, encoding="utf-8")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", action="append", required=True, help="English museum search term; repeat for related visual metaphors")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sources", nargs="+", choices=("artic", "met"), default=["met", "artic"],
                        help="Search order; Met originals first, then AIC preview-sized renditions")
    parser.add_argument("--count", type=int, default=8, help="Distinct candidate target (at least 5; default 8 leaves room for curation)")
    parser.add_argument("--scan-limit", type=int, default=60, help="Max records examined per source/query")
    parser.add_argument("--download", action="store_true", help="Download explicit original-file URLs only; never preview/rendition URLs. Measure pixels and create offline previews; requires Pillow")
    parser.add_argument("--target-width", type=int, default=1920)
    parser.add_argument("--target-height", type=int, default=1080)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--retries", type=int, choices=range(0, 3), default=1)
    parser.add_argument("--delay", type=float, default=1, help="Minimum 1 second between requests")
    parser.add_argument("--max-image-mb", type=float, default=40)
    args = parser.parse_args(argv)
    if args.count < 5 or args.scan_limit < 1 or min(args.target_width, args.target_height) < 1:
        parser.error("--count must be >= 5; scan limit and target dimensions must be positive")
    if args.timeout <= 0 or args.max_image_mb <= 0 or not math.isfinite(args.timeout + args.max_image_mb + args.delay):
        parser.error("Timeout and file-size limit must be finite and positive; delay must be finite")
    if args.download:
        try:
            import PIL  # noqa: F401
        except ImportError:
            parser.error("--download requires Pillow: python -m pip install Pillow")
    return args


def main(argv=None):
    args = parse_args(argv)
    client = HTTPClient(args.timeout, args.retries, args.delay)
    rows, seen_ids, seen_works, errors = [], set(), {}, []
    searches = {"artic": search_artic, "met": search_met}
    for query in args.query:
        for source in dict.fromkeys(args.sources):
            print(f"Searching {source}: {query}", file=sys.stderr, flush=True)
            for row in searches[source](client, query, args.scan_limit, errors):
                key = identity_key(row)
                if row["id"] in seen_ids or key in seen_works:
                    if key in seen_works and query not in seen_works[key]["matched_queries"]:
                        seen_works[key]["matched_queries"].append(query)
                    continue
                seen_ids.add(row["id"])
                seen_works[key] = row
                rows.append(row)
                if len(rows) >= args.count:
                    break
            if len(rows) >= args.count:
                break
        if len(rows) >= args.count:
            break
    output_dir = args.output_dir.resolve()
    if args.download:
        for number, row in enumerate(rows, 1):
            print(f"Downloading {number}/{len(rows)}: {row['id']}", file=sys.stderr, flush=True)
            download_candidate(row, client, output_dir, args.target_width, args.target_height, int(args.max_image_mb * 1024 * 1024))
    hd_count = sum(row["resolution_status"] == "verified_hd" and row["download_status"] == "downloaded" for row in rows)
    report = {
        "schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "queries": args.query, "minimum_required": 5, "requested_count": args.count,
        "target_pixels": {"width": args.target_width, "height": args.target_height},
        "hd_rule": "Decoded image width >= target_width AND height >= target_height; no upscaling. Theme relevance requires separate review.",
        "summary": {"candidate_count": len(rows), "verified_hd_count": hd_count,
                    "metadata_quota_status": "enough_for_review" if len(rows) >= 5 else "insufficient",
                    "hd_quota_status": "enough_for_review" if hd_count >= 5 else "insufficient_or_unverified",
                    "download_failed_count": sum(row["download_status"] == "download_failed" for row in rows),
                    "too_small_count": sum(row["resolution_status"] == "too_small" for row in rows)},
        "errors": errors, "candidates": rows,
    }
    write_outputs(output_dir, report)
    print(f"Candidates: {len(rows)}; verified HD: {hd_count}; required: 5.")
    print(f"Manifest: {output_dir / 'candidates.json'}")
    print(f"Gallery: {output_dir / 'candidates.html'}")
    if errors:
        print(f"Source errors: {len(errors)} (URLs and reasons retained in candidates.json).")
    if len(rows) < 5 or (args.download and hd_count < 5):
        print("SHORTFALL: expand search terms/sources or supply the official links for manual acquisition; do not claim five verified HD choices.")
        return 2
    if not args.download:
        print("Pixel dimensions unverified. These metadata results do not yet satisfy the five-HD-image requirement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
