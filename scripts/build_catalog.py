#!/usr/bin/env python3
"""Build catalog.json from the GitHub Releases of this repo + jamats.json + names.json.
Run locally:  GITHUB_TOKEN=... python3 scripts/build_catalog.py
"""
import json, os, re, sys, urllib.request
from datetime import datetime, timezone

REPO = os.environ.get("GITHUB_REPOSITORY", "Arifmullikh/qawmi-kitab")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PART = re.compile(r"^(?P<base>.+?)_part(?P<n>\d+)of(?P<m>\d+)\.pdf$", re.I)

def api(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "qawmi-kitab-catalog"})
    if TOKEN: req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r), r.headers.get("Link", "")

def all_releases():
    out, url = [], f"https://api.github.com/repos/{REPO}/releases?per_page=100"
    while url:
        page, link = api(url); out += page
        m = re.search(r'<([^>]+)>;\s*rel="next"', link); url = m.group(1) if m else None
    return out

def pretty(name):
    s = re.sub(r"^(Bangla|Original)__", "", name); s = re.sub(r"\.pdf$", "", s, flags=re.I)
    s = re.sub(r"^[0-9]+[a-z]?[-_]", "", s); return re.sub(r"[-_]+", " ", s).strip()

def main():
    jam = json.load(open(os.path.join(ROOT, "jamats.json"), encoding="utf-8"))
    names = json.load(open(os.path.join(ROOT, "names.json"), encoding="utf-8"))
    rel = {r["tag_name"]: r for r in all_releases()}
    order = [j["tag"] for j in jam["jamats"]]
    extra = [t for t in rel if t not in order]  # releases created later but not yet in jamats.json
    jams = jam["jamats"] + [{"order": len(order) + i + 1, "tag": t, "name_bn": rel[t]["name"] or t, "name_en": t, "group": "other"} for i, t in enumerate(extra)]
    total_files = total_size = 0
    out_j = []
    for j in jams:
        r = rel.get(j["tag"]); books = {}
        for a in (r or {}).get("assets", []):
            if a.get("state") != "uploaded" or not a["name"].lower().endswith(".pdf"): continue
            n = a["name"]; m = PART.match(n)
            base = (m.group("base") + ".pdf") if m else n
            section = "bangla" if n.startswith("Bangla__") else "original"
            meta = names.get(f'{j["tag"]}/{n}') or names.get(f'{j["tag"]}/{base}') or {}
            b = books.setdefault(base, {"id": f'{j["tag"]}/{base}', "section": section,
                                        "title": meta.get("title") or pretty(base),
                                        "lang": meta.get("lang") or ("bn" if section == "bangla" else None),
                                        "size": 0, "parts": []})
            b["parts"].append({"name": n, "part": int(m.group("n")) if m else 1, "size": a["size"],
                               "url": a["browser_download_url"], "updated_at": a["updated_at"]})
            b["size"] += a["size"]; total_files += 1; total_size += a["size"]
        bl = sorted(books.values(), key=lambda b: (b["section"] != "bangla", b["id"]))
        for b in bl: b["parts"].sort(key=lambda p: p["part"])
        out_j.append({**j, "release_url": r["html_url"] if r else None, "book_count": len(bl), "books": bl})
    cat = {"schema": 1, "repo": REPO, "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "total_files": total_files, "total_size": total_size, "groups": jam.get("groups", {}), "jamats": out_j}
    path = os.path.join(ROOT, "catalog.json")
    old = None
    if os.path.exists(path):
        old = json.load(open(path, encoding="utf-8")); old.pop("generated_at", None)
    new = dict(cat); new.pop("generated_at")
    if old == new:
        print("catalog unchanged"); return
    json.dump(cat, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"catalog.json written: {total_files} files, {total_size/1e9:.2f} GB")

if __name__ == "__main__":
    main()
