#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, os, json, glob

SRC = "C:/Users/MZCny/AppData/Local/Temp/rmrb"
DATE = "202610/15"
CONTENT_BASE = f"http://paper.people.com.cn/rmrb/pc/content/{DATE}/"

files = sorted(glob.glob(os.path.join(SRC, "node_*.html")))
result = []
for f in files:
    name = os.path.basename(f)
    num = name.replace("node_", "").replace(".html", "")
    html = open(f, encoding="utf-8", errors="ignore").read()

    sec = None
    for m in re.finditer(r'<a id="pageLink" href="(node_\d+\.html)">([^<]+)</a>', html):
        if m.group(1) == name:
            sec = m.group(2).strip()
            break
    if not sec:
        sec = f"{num}版"

    arts = []
    seen = set()
    for m in re.finditer(
        r'<a\s+href="(\.\./\.\./\.\./content/202610/15/content_\d+\.html)"[^>]*>\s*(.*?)\s*</a>',
        html, re.S):
        url = m.group(1)
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        if not title or url in seen:
            continue
        seen.add(url)
        full = CONTENT_BASE + url.split("/")[-1]
        arts.append({"title": title, "url": full})

    result.append({"page": num, "section": sec, "articles": arts})

total = sum(len(r["articles"]) for r in result)
print(f"Pages: {len(result)}  Total articles: {total}")
for r in result:
    print(f"  {r['page']} {r['section']}  ({len(r['articles'])} articles)")

os.makedirs("E:/ProjectStartingBusiness/Project11-News/data", exist_ok=True)
json.dump(result, open("E:/ProjectStartingBusiness/Project11-News/data/rmrb_2026-10-15.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("Saved data/rmrb_2026-10-15.json")
