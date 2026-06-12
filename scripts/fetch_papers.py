#!/usr/bin/env python3
"""Fetch arXiv papers for the static GitHub Pages digest."""

from __future__ import annotations

import datetime as dt
import email.utils
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
OUTPUT_PATH = ROOT / "docs" / "data" / "papers.json"

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
DEFAULT_CONFIG = {
    "category": "cs.CV",
    "max_results": 50,
    "keywords": [],
    "exclude_keywords": [],
    "translate": True,
    "openai_model": "gpt-4o-mini",
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        config = json.load(f)
    merged = DEFAULT_CONFIG.copy()
    merged.update(config)
    return merged


def load_existing() -> dict[str, Any]:
    if not OUTPUT_PATH.exists():
        return {"papers": []}
    with OUTPUT_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_output(payload: dict[str, Any]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = OUTPUT_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(OUTPUT_PATH)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def parse_datetime(value: str) -> str:
    if not value:
        return ""
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.isoformat()
        except (TypeError, ValueError):
            return value


def fetch_arxiv(config: dict[str, Any]) -> list[dict[str, Any]]:
    category = str(config["category"]).strip() or "cs.CV"
    max_results = max(1, min(int(config["max_results"]), 200))
    params = {
        "search_query": f"cat:{category}",
        "start": "0",
        "max_results": str(max_results),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    request = urllib.request.Request(
        f"{ARXIV_API_URL}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": "arxiv-cv-digest/1.0"},
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())

    papers: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        title = normalize_space(entry.findtext("atom:title", "", ATOM_NS))
        summary = normalize_space(entry.findtext("atom:summary", "", ATOM_NS))
        abs_url = normalize_space(entry.findtext("atom:id", "", ATOM_NS))
        pdf_url = ""
        for link in entry.findall("atom:link", ATOM_NS):
            if link.attrib.get("rel") == "alternate":
                abs_url = link.attrib.get("href", abs_url)
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href", "")

        papers.append(
            {
                "id": abs_url.rstrip("/").split("/")[-1],
                "title_en": title,
                "title_zh": "",
                "summary_en": summary,
                "summary_zh": "",
                "authors": [
                    normalize_space(author.findtext("atom:name", "", ATOM_NS))
                    for author in entry.findall("atom:author", ATOM_NS)
                ],
                "categories": [
                    cat.attrib.get("term", "")
                    for cat in entry.findall("atom:category", ATOM_NS)
                    if cat.attrib.get("term")
                ],
                "published": parse_datetime(
                    normalize_space(entry.findtext("atom:published", "", ATOM_NS))
                ),
                "updated": parse_datetime(
                    normalize_space(entry.findtext("atom:updated", "", ATOM_NS))
                ),
                "abs_url": abs_url,
                "pdf_url": pdf_url,
            }
        )
    return papers


def matches_keywords(paper: dict[str, Any], config: dict[str, Any]) -> bool:
    text = " ".join(
        [
            paper.get("title_en", ""),
            paper.get("summary_en", ""),
            " ".join(paper.get("categories", [])),
        ]
    ).lower()
    keywords = [str(k).strip().lower() for k in config.get("keywords", []) if str(k).strip()]
    excludes = [str(k).strip().lower() for k in config.get("exclude_keywords", []) if str(k).strip()]
    if keywords and not any(k in text for k in keywords):
        return False
    return not (excludes and any(k in text for k in excludes))


def merge_existing_translations(
    papers: list[dict[str, Any]],
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {paper.get("id"): paper for paper in existing}
    for paper in papers:
        old = by_id.get(paper.get("id"))
        if old:
            paper["title_zh"] = old.get("title_zh", "")
            paper["summary_zh"] = old.get("summary_zh", "")
            paper["translation_status"] = old.get("translation_status", "")
    return papers


def openai_request(messages: list[dict[str, str]], model: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    base_url = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com").rstrip("/")
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "arxiv-cv-digest/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def translate_paper(paper: dict[str, Any], config: dict[str, Any]) -> None:
    if not config.get("translate", True):
        paper["translation_status"] = "disabled"
        return
    if paper.get("title_zh") and paper.get("summary_zh"):
        return
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        paper["translation_status"] = "missing_api_key"
        return

    model = str(config.get("openai_model") or DEFAULT_CONFIG["openai_model"])
    content = openai_request(
        [
            {
                "role": "system",
                "content": (
                    "Translate this computer vision arXiv paper title and abstract into concise, "
                    "accurate Simplified Chinese. Preserve technical terms when English is clearer. "
                    'Return strict JSON with keys "title_zh" and "summary_zh".'
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "title_en": paper.get("title_en", ""),
                        "summary_en": paper.get("summary_en", ""),
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        model,
    )
    translated = json.loads(content)
    paper["title_zh"] = normalize_space(str(translated.get("title_zh", "")))
    paper["summary_zh"] = normalize_space(str(translated.get("summary_zh", "")))
    paper["translation_status"] = "translated"


def main() -> None:
    config = load_config()
    existing = load_existing()
    try:
        papers = fetch_arxiv(config)
        papers = [paper for paper in papers if matches_keywords(paper, config)]
        papers = merge_existing_translations(papers, existing.get("papers", []))
        for paper in papers:
            try:
                translate_paper(paper, config)
            except Exception as exc:  # noqa: BLE001 - keep the digest publishing.
                paper["translation_status"] = "translation_error"
                paper["translation_error"] = f"{type(exc).__name__}: {exc}"
            if os.environ.get("OPENAI_API_KEY", "").strip():
                time.sleep(0.15)

        write_output(
            {
                "papers": papers,
                "last_updated": utc_now().isoformat(),
                "last_error": None,
                "config": config,
                "translation_enabled": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
            }
        )
        print(f"Wrote {len(papers)} papers to {OUTPUT_PATH}")
    except Exception as exc:  # noqa: BLE001 - publish error to the static UI.
        existing["last_error"] = f"{type(exc).__name__}: {exc}"
        existing["last_updated"] = existing.get("last_updated")
        existing["config"] = config
        write_output(existing)
        raise


if __name__ == "__main__":
    main()
