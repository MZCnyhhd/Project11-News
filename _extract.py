#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, re
from html.parser import HTMLParser

class ArtParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_article = False
        self.depth = 0
        self.in_p = False
        self.cur = []
        self.paras = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == 'div':
            cls = ' '.join(d.get('class', '').split())
            if 'article' in cls.split() and not self.in_article:
                self.in_article = True
                self.depth = 0
            if self.in_article:
                self.depth += 1
        elif tag == 'p' and self.in_article:
            self.in_p = True
            self.cur = []

    def handle_endtag(self, tag):
        if not self.in_article:
            return
        if tag == 'p':
            self.in_p = False
            txt = ''.join(self.cur).strip()
            if txt:
                self.paras.append(txt)
            self.cur = []
        elif tag == 'div':
            self.depth -= 1
            if self.depth <= 0:
                self.in_article = False

    def handle_data(self, data):
        if self.in_article and self.in_p:
            self.cur.append(data)

def extract(path):
    html = open(path, encoding='utf-8', errors='ignore').read()
    p = ArtParser()
    p.feed(html)
    # dedupe consecutive identical paragraphs
    out = []
    for t in p.paras:
        t = re.sub(r'\s+', ' ', t).strip()
        if t and (not out or out[-1] != t):
            out.append(t)
    return out

if __name__ == '__main__':
    paras = extract(sys.argv[1])
    print(f"paragraphs: {len(paras)}")
    for t in paras[:6]:
        print('-', t[:120])
