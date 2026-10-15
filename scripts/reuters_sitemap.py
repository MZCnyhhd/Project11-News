#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reuters 新闻抓取（基于官方 sitemap，stdlib-only，适配 GitHub Actions）。

流程：
  1. 取 news sitemap 索引 -> 列出子 sitemap
  2. 优先选 URL 中含“今日日期”的子 sitemap；没有则取最近的若干个
  3. 解析子 sitemap 得到文章 URL（去重、限量）
  4. 逐篇抓取文章页，优先从 JSON-LD(application/ld+json) 的 articleBody 提取正文，
     回退到 <title> + og:description + 正文文本
  5. 写出 data/reuters_<DATE>.json ；并把 robots.txt dump 到 data/reuters_robots.txt
  6. 对 DataDome/验证码（401 / captcha-delivery）做检测并标记 blocked

使用 urllib（无需 pip）。运行：python scripts/reuters_sitemap.py [YYYY-MM-DD]
"""
import sys, os, re, json, gzip, datetime, urllib.request, urllib.error, xml.etree.ElementTree as ET

NEWS_INDEX = "https://www.reuters.com/sitemap_news_index.xml"
ROBOTS = "https://www.reuters.com/robots.txt"
UA = ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)")
ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
HEADERS = {"User-Agent": UA, "Accept": ACCEPT, "Accept-Language": "en-US,en;q=0.9"}

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
MAX_ARTICLES = int(os.environ.get("MAX_ARTICLES", "300"))
MAX_SUBMAPS = int(os.environ.get("MAX_SUBMAPS", "3"))
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def log(*a):
    print("[reuters]", *a, flush=True)


def fetch(url, timeout=30, raw=False):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
            enc = r.headers.get("Content-Encoding", "")
            if enc == "gzip":
                data = gzip.decompress(data)
            elif enc == "deflate":
                data = data  # rare; ignore
            if raw:
                return r.status, data
            return r.status, data.decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        # DataDome 常返回 401/403 验证码
        try:
            body = e.read()
            if e.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return e.code, body.decode("utf-8", "ignore")
        except Exception:
            return e.code, ""
    except Exception as e:
        return 0, f"ERR:{e}"


def is_captcha(text):
    return bool(re.search(r"captcha-delivery\.com|enable JS and disable any ad blocker|datadome", text, re.I)) \
        or "dd=" in text and "captcha" in text.lower()


def parse_locs(xml_text):
    locs = []
    try:
        root = ET.fromstring(xml_text)
        for el in root.iter():
            if el.tag in (SITEMAP_NS + "loc", "loc"):
                if el.text:
                    locs.append(el.text.strip())
    except ET.ParseError as e:
        log("XML parse error:", e)
    return locs


def pick_subsitemap(index_locs, today):
    # 优先 URL 含今日日期（两种格式 2026-10-15 / 20261015）
    t1 = today.strftime("%Y-%m-%d")
    t2 = today.strftime("%Y%m%d")
    matched = [u for u in index_locs if t1 in u or t2 in u]
    if matched:
        log(f"找到今日子 sitemap: {len(matched)} 个")
        return matched[:MAX_SUBMAPS]
    # 否则按 URL 中的日期排序，取最近的 MAX_SUBMAPS 个
    dated = sorted(
        [u for u in index_locs if re.search(r"\d{4}[-/]?\d{2}[-/]?\d{2}", u)],
        reverse=True,
    )
    if dated:
        log(f"未命中今日，取最近 {MAX_SUBMAPS} 个子 sitemap（最新在前）")
        return dated[:MAX_SUBMAPS]
    log(f"未识别日期，回退取前 {MAX_SUBMAPS} 个")
    return index_locs[:MAX_SUBMAPS]


def extract_article(html):
    # 1) JSON-LD
    bodies, title = [], None
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            obj = json.loads(m.group(1))
        except Exception:
            continue
        items = obj if isinstance(obj, list) else [obj]
        for it in items:
            if not isinstance(it, dict):
                continue
            if it.get("headline"):
                title = title or it["headline"]
            ab = it.get("articleBody") or it.get("description")
            if ab and isinstance(ab, str):
                bodies.append(ab)
    if bodies:
        body = "\n\n".join(bodies)
        return title, body
    # 2) 回退：title + meta description + 可见文本
    tm = re.search(r"<title>(.*?)</title>", html, re.S)
    if tm:
        title = title or tm.group(1).strip()
    dm = re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"', html)
    desc = dm.group(1) if dm else ""
    # 简单正文：去掉 script/style 后的文本片段
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    body = (desc + "\n" + text[:2000]).strip()
    return title, body


def main():
    today = datetime.date.today()
    if len(sys.argv) > 1:
        try:
            today = datetime.date.fromisoformat(sys.argv[1])
        except Exception:
            pass
    os.makedirs(OUT_DIR, exist_ok=True)
    date_str = today.strftime("%Y-%m-%d")

    log(f"目标日期: {date_str}")

    # robots.txt dump（供人工查看；被拦也能看到 blocked 标记）
    status, rtext = fetch(ROBOTS, timeout=20, raw=False)
    blocked = is_captcha(rtext) or status in (401, 403, 0)
    robots_path = os.path.join(OUT_DIR, "reuters_robots.txt")
    with open(robots_path, "w", encoding="utf-8") as f:
        f.write(f"# robots.txt fetch status={status} blocked={blocked}\n")
        f.write(rtext if isinstance(rtext, str) else rtext.decode("utf-8", "ignore"))
    log(f"robots.txt -> {robots_path} (status={status}, blocked={blocked})")

    # 1) 索引
    s, idx = fetch(NEWS_INDEX, timeout=30)
    if s != 200 or is_captcha(idx):
        log(f"!! 索引抓取失败/被拦: status={s} captcha={is_captcha(idx)}")
        # 仍写出空结果，便于 workflow 继续 commit
        json.dump({"date": date_str, "blocked": True, "status": s, "articles": []},
                  open(os.path.join(OUT_DIR, f"reuters_{date_str}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        return

    index_locs = parse_locs(idx)
    log(f"索引解析到 {len(index_locs)} 个 loc（含子 sitemap）")
    subs = pick_subsitemap(index_locs, today)

    # 2) 子 sitemap -> 文章 URL
    article_urls = []
    for sub in subs:
        s2, sxml = fetch(sub, timeout=30)
        if s2 != 200 or is_captcha(sxml):
            log(f"子 sitemap 失败: {sub} status={s2}")
            continue
        locs = parse_locs(sxml)
        # 子 sitemap 可能还是索引层
        if any("/sitemap" in u.lower() for u in locs) and len(article_urls) == 0:
            subs += [u for u in locs if u not in subs][:MAX_SUBMAPS]
            continue
        for u in locs:
            if u not in article_urls:
                article_urls.append(u)
        if len(article_urls) >= MAX_ARTICLES:
            break
    article_urls = article_urls[:MAX_ARTICLES]
    log(f"共收集文章 URL: {len(article_urls)}")

    # 3) 抓取文章
    articles = []
    for i, url in enumerate(article_urls, 1):
        s3, html = fetch(url, timeout=25)
        if s3 != 200 or is_captcha(html):
            continue
        title, body = extract_article(html)
        if not body:
            continue
        articles.append({
            "title": (title or "").strip(),
            "url": url,
            "body": body[:6000],
        })
        if i % 25 == 0:
            log(f"  已处理 {i}/{len(article_urls)}，得到 {len(articles)} 篇")

    out = {
        "date": date_str,
        "source": "Reuters (sitemap)",
        "blocked": False,
        "index_status": s,
        "article_urls_found": len(article_urls),
        "articles": articles,
    }
    out_path = os.path.join(OUT_DIR, f"reuters_{date_str}.json")
    json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"完成：{len(articles)} 篇 -> {out_path}")


if __name__ == "__main__":
    main()
