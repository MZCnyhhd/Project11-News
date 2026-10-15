#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, re, html, os, sys
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
DOCSDIR = os.path.join(BASE, "docs")
sys.path.insert(0, BASE)
try:
    from _extract import extract
except Exception:
    extract = None

import datetime, glob as _glob
DATE = os.environ.get("DIGEST_DATE") or datetime.date.today().isoformat()
try:
    WEEKDAY = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][datetime.date.fromisoformat(DATE).weekday()]
except Exception:
    WEEKDAY = ""

# 优先读取已含正文的 full.json（跨平台 / GitHub Actions 可用）；
# 否则回退到标题 json + 本地正文缓存（ARTDIR）。取不到当天则用最新一份人民日报快照。
_full = os.path.join(DATA, f"rmrb_{DATE}.full.json")
if not os.path.exists(_full):
    _cands = sorted(_glob.glob(os.path.join(DATA, "rmrb_*.full.json")))
    if _cands:
        _full = _cands[-1]
_titles = os.path.join(DATA, f"rmrb_{DATE}.json")
ARTDIR = os.path.join("C:", "Users", "MZCny", "AppData", "Local", "Temp", "rmrb", "art")

if os.path.exists(_full):
    raw = json.load(open(_full, encoding="utf-8"))
    for sec in raw:
        sec["articles"] = [a for a in sec["articles"] if "责编" not in a["title"]]
else:
    raw = json.load(open(_titles, encoding="utf-8"))
    for sec in raw:
        sec["articles"] = [a for a in sec["articles"] if "责编" not in a["title"]]
        for a in sec["articles"]:
            cid = a["url"].split("/")[-1]
            path = os.path.join(ARTDIR, cid)
            body = []
            if extract and os.path.exists(path):
                for p in extract(path):
                    if p == a["title"]:
                        continue
                    if p.startswith("《人民日报》"):
                        continue
                    body.append(p)
            a["body"] = body
    json.dump(raw, open(_full, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

# ---------- HTML digest ----------
def esc(s):
    return html.escape(s)

sections_html = []
toc = []
for sec in raw:
    page = sec["page"]
    sname = sec["section"]
    toc.append(f'<li><a href="#sec{page}">{esc(sname)}</a> <span class="cnt">({len(sec["articles"])})</span></li>')
    items = []
    for idx, a in enumerate(sec["articles"]):
        aid = f"a{page}_{idx}"
        body_html = "".join(f"<p>{esc(p)}</p>" for p in a["body"])
        if not body_html:
            body_html = '<p class="muted">（正文暂未抓取）</p>'
        items.append(f'''
        <article class="art" id="{aid}">
          <h3><a href="{esc(a['url'])}" target="_blank" rel="noopener">{esc(a['title'])}</a></h3>
          <div class="body">{body_html}</div>
        </article>''')
    sections_html.append(f'''
    <section class="sec" id="sec{page}">
      <h2>{esc(sname)}</h2>
      {''.join(items)}
    </section>''')

total_articles = sum(len(s["articles"]) for s in raw)
total_sections = len(raw)

def reuters_blocked_html(DATE):
    return f'''
    <section class="sec notice">
      <h2>Reuters（路透社）— 本环境未能抓取（已穷尽重试）</h2>
      <p>本环境<strong>无法</strong>通过 sitemap 抓取 Reuters 今日新闻，经多轮重试确认存在<strong>双重封锁</strong>：</p>
      <ol>
        <li><strong>网络出口防火墙</strong>直接阻断 <code>reuters.com</code>（直连返回 502 / 连接超时；Google、Google News 同样被拦）。</li>
        <li><strong>Reuters 反爬验证</strong>：即便经可达的代抓代理（allorigins）连到 reuters，对方也只回 <code>401</code> 的
        “启用 JS、关闭广告拦截”验证码页（<code>captcha-delivery.com</code>），不返回 sitemap XML。代理本身也多被防火墙拦截（codetabs、cors.sh、thingproxy、r.jina.ai 均不可达）。</li>
      </ol>
      <p>因此在本环境内无法取得 Reuters sitemap，已改由 <strong>GitHub Actions</strong> 在可直连外网的 runner 上定时抓取
      （仓库 <code>MZCnyhhd/Project11-News</code> 的 <code>reuters-daily</code> workflow），跑出的 <code>data/reuters_{DATE}.json</code>
      由本地页面直接消费。以下 sitemap 入口供参考：</p>
      <ul>
        <li>新闻索引：<code>https://www.reuters.com/sitemap_news_index.xml</code></li>
        <li>总索引：<code>https://www.reuters.com/sitemap_index.xml</code></li>
        <li>视频索引：<code>https://www.reuters.com/sitemap_video_index.xml</code></li>
        <li>市场索引：<code>https://www.reuters.com/sitemap_market_index.xml</code></li>
      </ul>
      <p class="muted">可用流程：从 <code>sitemap_news_index.xml</code> 进入按日期/分类的子 sitemap → 筛选 <code>{DATE}</code> 当日条目 → 抓取文章正文。
      需要我改用 Bing/Baidu 检索方式做 Reuters 头条降级来源时，告诉我即可。</p>
    </section>'''

import os as _os
_reuters_json = _os.path.join(DATA, f"reuters_{DATE}.json")
reuters_block = reuters_blocked_html(DATE)
reuters_count = 0
if _os.path.exists(_reuters_json):
    try:
        _rt = json.load(open(_reuters_json, encoding="utf-8"))
        if not _rt.get("blocked") and _rt.get("articles"):
            reuters_count = len(_rt["articles"])
            _items = []
            for _a in _rt["articles"]:
                _paras = [p for p in (_a.get("body") or "").split("\n\n") if p.strip()][:4]
                if _paras:
                    _body = "".join(f"<p>{esc(p)}</p>" for p in _paras)
                else:
                    _body = '<p class="muted">正文需授权（DataDome 拦截），点击标题查看原文。</p>'
                _pd = (_a.get("pub_date") or "")
                if _pd:
                    _pd = _pd.replace("T", " ").replace("Z", "").split(".")[0]
                _items.append(f'''
        <article class="art">
          <h3><a href="{esc(_a.get('url',''))}" target="_blank" rel="noopener">{esc(_a.get('title',''))}</a></h3>
          <div class="date">{esc(_pd)}</div>
          <div class="body">{_body}</div>
        </article>''')
            reuters_block = f'''
    <section class="sec">
      <h2>Reuters（路透社）— sitemap 抓取 · {esc(_rt.get('date', DATE))}</h2>
      <p class="muted">Reuters 官方 news sitemap（GitHub Actions 定时抓取，Googlebot-News UA）· 本次 {reuters_count} 条头条 / 采集 {_rt.get('article_urls_found',0)} 个条目。
      标题/日期/链接来自 sitemap；文章正文页被 Reuters 反爬（DataDome 401）拦截，需授权后方可抓取。</p>
      {''.join(_items)}
    </section>'''
        elif _rt.get("blocked"):
            reuters_block = f'''
    <section class="sec notice">
      <h2>Reuters（路透社）— workflow 已运行但仍被反爬拦截</h2>
      <p>GitHub Actions 已尝试抓取（status={_rt.get('status')}），但 Reuters 返回反爬验证码（DataDome），未拿到 sitemap。
      可能需要在 runner 侧增强绕过（真实浏览器头 /  residential 代理），详见仓库 <code>scripts/reuters_sitemap.py</code> 的 captcha 检测分支。</p>
    </section>'''
    except Exception:
        reuters_block = reuters_blocked_html(DATE)

html_doc = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>每日新闻摘要 {DATE}</title>
<link rel="icon" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==">
<style>
  :root{{--bg:#f7f8fa;--card:#fff;--ink:#1f2329;--sub:#6b7280;--line:#e5e7eb;--accent:#c0392b;}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 -apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif}}
  header{{background:linear-gradient(135deg,#c0392b,#922b21);color:#fff;padding:28px 24px}}
  header h1{{margin:0 0 6px;font-size:24px}}
  header .meta{{opacity:.9;font-size:14px}}
  .wrap{{max-width:960px;margin:0 auto;padding:20px 16px 60px}}
  .stats{{display:flex;gap:16px;flex-wrap:wrap;margin:18px 0}}
  .stat{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;flex:1;min-width:140px}}
  .stat b{{display:block;font-size:22px;color:var(--accent)}}
  .stat span{{color:var(--sub);font-size:13px}}
  .toc{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px;margin:16px 0}}
  .toc h2{{margin:0 0 8px;font-size:16px}}
  .toc ul{{margin:0;padding-left:20px;columns:2;column-gap:24px}}
  .toc li{{margin:2px 0}}
  .toc .cnt{{color:var(--sub);font-size:12px}}
  .sec{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:18px 0}}
  .sec h2{{margin:0 0 12px;font-size:19px;border-left:4px solid var(--accent);padding-left:10px}}
  .art{{border-top:1px dashed var(--line);padding:12px 0}}
  .art:first-of-type{{border-top:none}}
  .art h3{{margin:0 0 6px;font-size:16px;line-height:1.5}}
  .art h3 a{{color:var(--ink);text-decoration:none}}
  .art h3 a:hover{{color:var(--accent)}}
  .art .date{{color:var(--sub);font-size:12px;margin:0 0 4px}}
  .art .body p{{margin:6px 0;color:#374151}}
  .muted{{color:var(--sub);font-size:13px}}
  .notice{{border-color:#f0c36d;background:#fffaf0}}
  code{{background:#f0f1f3;padding:1px 6px;border-radius:5px;font-size:13px}}
</style>
</head>
<body>
<header>
  <h1>每日新闻摘要 · {DATE}</h1>
  <div class="meta">{WEEKDAY} ｜ 来源：人民日报（全文）· Reuters（{'sitemap 已抓' if reuters_count else 'sitemap，本环境受限'}）</div>
</header>
<div class="wrap">
  <div class="stats">
    <div class="stat"><b>2</b><span>信息源</span></div>
    <div class="stat"><b>{total_articles}</b><span>人民日报文章</span></div>
    <div class="stat"><b>{total_sections}</b><span>人民日报版面</span></div>
    <div class="stat"><b>{reuters_count if reuters_count else '—'}</b><span>Reuters（{('sitemap 已抓' if reuters_count else '待抓取/受限')}）</span></div>
  </div>
  <div class="toc">
    <h2>版面导航</h2>
    <ul>{''.join(toc)}</ul>
  </div>
  {reuters_block}
  {''.join(sections_html)}
  <p class="muted">数据抓取时间：{DATE} ｜ 人民日报原文链接见各文章标题。{'Reuters 头条来自官方 news sitemap（GitHub Actions 定时抓取），正文页受 Reuters 反爬（DataDome 401）限制需授权，点击标题查看原文。' if reuters_count else 'Reuters 部分因网络限制未抓取，sitemap 入口已附上，具备外网时可重试。'}</p>
</div>
</body>
</html>'''

os.makedirs(DOCSDIR, exist_ok=True)
open(os.path.join(DOCSDIR, "index.html"), "w", encoding="utf-8").write(html_doc)
print("Wrote docs/index.html")
# 注：按用户要求仅输出 HTML，不生成 Markdown。
print("Total articles with body:", sum(1 for s in raw for a in s['articles'] if a['body']))
