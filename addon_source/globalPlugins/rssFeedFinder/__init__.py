# -*- coding: utf-8 -*-
# RSS Feed & Category Finder global plugin for NVDA
# Copyright (C) 2026 Sushil Chaudhary
# This file is covered by the GNU General Public License v2.0.
# See the file LICENSE for more details.

import wx
import gui
import ui
import globalPluginHandler
import scriptHandler
import globalVars
import api
import threading
import os
import addonHandler
import urllib.request
import urllib.parse
import urllib.error
import re
import json
import ssl
import gzip
import zlib
import webbrowser
import html
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime

addonHandler.initTranslation()

# ---------------------------------------------------------------------------
# Network Utilities (Unicode-Safe URL Encoding, Resilient SSL & Gzip/Deflate)
# ---------------------------------------------------------------------------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, text/html, */*",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


def safe_iri_to_uri(raw_url):
    if not raw_url:
        return ""
    u = raw_url.strip()
    try:
        parsed = urllib.parse.urlsplit(u)
        safe_path = urllib.parse.quote(urllib.parse.unquote(parsed.path), safe="/:@!$&'()*+,;=-._~%")
        safe_query = urllib.parse.quote(urllib.parse.unquote(parsed.query), safe="=&/:@!$'()*+,;-._~%")
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, safe_path, safe_query, ""))
    except Exception:
        return u


def _decode_response_bytes(raw_bytes, headers):
    if not raw_bytes:
        return ""
    encoding = ""
    if headers:
        try:
            encoding = (headers.get("Content-Encoding") or "").lower()
        except Exception:
            encoding = ""

    data = raw_bytes
    if "gzip" in encoding or (len(data) > 2 and data[:2] == b"\x1f\x8b"):
        try:
            data = gzip.decompress(data)
        except Exception:
            pass
    elif "deflate" in encoding:
        try:
            data = zlib.decompress(data, -zlib.MAX_WBITS)
        except Exception:
            try:
                data = zlib.decompress(data)
            except Exception:
                pass

    for charset in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            return data.decode(charset)
        except Exception:
            continue
    return data.decode("utf-8", errors="ignore")


def fetch_url(url, timeout=9):
    safe_url = safe_iri_to_uri(url)
    if not safe_url:
        return None, None, None

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    except Exception:
        pass

    try:
        req = urllib.request.Request(safe_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
            status = getattr(response, "status", None) or response.getcode() or 200
            body_str = _decode_response_bytes(response.read(), response.headers)
            return status, response.headers, body_str
    except Exception:
        if safe_url.startswith("https://"):
            http_url = "http://" + safe_url[8:]
            try:
                req_http = urllib.request.Request(http_url, headers=HEADERS)
                with urllib.request.urlopen(req_http, timeout=timeout) as response:
                    status = getattr(response, "status", None) or response.getcode() or 200
                    body_str = _decode_response_bytes(response.read(), response.headers)
                    return status, response.headers, body_str
            except Exception:
                pass
        return None, None, None


# ---------------------------------------------------------------------------
# RSS Probing, Auto-Categorization & Sub-Category Feed Discovery Utilities
# ---------------------------------------------------------------------------
FEED_PATHS = [
    "feed", "feed/", "rss", "rss/", "rss.xml", "feed.xml", "atom.xml",
    "feeds", "feeds/", "index.xml", "news.xml", "xml/rss/all.xml",
    "?feed=rss2", "?format=feed&type=rss",
    "feed/rss", "feed/atom", "wp-rss2.php",
]

COMMON_CATEGORY_SLUGS = [
    ("health", "Health"),
    ("lifestyle", "Lifestyle"),
    ("lifeandstyle", "Lifestyle"),
    ("life-style", "Lifestyle"),
    ("sports", "Sports"),
    ("sport", "Sports"),
    ("business", "Business & Economy"),
    ("economy", "Business & Economy"),
    ("markets", "Business & Economy"),
    ("technology", "Technology & Science"),
    ("tech", "Technology & Science"),
    ("science", "Technology & Science"),
    ("entertainment", "Entertainment"),
    ("arts", "Entertainment"),
    ("education", "Education"),
    ("world", "International / World"),
    ("international", "International / World"),
    ("global", "International / World"),
    ("politics", "Politics & Governance"),
    ("national", "General News"),
    ("news", "General News"),
    ("opinion", "Opinion & Analysis"),
    ("literature", "Literature & Culture"),
    ("culture", "Literature & Culture"),
    ("society", "Society & Crime"),
    ("social", "Society & Crime"),
    ("environment", "Agriculture & Environment"),
    ("agriculture", "Agriculture & Environment"),
]

KNOWN_PUBLISHER_FEEDS = {
    "bbc.com": [
        ("BBC News - Top Stories", "https://feeds.bbci.co.uk/news/rss.xml", "https://www.bbc.com/news", "General News"),
        ("BBC News - World", "https://feeds.bbci.co.uk/news/world/rss.xml", "https://www.bbc.com/news/world", "International / World"),
        ("BBC News - Business", "https://feeds.bbci.co.uk/news/business/rss.xml", "https://www.bbc.com/news/business", "Business & Economy"),
        ("BBC News - Health", "https://feeds.bbci.co.uk/news/health/rss.xml", "https://www.bbc.com/news/health", "Health"),
        ("BBC News - Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml", "https://www.bbc.com/news/technology", "Technology & Science"),
        ("BBC News - Science & Environment", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "https://www.bbc.com/news/science_and_environment", "Technology & Science"),
        ("BBC News - Education", "https://feeds.bbci.co.uk/news/education/rss.xml", "https://www.bbc.com/news/education", "Education"),
        ("BBC News - Entertainment & Arts", "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml", "https://www.bbc.com/news/entertainment_and_arts", "Entertainment"),
        ("BBC News - Politics", "https://feeds.bbci.co.uk/news/politics/rss.xml", "https://www.bbc.com/news/politics", "Politics & Governance"),
        ("BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml", "https://www.bbc.com/sport", "Sports"),
    ],
    "cnn.com": [
        ("CNN - Top Stories", "http://rss.cnn.com/rss/edition.rss", "https://www.cnn.com", "General News"),
        ("CNN - World", "http://rss.cnn.com/rss/edition_world.rss", "https://www.cnn.com/world", "International / World"),
        ("CNN - Business & Money", "http://rss.cnn.com/rss/money_latest.rss", "https://www.cnn.com/business", "Business & Economy"),
        ("CNN - Technology", "http://rss.cnn.com/rss/edition_technology.rss", "https://www.cnn.com/business/tech", "Technology & Science"),
        ("CNN - Science & Space", "http://rss.cnn.com/rss/edition_space.rss", "https://www.cnn.com/science", "Technology & Science"),
        ("CNN - Entertainment", "http://rss.cnn.com/rss/edition_entertainment.rss", "https://www.cnn.com/entertainment", "Entertainment"),
        ("CNN - World Sport", "http://rss.cnn.com/rss/edition_sport.rss", "https://www.cnn.com/sport", "Sports"),
        ("CNN - Travel & Lifestyle", "http://rss.cnn.com/rss/edition_travel.rss", "https://www.cnn.com/travel", "Lifestyle"),
    ],
    "nytimes.com": [
        ("NYT - Home Page", "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "https://www.nytimes.com", "General News"),
        ("NYT - World", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "https://www.nytimes.com/section/world", "International / World"),
        ("NYT - Politics", "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml", "https://www.nytimes.com/section/politics", "Politics & Governance"),
        ("NYT - Business", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "https://www.nytimes.com/section/business", "Business & Economy"),
        ("NYT - Technology", "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "https://www.nytimes.com/section/technology", "Technology & Science"),
        ("NYT - Science", "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml", "https://www.nytimes.com/section/science", "Technology & Science"),
        ("NYT - Health", "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml", "https://www.nytimes.com/section/health", "Health"),
        ("NYT - Sports", "https://rss.nytimes.com/services/xml/rss/nyt/Sports.xml", "https://www.nytimes.com/section/sports", "Sports"),
        ("NYT - Arts & Entertainment", "https://rss.nytimes.com/services/xml/rss/nyt/Arts.xml", "https://www.nytimes.com/section/arts", "Entertainment"),
        ("NYT - Fashion & Style", "https://rss.nytimes.com/services/xml/rss/nyt/FashionandStyle.xml", "https://www.nytimes.com/section/style", "Lifestyle"),
        ("NYT - Education", "https://rss.nytimes.com/services/xml/rss/nyt/Education.xml", "https://www.nytimes.com/section/education", "Education"),
    ],
    "washingtonpost.com": [
        ("Washington Post - World", "https://feeds.washingtonpost.com/rss/world", "https://www.washingtonpost.com/world", "International / World"),
        ("Washington Post - Politics", "https://feeds.washingtonpost.com/rss/politics", "https://www.washingtonpost.com/politics", "Politics & Governance"),
        ("Washington Post - National", "https://feeds.washingtonpost.com/rss/national", "https://www.washingtonpost.com/national", "General News"),
        ("Washington Post - Business", "https://feeds.washingtonpost.com/rss/business", "https://www.washingtonpost.com/business", "Business & Economy"),
        ("Washington Post - Technology", "https://feeds.washingtonpost.com/rss/business/technology", "https://www.washingtonpost.com/business/technology", "Technology & Science"),
        ("Washington Post - Sports", "https://feeds.washingtonpost.com/rss/sports", "https://www.washingtonpost.com/sports", "Sports"),
        ("Washington Post - Lifestyle", "https://feeds.washingtonpost.com/rss/lifestyle", "https://www.washingtonpost.com/lifestyle", "Lifestyle"),
        ("Washington Post - Entertainment", "https://feeds.washingtonpost.com/rss/entertainment", "https://www.washingtonpost.com/entertainment", "Entertainment"),
        ("Washington Post - Opinions", "https://feeds.washingtonpost.com/rss/opinions", "https://www.washingtonpost.com/opinions", "Opinion & Analysis"),
    ],
    "foxnews.com": [
        ("Fox News - Latest", "https://moxie.foxnews.com/google-publisher/latest.xml", "https://www.foxnews.com", "General News"),
        ("Fox News - World", "https://moxie.foxnews.com/google-publisher/world.xml", "https://www.foxnews.com/world", "International / World"),
        ("Fox News - Politics", "https://moxie.foxnews.com/google-publisher/politics.xml", "https://www.foxnews.com/politics", "Politics & Governance"),
        ("Fox News - Science", "https://moxie.foxnews.com/google-publisher/science.xml", "https://www.foxnews.com/science", "Technology & Science"),
        ("Fox News - Tech", "https://moxie.foxnews.com/google-publisher/tech.xml", "https://www.foxnews.com/tech", "Technology & Science"),
        ("Fox News - Health", "https://moxie.foxnews.com/google-publisher/health.xml", "https://www.foxnews.com/health", "Health"),
        ("Fox News - Sports", "https://moxie.foxnews.com/google-publisher/sports.xml", "https://www.foxnews.com/sports", "Sports"),
        ("Fox News - Travel & Lifestyle", "https://moxie.foxnews.com/google-publisher/travel.xml", "https://www.foxnews.com/travel", "Lifestyle"),
        ("Fox News - Opinion", "https://moxie.foxnews.com/google-publisher/opinion.xml", "https://www.foxnews.com/opinion", "Opinion & Analysis"),
    ],
    "nbcnews.com": [
        ("NBC News - Top Stories", "https://feeds.nbcnews.com/nbcnews/public/news", "https://www.nbcnews.com", "General News"),
        ("NBC News - World", "https://feeds.nbcnews.com/nbcnews/public/world", "https://www.nbcnews.com/world", "International / World"),
        ("NBC News - Business", "https://feeds.nbcnews.com/nbcnews/public/business", "https://www.nbcnews.com/business", "Business & Economy"),
        ("NBC News - Tech", "https://feeds.nbcnews.com/nbcnews/public/tech", "https://www.nbcnews.com/tech-media", "Technology & Science"),
        ("NBC News - Science", "https://feeds.nbcnews.com/nbcnews/public/science", "https://www.nbcnews.com/science", "Technology & Science"),
        ("NBC News - Health", "https://feeds.nbcnews.com/nbcnews/public/health", "https://www.nbcnews.com/health", "Health"),
        ("NBC News - Politics", "https://feeds.nbcnews.com/nbcnews/public/politics", "https://www.nbcnews.com/politics", "Politics & Governance"),
    ],
    "abcnews.go.com": [
        ("ABC News - Top Stories", "https://abcnews.go.com/abcnews/topstories", "https://abcnews.go.com", "General News"),
        ("ABC News - International", "https://abcnews.go.com/abcnews/internationalheadlines", "https://abcnews.go.com/International", "International / World"),
        ("ABC News - Politics", "https://abcnews.go.com/abcnews/politicsheadlines", "https://abcnews.go.com/Politics", "Politics & Governance"),
        ("ABC News - Business & Money", "https://abcnews.go.com/abcnews/moneyheadlines", "https://abcnews.go.com/Business", "Business & Economy"),
        ("ABC News - Technology", "https://abcnews.go.com/abcnews/technologyheadlines", "https://abcnews.go.com/Technology", "Technology & Science"),
        ("ABC News - Health", "https://abcnews.go.com/abcnews/healthheadlines", "https://abcnews.go.com/Health", "Health"),
        ("ABC News - Entertainment", "https://abcnews.go.com/abcnews/entertainmentheadlines", "https://abcnews.go.com/Entertainment", "Entertainment"),
        ("ABC News - Sports", "https://abcnews.go.com/abcnews/sportsheadlines", "https://abcnews.go.com/Sports", "Sports"),
        ("ABC News - Travel & Lifestyle", "https://abcnews.go.com/abcnews/travelheadlines", "https://abcnews.go.com/Travel", "Lifestyle"),
    ],
}

CATEGORY_RULES = [
    ("Health", [
        "health", "swasthya", "medical", "hospital", "doctor", "clinic", "pharma",
        "nursing", "fitness", "nutrition", "mental-health", "sex-health", "ayurved",
        "wellness", "disease", "स्वास्थ्य", "मेडिकल", "अस्पताल", "चिकित्सा", "डाक्टर", "हेल्थ", "आयुर्वेद", "यौन"
    ]),
    ("Lifestyle", [
        "lifestyle", "life-style", "lifeandstyle", "fashion", "beauty", "nepalbeauty", "living",
        "food", "recipe", "relationship", "family", "home-decor", "horoscope",
        "rashifal", "astrology", "women", "youth", "travel", "ghumphir", "style",
        "जीवनशैली", "फेशन", "सौन्दर्य", "राशिफल", "महिला", "युवा", "खानपान", "परिवार", "यात्रा", "घुमफिर"
    ]),
    ("Sports", [
        "sport", "sports", "khel", "khelkud", "cricket", "football", "soccer",
        "olympic", "worldcup", "13-sag", "athletics",
        "खेल", "खेलकुद", "क्रिकेट", "फुटबल", "साग"
    ]),
    ("Technology & Science", [
        "tech", "technology", "ict", "science", "cyber", "digital", "gadget",
        "mobile", "telecom", "ai", "innovation", "startup", "auto", "automobile", "space",
        "प्रविधि", "सूचना प्रविधि", "विज्ञान", "डिजिटल", "साइबर", "अटो"
    ]),
    ("Business & Economy", [
        "business", "biz", "economy", "economic", "eco-policy", "artha", "aarthik",
        "arthik", "finance", "financial", "market", "markets", "share", "stock",
        "nepse", "ipo", "mutual-fund", "bank", "banking", "corporate", "trade",
        "industry", "tax", "karobar", "lagani", "byapar", "tourism", "real-estate",
        "employment", "rojgar", "kinmel", "money",
        "आर्थिक", "अर्थ", "अर्थनीति", "बिजनेस", "विजनेश", "बैंक", "बैंकिङ", "शेयर", "सेयर",
        "बजार", "लगानी", "कारोबार", "व्यापार", "उद्योग", "कर्पोरेट", "रोजगार", "पर्यटन", "किनमेल"
    ]),
    ("Entertainment", [
        "entertainment", "ent-news", "manoranjan", "cinema", "cine", "film",
        "movie", "bollywood", "hollywood", "kollywood", "music", "song",
        "celebrity", "gossip", "actor", "actress", "glamour", "arts", "kala",
        "मनोरञ्जन", "मनोरन्जन", "चलचित्र", "फिल्म", "सिनेमा", "बलिउड", "हलिउड", "कला", "संगीत", "तस्वीर"
    ]),
    ("Education", [
        "education", "educational", "edu", "shiksha", "school", "college",
        "university", "campus", "student", "exam", "scholarship", "loksewa",
        "शिक्षा", "शैक्षिक", "स्कुल", "विद्यालय", "कलेज", "विश्वविद्यालय", "परीक्षा", "लोकसेवा", "विद्यार्थी"
    ]),
    ("Literature & Culture", [
        "literature", "literary", "sahitya", "poem", "poetry", "story", "novel",
        "book", "culture", "religion", "koseli", "sathiya",
        "साहित्य", "साहित्यिक", "कविता", "कथा", "संस्कृति", "धर्म", "कोसेली", "गजल", "लेख", "साहित्यपाटी"
    ]),
    ("International / World", [
        "international", "world", "global", "foreign", "bidesh", "prabas",
        "prabhas", "diaspora", "nrn",
        "अन्तर्राष्ट्रिय", "विश्व", "विदेश", "प्रवास", "ग्लोबल"
    ]),
    ("Opinion & Analysis", [
        "opinion", "opinions", "vichar", "bichar", "editorial", "analysis", "column", "blog",
        "interview", "feature", "factcheck",
        "विचार", "सम्पादकीय", "विश्लेषण", "अन्तर्वार्ता", "फिचर", "ब्लग", "दृष्टिकोण"
    ]),
    ("Agriculture & Environment", [
        "agriculture", "krishi", "farming", "farmer", "environment", "climate",
        "nature", "weather", "energy", "hydropower",
        "कृषि", "किसान", "वातावरण", "जलवायु", "ऊर्जा"
    ]),
    ("Politics & Governance", [
        "politics", "political", "rajniti", "parliament", "election", "government",
        "constitution", "policy", "diplomacy",
        "राजनीति", "संसद", "निर्वाचन", "चुनाव", "सरकार"
    ]),
    ("Provincial / Regional", [
        "province", "pradesh", "koshi", "madhesh", "bagmati", "gandaki", "lumbini",
        "karnali", "sudurpashchim", "valley", "desh-samachar", "local",
        "प्रदेश", "कोशी", "मधेस", "मधेश", "बागमती", "गण्डकी", "लुम्बिनी", "कर्णाली", "सुदूरपश्चिम", "उपत्यका", "स्थानीय"
    ]),
    ("Society & Crime", [
        "society", "samaj", "social", "crime", "police", "court", "law",
        "justice", "human-rights", "accident",
        "समाज", "अपराध", "कानुन", "प्रहरी", "अदालत"
    ]),
]

IGNORE_SEGMENTS = {
    "wp-admin", "wp-login.php", "wp-content", "wp-includes", "wp-json",
    "login", "logout", "register", "signup", "signin", "account", "profile",
    "about", "about-us", "contact", "contact-us", "privacy", "privacy-policy",
    "terms", "terms-and-conditions", "disclaimer", "advertise", "advertisement",
    "team", "our-team", "career", "careers", "search", "tag", "tags", "author",
    "authors", "page", "comments", "cart", "checkout", "cdn-cgi", "feed", "rss",
    "unicode", "preeti-to-unicode", "date-converter", "forex", "gold-silver",
    "rashifal-daily", "epaper", "archive", "live", "video", "videos", "gallery", "photo"
}


def normalize_url(url):
    url = (url or "").strip().rstrip("/")
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    return url


def canonical_feed_key(url):
    u = (url or "").strip().lower().rstrip("/")
    u = re.sub(r"^https?://(www\.)?", "", u)
    return u


def get_origin_and_path(raw_url):
    norm = normalize_url(raw_url)
    try:
        parsed = urllib.parse.urlparse(norm)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        clean_path = parsed.path.strip("/")
        segments = [s for s in clean_path.split("/") if s] if clean_path else []
        last_slug = segments[-1].lower() if segments else ""
        return origin, norm, parsed.netloc, clean_path, last_slug
    except Exception:
        return norm, norm, norm, "", ""


def get_known_publisher_feeds(hostname):
    root_dom = (hostname or "").lower().lstrip("www.")
    if root_dom in KNOWN_PUBLISHER_FEEDS:
        return KNOWN_PUBLISHER_FEEDS[root_dom]
    for k, v in KNOWN_PUBLISHER_FEEDS.items():
        if root_dom.endswith("." + k):
            return v
    return None


def is_feed_response(headers, body, reject_comments=True):
    if not body or not isinstance(body, str):
        return False
    preview = body.strip()[:4000].lower()
    if preview.startswith("<!doctype html") or preview.startswith("<html"):
        return False
    has_xml = (
        "<rss" in preview
        or "<feed" in preview
        or "<channel>" in preview
        or "<rdf:rdf" in preview
    )
    if not has_xml:
        return False
    if reject_comments:
        t_match = re.search(r"<title[^>]*>(.*?)</title>", preview, re.DOTALL | re.IGNORECASE)
        if t_match:
            t_text = t_match.group(1).strip()
            if t_text.startswith("comments on:") or t_text.startswith("टिप्पणीहरू:") or "comments feed" in t_text:
                return False
    return True


def extract_feed_meta(body):
    if not body or not isinstance(body, str):
        return "", []
    preview = body[:25000]
    t_match = re.search(r"<title[^>]*>(.*?)</title>", preview, re.DOTALL | re.IGNORECASE)
    title = ""
    if t_match:
        raw_t = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", t_match.group(1), flags=re.DOTALL).strip()
        title = html.unescape(raw_t)
    cat_matches = re.findall(r"<category[^>]*>(.*?)</category>", preview, re.DOTALL | re.IGNORECASE)
    freq = {}
    for c_raw in cat_matches[:30]:
        c_clean = html.unescape(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", c_raw, flags=re.DOTALL).strip())
        if c_clean:
            k = c_clean.lower()
            freq[k] = freq.get(k, 0) + 1
    categories = [k for k, cnt in freq.items() if cnt >= 2]
    return title, categories


def match_category_rule(text):
    if not text or not text.strip():
        return None
    lower = text.lower()
    for cat_name, keywords in CATEGORY_RULES:
        for kw in keywords:
            if len(kw) <= 3 and kw.isalpha() and kw.isascii():
                if re.search(rf"(^|[^a-z0-9]){re.escape(kw)}([^a-z0-9]|$)", lower):
                    return cat_name
            elif kw.lower() in lower:
                return cat_name
    return None


_match_category_rule = match_category_rule


def detect_category(name="", url="", feed_url="", folder_name="", feed_title="", feed_categories=None):
    target_u = re.sub(r"/+(feed|rss|atom)(\.xml)?/?$", "", (feed_url or url), flags=re.IGNORECASE)
    leaf_path = " ".join(target_u.split("/")[-2:])
    if folder_name:
        mf = match_category_rule(folder_name)
        if mf:
            return mf
    m1 = match_category_rule(f"{name} {leaf_path}")
    if m1:
        return m1
    m2 = match_category_rule(f"{feed_title} {url} {feed_url}")
    if m2:
        return m2
    if feed_categories:
        m3 = match_category_rule(" ".join(feed_categories))
        if m3:
            return m3
    if folder_name and folder_name.strip():
        return folder_name.strip()
    return "General News"


def check_feed_url_with_meta(url, reject_comments=True, timeout=7):
    status, headers, body = fetch_url(url, timeout=timeout)
    if status == 200 and is_feed_response(headers, body, reject_comments):
        title, cats = extract_feed_meta(body)
        return {"feed_url": url, "title": title, "categories": cats}
    return None


def find_all_feeds_in_html(page_url):
    alternates = []
    status, headers, body = fetch_url(page_url, timeout=9)
    if status == 200 and body:
        if is_feed_response(headers, body, True):
            title, _ = extract_feed_meta(body)
            alternates.append({"url": page_url, "title": title or page_url})
            return alternates, ""

        link_tags = re.findall(r"<link[^>]+>", body, re.IGNORECASE)
        for tag in link_tags:
            if not re.search(r"application/(?:rss|atom)\+xml", tag, re.IGNORECASE):
                continue
            href_m = re.search(r'href=["\']([^"\']+)["\']', tag, re.IGNORECASE)
            if not href_m:
                continue
            title_m = re.search(r'title=["\']([^"\']+)["\']', tag, re.IGNORECASE)
            raw_href = html.unescape(href_m.group(1)).strip()
            resolved_href = raw_href if raw_href.startswith("http") else urllib.parse.urljoin(page_url, raw_href)
            if re.search(r"/comments/feed/?$", resolved_href, re.IGNORECASE):
                continue
            title = html.unescape(title_m.group(1)).strip() if title_m else ""
            if "comments feed" in title.lower() or title.lower().startswith("comments on:"):
                continue
            alternates.append({"url": resolved_href, "title": title})
        return alternates, body
    return [], ""


def find_feed_in_homepage(base_url):
    alternates, _ = find_all_feeds_in_html(base_url)
    if alternates:
        _, _, _, _, last_slug = get_origin_and_path(base_url)
        if last_slug:
            for alt in alternates:
                if last_slug in alt["url"].lower():
                    verified = check_feed_url_with_meta(alt["url"])
                    if verified:
                        return verified
        for alt in alternates:
            verified = check_feed_url_with_meta(alt["url"])
            if verified:
                return verified
    return None


def check_site_feed_full(site):
    name = site.get("name", "")
    url = site.get("url", "")
    folder_name = site.get("category", "")
    base_url = normalize_url(url)
    origin, _, hostname, pathname, _ = get_origin_and_path(base_url)

    known_list = get_known_publisher_feeds(hostname)
    if known_list:
        matched = known_list[0]
        if pathname:
            for item in known_list:
                if pathname.lower() in item[2].lower() or pathname.lower() in item[1].lower():
                    matched = item
                    break
        cat = detect_category(name, url, matched[1], folder_name, matched[0]) if folder_name else matched[3]
        return matched[1], "publisher_registry", cat, matched[0]

    if pathname:
        sub_candidates = [
            f"{base_url}/feed",
            f"{base_url}/rss",
            f"{base_url}/rss.xml",
            f"{origin}/content/{pathname}/feed",
            f"{origin}/category/{pathname}/feed",
            f"{origin}/category/{pathname}/rss",
            f"{base_url}.xml",
        ]
        with ThreadPoolExecutor(max_workers=7) as ex:
            futs = {ex.submit(check_feed_url_with_meta, cand, True, 5): cand for cand in sub_candidates}
            for fut in as_completed(futs):
                try:
                    meta = fut.result()
                    if meta:
                        cat = detect_category(name, url, meta["feed_url"], folder_name, meta["title"], meta["categories"])
                        return meta["feed_url"], "subpath_probe", cat, meta["title"]
                except Exception:
                    pass

    auto = find_feed_in_homepage(base_url)
    if auto:
        cat = detect_category(name, url, auto["feed_url"], folder_name, auto["title"], auto["categories"])
        return auto["feed_url"], "autodiscovery", cat, auto["title"]

    probe_urls = [base_url + "/" + p.lstrip("/") for p in FEED_PATHS[:10]]
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(check_feed_url_with_meta, u, True, 5): u for u in probe_urls}
        for fut in as_completed(futs):
            try:
                found = fut.result()
                if found:
                    cat = detect_category(name, url, found["feed_url"], folder_name, found["title"], found["categories"])
                    return found["feed_url"], "probe", cat, found["title"]
            except Exception:
                pass

    return None, None, detect_category(name, url, "", folder_name), ""


def discover_site_category_feeds(target_url):
    origin, full_url, hostname, pathname, last_slug = get_origin_and_path(target_url)
    verified_feeds = []
    seen_keys = set()

    def add_verified(name, page_url, feed_url, feed_title="", feed_categories=None, category=None, priority=5):
        if not feed_url:
            return
        clean_feed = feed_url.strip().rstrip("/")
        k = canonical_feed_key(clean_feed)
        if k in seen_keys:
            return
        seen_keys.add(k)
        disp_name = html.unescape(name if (name and not name.startswith("http")) else (feed_title or name or hostname)).strip()
        cat_name = category or detect_category(
            name=disp_name,
            url=page_url or origin,
            feed_url=clean_feed,
            feed_title=feed_title or disp_name,
            feed_categories=feed_categories or [],
        )
        verified_feeds.append({
            "name": disp_name,
            "category": cat_name,
            "page_url": page_url or origin,
            "feed_url": clean_feed,
            "feed_title": html.unescape(feed_title or disp_name).strip(),
            "priority": priority,
        })

    # 1. Known Publisher Registry (BBC, CNN, NYT, WaPo, Fox, NBC, ABC)
    known_list = get_known_publisher_feeds(hostname)
    if known_list:
        for item_name, item_feed, item_page, item_cat in known_list:
            prio = 1 if (pathname and (pathname.lower() in item_page.lower() or pathname.lower() in item_feed.lower())) else 2
            add_verified(item_name, item_page, item_feed, item_name, [], item_cat, prio)

    # 2. WordPress REST API with Cloudflare WAF ?cat=ID fallback (only if not in known registry)
    if not known_list:
        wp_queries = [f"{origin}/wp-json/wp/v2/categories?per_page=70"]
        if last_slug:
            wp_queries.insert(0, f"{origin}/wp-json/wp/v2/categories?search={urllib.parse.quote(last_slug)}&per_page=20")

        wp_cats = []
        seen_wp_ids = set()
        for q_url in wp_queries:
            try:
                status, _, body = fetch_url(q_url, timeout=6)
                if status == 200 and body:
                    cats_data = json.loads(body)
                    if isinstance(cats_data, list):
                        for cat in cats_data:
                            if not isinstance(cat, dict):
                                continue
                            cid = cat.get("id")
                            link = (cat.get("link") or "").strip().rstrip("/")
                            count = cat.get("count", 0)
                            cslug = str(cat.get("slug") or "").lower()
                            if not cid or not link or (isinstance(count, int) and count <= 0) or cslug in ("uncategorized", "uncategorised"):
                                continue
                            if cid not in seen_wp_ids:
                                seen_wp_ids.add(cid)
                                wp_cats.append(cat)
            except Exception:
                pass

        if wp_cats:
            wp_cats.sort(key=lambda c: c.get("count", 0), reverse=True)
            sample = wp_cats[0]
            s_link = sample["link"].strip().rstrip("/")
            wp_mode = None
            wp_probe_candidates = [
                ("path_feed", f"{s_link}/feed"),
                ("query_cat", f"{origin}/feed/?cat={sample['id']}"),
                ("rss2_cat", f"{origin}/?feed=rss2&cat={sample['id']}"),
            ]
            with ThreadPoolExecutor(max_workers=3) as ex:
                futs = {ex.submit(check_feed_url_with_meta, u, True, 5): mode for mode, u in wp_probe_candidates}
                results_mode = {}
                for fut in as_completed(futs):
                    mode = futs[fut]
                    try:
                        if fut.result():
                            results_mode[mode] = True
                    except Exception:
                        pass
                for mode in ("path_feed", "query_cat", "rss2_cat"):
                    if results_mode.get(mode):
                        wp_mode = mode
                        break

            if wp_mode:
                add_verified(f"{hostname} (Main Feed)", origin, f"{origin}/feed", f"{hostname} - Main Feed", [], "General News", 2 if pathname else 1)
                for cat in wp_cats[:55]:
                    c_link = cat["link"].strip().rstrip("/")
                    c_slug = str(cat.get("slug") or "").lower()
                    c_feed = (
                        f"{c_link}/feed" if wp_mode == "path_feed"
                        else f"{origin}/feed/?cat={cat['id']}" if wp_mode == "query_cat"
                        else f"{origin}/?feed=rss2&cat={cat['id']}"
                    )
                    is_match = bool(last_slug and (last_slug in c_slug or last_slug in c_link.lower()))
                    add_verified(
                        cat.get("name") or c_slug or "Category",
                        c_link,
                        c_feed,
                        f"{cat.get('name')} - {hostname}",
                        [],
                        None,
                        1 if is_match else 2,
                    )

    # 3. Scrape HTML from targetUrl and root origin if not enough feeds yet
    if len(verified_feeds) < 5:
        pages_to_inspect = [full_url, origin] if pathname else [origin]
        scraped_sections = {}
        direct_feeds = []
        all_alternates = []

        for idx, base_page in enumerate(pages_to_inspect):
            try:
                alternates, html_body = find_all_feeds_in_html(base_page)
                for alt in alternates:
                    all_alternates.append((alt, base_page, 1 if (idx == 0 and pathname) else 2))

                if not html_body:
                    continue

                for m in re.finditer(r'<a[^>]+href=["\']([^"\'#?]+)["\'][^>]*>(.*?)</a>', html_body, re.DOTALL | re.IGNORECASE):
                    raw_href = html.unescape(m.group(1)).strip()
                    link_text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(2)))).strip()
                    if not raw_href or raw_href.startswith(("javascript:", "mailto:", "tel:")):
                        continue
                    try:
                        resolved_url = urllib.parse.urljoin(base_page, raw_href)
                        p_res = urllib.parse.urlparse(resolved_url)
                    except Exception:
                        continue
                    if p_res.netloc.lower().lstrip("www.") != hostname.lower().lstrip("www."):
                        continue
                    clean_path = p_res.path.strip("/")
                    if not clean_path:
                        continue
                    segments = clean_path.split("/")
                    if len(segments) > 3:
                        continue
                    if any(s.lower() in IGNORE_SEGMENTS for s in segments):
                        continue
                    if re.search(r"\.(html?|php|aspx?|jpg|png|gif|pdf|mp3|mp4|css|js|json|xml)$", clean_path, re.IGNORECASE):
                        continue
                    if any(re.match(r"^\d+$", s) or re.match(r"^\d{4}-\d{2}", s) for s in segments):
                        continue
                    if len(segments[-1].split("-")) > 3:
                        continue

                    res_origin = f"{p_res.scheme}://{p_res.netloc}"
                    section_url = f"{res_origin}/{clean_path}"
                    label = link_text if (link_text and 2 <= len(link_text) <= 45) else urllib.parse.unquote(segments[-1])

                    if re.search(r"(?:/feed|/rss|\.xml)$", clean_path, re.IGNORECASE):
                        direct_feeds.append((section_url, label, res_origin))
                        continue

                    first_seg = segments[0].lower()
                    is_lang = bool(re.match(r"^[a-z]{2}(-[a-z]{2})?$", first_seg, re.IGNORECASE))
                    is_exp = (
                        first_seg in ("content", "category", "categories", "section", "topic")
                        or (len(segments) == 2 and (first_seg == "news" or is_lang or segments[1].lower() == "category"))
                    )
                    matched_cat = match_category_rule(f"{link_text} {segments[-1]}")
                    if is_exp or len(segments) == 1 or (len(segments) == 2 and matched_cat):
                        if section_url not in scraped_sections:
                            scraped_sections[section_url] = (section_url, label, segments, bool(is_exp or matched_cat))
            except Exception:
                pass

        if all_alternates:
            with ThreadPoolExecutor(max_workers=8) as ex:
                futs = {ex.submit(check_feed_url_with_meta, alt["url"], True, 5): (alt, bp, pr) for alt, bp, pr in all_alternates[:12]}
                for fut in as_completed(futs):
                    alt, bp, pr = futs[fut]
                    try:
                        checked = fut.result()
                        if checked:
                            alt_page = re.sub(r"/+(feed|rss|atom)(\.xml)?/?$", "", alt["url"], flags=re.IGNORECASE) or bp
                            add_verified(alt["title"] or checked["title"] or hostname, alt_page, checked["feed_url"], checked["title"], checked["categories"], None, pr)
                    except Exception:
                        pass

        if direct_feeds:
            with ThreadPoolExecutor(max_workers=8) as ex:
                futs = {ex.submit(check_feed_url_with_meta, df_url, True, 5): (df_url, df_label, df_page) for df_url, df_label, df_page in direct_feeds[:15]}
                for fut in as_completed(futs):
                    df_url, df_label, df_page = futs[fut]
                    try:
                        checked = fut.result()
                        if checked:
                            add_verified(df_label, df_page, checked["feed_url"], checked["title"], checked["categories"], None, 2)
                    except Exception:
                        pass

        if not verified_feeds:
            probe_list = [f"{origin}/feed", f"{origin}/rss", f"{origin}/rss.xml", f"{origin}/xml/rss/all.xml"]
            if pathname:
                probe_list = [
                    f"{full_url}/feed",
                    f"{full_url}/rss",
                    f"{full_url}/rss.xml",
                    f"{origin}/content/{pathname}/feed",
                    f"{origin}/category/{pathname}/feed",
                    f"{origin}/category/{pathname}/rss",
                ] + probe_list
            with ThreadPoolExecutor(max_workers=10) as ex:
                futs = {ex.submit(check_feed_url_with_meta, p_url, True, 5): p_url for p_url in probe_list}
                for fut in as_completed(futs):
                    try:
                        checked = fut.result()
                        if checked:
                            add_verified(checked["title"] or f"{hostname} (Main Feed)", origin, checked["feed_url"], checked["title"], checked["categories"], None, 2)
                    except Exception:
                        pass

        section_list = sorted(scraped_sections.values(), key=lambda x: (not x[3], len(x[2])))[:40]
        if len(verified_feeds) <= 2 and section_list:
            working_sfx = None
            sample_probes = []
            for s_url, s_label, s_segs, _ in section_list[:3]:
                sample_probes.extend([
                    ("/feed", f"{s_url}/feed", s_label, s_url),
                    ("/rss", f"{s_url}/rss", s_label, s_url),
                    ("/rss.xml", f"{s_url}/rss.xml", s_label, s_url),
                ])
                if len(s_segs) == 1:
                    sample_probes.extend([
                        ("content_feed", f"{origin}/content/{s_segs[0]}/feed", s_label, s_url),
                        ("category_feed", f"{origin}/category/{s_segs[0]}/feed", s_label, s_url),
                        ("category_rss", f"{origin}/category/{s_segs[0]}/rss", s_label, s_url),
                        ("content_cat_feed", f"{origin}/content/category/{s_segs[0]}/feed", s_label, s_url),
                    ])
            with ThreadPoolExecutor(max_workers=12) as ex:
                futs = {ex.submit(check_feed_url_with_meta, p_url, True, 4): (sfx_key, s_label, s_url) for sfx_key, p_url, s_label, s_url in sample_probes}
                for fut in as_completed(futs):
                    sfx_key, s_label, s_url = futs[fut]
                    try:
                        checked = fut.result()
                        if checked:
                            if not working_sfx:
                                working_sfx = sfx_key
                            add_verified(s_label, s_url, checked["feed_url"], checked["title"], checked["categories"], None, 3)
                    except Exception:
                        pass

            if working_sfx:
                def build_sec_feed(s_url, slug):
                    if working_sfx == "content_feed":
                        return f"{origin}/content/{slug}/feed"
                    if working_sfx == "category_feed":
                        return f"{origin}/category/{slug}/feed"
                    if working_sfx == "category_rss":
                        return f"{origin}/category/{slug}/rss"
                    if working_sfx == "content_cat_feed":
                        return f"{origin}/content/category/{slug}/feed"
                    return f"{s_url}{working_sfx}"

                cands = [(s_label, s_url, build_sec_feed(s_url, s_segs[-1])) for s_url, s_label, s_segs, _ in section_list]
                with ThreadPoolExecutor(max_workers=12) as executor:
                    futs = {executor.submit(check_feed_url_with_meta, c[2], True, 5): c for c in cands}
                    for fut in as_completed(futs):
                        s_label, s_url, _ = futs[fut]
                        try:
                            checked = fut.result()
                            if checked:
                                add_verified(s_label, s_url, checked["feed_url"], checked["title"], checked["categories"], None, 3)
                        except Exception:
                            pass

        # Fallback for portals with only 1 global feed or 0 native feeds (Setopati, Ratopati, Ekantipur, etc.)
        if len(verified_feeds) <= 1 and section_list:
            for s_url, s_label, s_segs, is_exp in section_list:
                det_cat = detect_category(name=s_label, url=s_url)
                if det_cat == "General News" and not is_exp and len(section_list) > 12:
                    continue
                prio = 1 if (pathname and last_slug in s_url.lower()) else 4
                add_verified(s_label, s_url, s_url, f"{s_label} - {hostname}", [], det_cat, prio)

    verified_feeds.sort(key=lambda x: (x["priority"], x["category"], x["name"]))

    primary_feed = None
    if pathname:
        for f in verified_feeds:
            if (
                f["priority"] == 1
                or pathname.lower() in f["page_url"].lower()
                or (last_slug and last_slug in f["feed_url"].lower())
            ):
                primary_feed = f
                break
    if not primary_feed and verified_feeds:
        for f in verified_feeds:
            if f["page_url"].rstrip("/") == origin:
                primary_feed = f
                break
        if not primary_feed:
            primary_feed = verified_feeds[0]

    categories = {}
    for item in verified_feeds:
        categories.setdefault(item["category"], []).append({
            "name": item["name"],
            "category": item["category"],
            "page_url": item["page_url"],
            "feed_url": item["feed_url"],
            "feed_title": item["feed_title"],
        })

    return {
        "target_url": full_url,
        "origin": origin,
        "primary_feed": primary_feed["feed_url"] if primary_feed else None,
        "primary_category": primary_feed["category"] if primary_feed else detect_category(url=full_url),
        "categories": categories,
        "feeds": verified_feeds,
    }


def parse_smart_json(data):
    folder_map = {}
    if isinstance(data, dict) and isinstance(data.get("folders"), list):
        for f in data["folders"]:
            if isinstance(f, dict) and "id" in f and f.get("name"):
                folder_map[f["id"]] = str(f["name"]).strip()

    arr = []
    if isinstance(data, list):
        arr = data
    elif isinstance(data, dict):
        for k in ("links", "sites", "portals", "items", "with_feed", "data", "urls"):
            if isinstance(data.get(k), list):
                arr = data[k]
                break
        if not arr:
            arr = [data]

    sites = []
    url_keys = ["url", "url_address", "website", "link", "site_url", "siteurl", "homepage", "href", "feed_url"]
    name_keys = ["name", "title", "site_name", "sitename", "label", "portal_name", "portalname", "heading"]
    cat_keys = ["category", "folder", "folder_name", "group", "section", "type", "tag"]

    for item in arr:
        if isinstance(item, str) and item.strip():
            sites.append({"name": item.strip(), "url": item.strip(), "category": ""})
            continue
        if not isinstance(item, dict):
            continue
        url = ""
        for key in url_keys:
            val = item.get(key)
            if val and isinstance(val, str) and val.strip().startswith("http"):
                url = val.strip()
                break
        if not url:
            for key, val in item.items():
                if isinstance(val, str):
                    val_strip = val.strip()
                    if val_strip.startswith(("http://", "https://", "www.")):
                        url = val_strip
                        break
        if not url:
            continue

        name = ""
        for key in name_keys:
            val = item.get(key)
            if val and isinstance(val, str) and val.strip():
                name = val.strip()
                break
        if not name:
            for key, val in item.items():
                if isinstance(val, str) and val.strip() != url:
                    name = val.strip()
                    break
        if not name:
            name = url

        category = ""
        if "folderId" in item and item["folderId"] in folder_map:
            category = folder_map[item["folderId"]]
        else:
            for key in cat_keys:
                val = item.get(key)
                if val and isinstance(val, str) and val.strip():
                    category = val.strip()
                    break

        sites.append({"name": name, "url": url, "category": category})
    return sites


# ---------------------------------------------------------------------------
# RSS Feed & Category Finder Dialog (Clean Single-Window Finder)
# ---------------------------------------------------------------------------
class FeedFinderDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(
            parent,
            title=_("RSS Feed & Category Finder"),
            size=(740, 520),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX,
        )
        self.all_discovered_feeds = []
        self.discovered_feeds = []

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        label = wx.StaticText(
            self,
            label=_("Enter Website or Category URL (e.g. https://example.com):"),
        )
        main_sizer.Add(label, 0, wx.ALL, 10)

        url_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_url = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.txt_url.Bind(wx.EVT_TEXT_ENTER, self.on_find)
        url_sizer.Add(self.txt_url, 1, wx.RIGHT, 8)

        self.btn_find = wx.Button(self, label=_("&Find All Feeds"))
        self.btn_find.Bind(wx.EVT_BUTTON, self.on_find)
        url_sizer.Add(self.btn_find, 0)

        main_sizer.Add(url_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)
        lbl_filter = wx.StaticText(self, label=_("Filter Category:"))
        filter_sizer.Add(lbl_filter, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.combo_filter_cat = wx.ComboBox(self, choices=[_("All Categories")], style=wx.CB_READONLY)
        self.combo_filter_cat.SetSelection(0)
        self.combo_filter_cat.Bind(wx.EVT_COMBOBOX, self.on_filter_cat_changed)
        filter_sizer.Add(self.combo_filter_cat, 1, wx.RIGHT, 10)

        output_label = wx.StaticText(self, label=_("Selected Feed URL:"))
        filter_sizer.Add(output_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.txt_output = wx.TextCtrl(self, style=wx.TE_READONLY)
        filter_sizer.Add(self.txt_output, 2)

        main_sizer.Add(filter_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        sub_label = wx.StaticText(self, label=_("Discovered Categories & RSS Feeds:"))
        main_sizer.Add(sub_label, 0, wx.TOP | wx.LEFT | wx.RIGHT, 10)

        self.lst_sub_feeds = wx.ListBox(self, style=wx.LB_SINGLE)
        self.lst_sub_feeds.Bind(wx.EVT_LISTBOX, self.on_sub_feed_selected)
        self.lst_sub_feeds.Bind(wx.EVT_LISTBOX_DCLICK, self.on_copy)
        main_sizer.Add(self.lst_sub_feeds, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.btn_copy = wx.Button(self, label=_("&Copy Selected Link"))
        self.btn_copy.Bind(wx.EVT_BUTTON, self.on_copy)
        self.btn_copy.Disable()
        btn_sizer.Add(self.btn_copy, 1, wx.RIGHT, 5)

        self.btn_copy_all = wx.Button(self, label=_("Copy &All in Category"))
        self.btn_copy_all.Bind(wx.EVT_BUTTON, self.on_copy_all_category)
        self.btn_copy_all.Disable()
        btn_sizer.Add(self.btn_copy_all, 1, wx.LEFT | wx.RIGHT, 5)

        self.btn_batch = wx.Button(self, label=_("&Batch Check JSON..."))
        self.btn_batch.Bind(wx.EVT_BUTTON, self.on_batch)
        btn_sizer.Add(self.btn_batch, 1, wx.LEFT | wx.RIGHT, 5)

        btn_help = wx.Button(self, label=_("&Help"))
        btn_help.Bind(wx.EVT_BUTTON, self.on_help)
        btn_sizer.Add(btn_help, 0, wx.LEFT | wx.RIGHT, 5)

        btn_close = wx.Button(self, wx.ID_CANCEL, label=_("&Close"))
        btn_sizer.Add(btn_close, 0, wx.LEFT, 5)

        main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 12)
        self.SetSizer(main_sizer)
        self.Centre()
        self.txt_url.SetFocus()

    def _populate_category_filter(self, feeds, primary_feed=None):
        self.all_discovered_feeds = list(feeds or [])
        cats = sorted({f.get("category", "General News") for f in self.all_discovered_feeds})
        self.combo_filter_cat.Clear()
        self.combo_filter_cat.Append(_("All Categories ({count})").format(count=len(self.all_discovered_feeds)))
        for c in cats:
            cnt = sum(1 for f in self.all_discovered_feeds if f.get("category", "General News") == c)
            self.combo_filter_cat.Append(f"{c} ({cnt})")
        self.combo_filter_cat.SetSelection(0)
        self._apply_category_filter(primary_feed=primary_feed)

    def _apply_category_filter(self, primary_feed=None):
        sel_idx = self.combo_filter_cat.GetSelection()
        raw_val = self.combo_filter_cat.GetValue() if sel_idx > 0 else None
        selected_cat = re.sub(r"\s*\(\d+\)$", "", raw_val) if raw_val else None

        if selected_cat:
            self.discovered_feeds = [
                f for f in self.all_discovered_feeds if f.get("category", "General News") == selected_cat
            ]
        else:
            self.discovered_feeds = list(self.all_discovered_feeds)

        self.lst_sub_feeds.Clear()
        target_idx = 0
        target_key = canonical_feed_key(primary_feed) if primary_feed else None

        for i, f in enumerate(self.discovered_feeds):
            self.lst_sub_feeds.Append(f"[{f.get('category', 'General News')}] {f['name']} — {f['feed_url']}")
            if target_key and canonical_feed_key(f["feed_url"]) == target_key:
                target_idx = i

        if self.discovered_feeds:
            self.lst_sub_feeds.SetSelection(target_idx)
            self.txt_output.SetValue(self.discovered_feeds[target_idx]["feed_url"])
            self.btn_copy.Enable()
            self.btn_copy_all.Enable()
        else:
            self.btn_copy.Disable()
            self.btn_copy_all.Disable()

    def on_filter_cat_changed(self, event):
        self._apply_category_filter()

    def on_sub_feed_selected(self, event):
        sel = self.lst_sub_feeds.GetSelection()
        if sel != wx.NOT_FOUND and sel < len(self.discovered_feeds):
            item = self.discovered_feeds[sel]
            self.txt_output.SetValue(item["feed_url"])
            self.btn_copy.Enable()
            self.btn_copy_all.Enable()

    def on_find(self, event):
        url = self.txt_url.GetValue().strip()
        if not url:
            ui.message(_("Please enter a website URL."))
            return
        self.btn_find.Disable()
        self.btn_batch.Disable()
        self.btn_copy.Disable()
        self.btn_copy_all.Disable()
        self.lst_sub_feeds.Clear()
        self.lst_sub_feeds.Append(_("Discovering website categories and RSS feeds..."))
        self.txt_output.SetValue(_("Searching for main and sub-category RSS feeds..."))
        ui.message(_("Searching for website categories and RSS feeds..."))
        threading.Thread(target=self._run_finder, args=(url,), daemon=True).start()

    def _run_finder(self, url):
        try:
            discovery = discover_site_category_feeds(url)
            if not discovery.get("feeds"):
                feed_url, _, cat, title = check_site_feed_full({"name": url, "url": url})
                if feed_url:
                    discovery["primary_feed"] = feed_url
                    discovery["primary_category"] = cat
                    discovery["feeds"] = [{
                        "name": title or url,
                        "category": cat,
                        "page_url": url,
                        "feed_url": feed_url,
                        "feed_title": title or url,
                    }]
            wx.CallAfter(self._on_finder_complete, discovery)
        except Exception as e:
            wx.CallAfter(self._on_finder_error, str(e))

    def _on_finder_complete(self, discovery):
        self.btn_find.Enable()
        self.btn_batch.Enable()
        feeds = discovery.get("feeds", [])
        primary_feed = discovery.get("primary_feed")

        if feeds or primary_feed:
            self._populate_category_filter(feeds, primary_feed=primary_feed)
            self.lst_sub_feeds.SetFocus()
            cat_count = len(discovery.get("categories", {})) or 1
            ui.message(
                _("Found {count} RSS feeds across {cats} categories. Primary feed: {url}").format(
                    count=len(feeds),
                    cats=cat_count,
                    url=primary_feed or feeds[0]["feed_url"],
                )
            )
        else:
            self.txt_output.SetValue(_("No RSS feed found for this website."))
            self.lst_sub_feeds.Clear()
            self.lst_sub_feeds.Append(_("No sub-category feeds found."))
            self.btn_copy.Disable()
            self.btn_copy_all.Disable()
            ui.message(_("No RSS feed found."))

    def _on_finder_error(self, err):
        self.btn_find.Enable()
        self.btn_batch.Enable()
        self.txt_output.SetValue(_("Error checking feed: {err}").format(err=err))
        ui.message(_("Error checking feed."))

    def on_copy(self, event):
        feed = self.txt_output.GetValue().strip()
        if feed:
            api.copyToClip(feed)
            ui.message(_("Feed URL copied to clipboard."))

    def on_copy_all_category(self, event):
        if not self.discovered_feeds:
            return
        links = "\n".join(f["feed_url"] for f in self.discovered_feeds if f.get("feed_url"))
        if links:
            api.copyToClip(links)
            ui.message(_("Copied {count} feed links to clipboard.").format(count=len(self.discovered_feeds)))

    def on_batch(self, event):
        wildcard = _("JSON files (*.json)|*.json")
        open_dlg = wx.FileDialog(self, message=_("Select input JSON file"), wildcard=wildcard, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if open_dlg.ShowModal() != wx.ID_OK:
            open_dlg.Destroy()
            return
        input_path = open_dlg.GetPath()
        open_dlg.Destroy()

        save_dlg = wx.FileDialog(self, message=_("Select where to save results"), wildcard=wildcard, style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if save_dlg.ShowModal() != wx.ID_OK:
            save_dlg.Destroy()
            return
        output_path = save_dlg.GetPath()
        save_dlg.Destroy()

        self.btn_find.Disable()
        self.btn_batch.Disable()
        self.txt_output.SetValue(_("Starting batch process with auto-categorization..."))
        ui.message(_("Starting batch check and automatic categorization..."))

        threading.Thread(target=self._run_batch, args=(input_path, output_path), daemon=True).start()

    def _run_batch(self, input_path, output_path):
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            sites = parse_smart_json(data)
            total = len(sites)
            results = [None] * total
            completed = 0

            def check_single(idx, site):
                feed, method, cat, title = check_site_feed_full(site)
                return idx, site["name"], site["url"], feed, method, cat, title

            with ThreadPoolExecutor(max_workers=12) as executor:
                futures = {executor.submit(check_single, i, site): i for i, site in enumerate(sites)}
                for fut in as_completed(futures):
                    try:
                        i, name, url, feed, method, cat, title = fut.result()
                        results[i] = {
                            "name": name,
                            "url": url,
                            "feed_url": feed,
                            "feed_title": title,
                            "category": cat,
                            "method": method,
                        }
                    except Exception:
                        pass
                    completed += 1
                    wx.CallAfter(self.txt_output.SetValue, f"Progress: {completed}/{total}")

            with_feed = [r for r in results if r and r["feed_url"]]
            without_feed = [r for r in results if r and not r["feed_url"]]

            categories = {}
            category_summary = {}
            for r in with_feed:
                cat = r.get("category") or "General News"
                categories.setdefault(cat, []).append(r)
                category_summary[cat] = category_summary.get(cat, 0) + 1

            out_data = {
                "checked_at": datetime.datetime.utcnow().isoformat() + "Z",
                "total": total,
                "with_feed_count": len(with_feed),
                "without_feed_count": len(without_feed),
                "category_summary": category_summary,
                "categories": categories,
                "with_feed": with_feed,
                "without_feed": [{"name": r["name"], "url": r["url"], "category": r.get("category", "General News")} for r in without_feed],
            }
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(out_data, f, indent=2, ensure_ascii=False)

            wx.CallAfter(self._on_batch_done, output_path, with_feed, len(categories))
        except Exception as e:
            wx.CallAfter(self._on_batch_error, str(e))

    def _on_batch_done(self, path, with_feed, cat_count):
        self.btn_find.Enable()
        self.btn_batch.Enable()
        self._populate_category_filter(with_feed)
        self.txt_output.SetValue(_("Batch complete! {count} feeds in {cats} categories saved to: {path}").format(
            count=len(with_feed), cats=cat_count, path=path
        ))
        ui.message(_("Batch feed check complete. Found {count} feeds in {cats} categories.").format(
            count=len(with_feed), cats=cat_count
        ))

    def _on_batch_error(self, err):
        self.btn_find.Enable()
        self.btn_batch.Enable()
        self.txt_output.SetValue(_("Batch process failed: {err}").format(err=err))

    def on_help(self, event):
        try:
            addon_dir = os.path.dirname(__file__)
            help_path = os.path.abspath(os.path.join(addon_dir, "..", "..", "doc", "en", "readme.html"))
            if os.path.exists(help_path):
                webbrowser.open(help_path)
            else:
                wx.MessageBox(_("Help document not found at: {path}").format(path=help_path), _("Error"), wx.ICON_ERROR)
        except Exception as e:
            wx.MessageBox(_("Could not open help: {error}").format(error=str(e)), _("Error"), wx.ICON_ERROR)


# ---------------------------------------------------------------------------
# NVDA Global Plugin Handler
# ---------------------------------------------------------------------------
class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    scriptCategory = _("RSS Feed Finder")

    def __init__(self):
        super().__init__()
        if not globalVars.appArgs.secure:
            self.tools_menu = gui.mainFrame.sysTrayIcon.toolsMenu
            self.menu_item = self.tools_menu.Append(wx.ID_ANY, _("RSS Feed & Category Finder..."))
            self.tools_menu.Bind(wx.EVT_MENU, self.on_menu_item, self.menu_item)

    def terminate(self):
        if not globalVars.appArgs.secure:
            try:
                if hasattr(self, "menu_item") and self.menu_item:
                    self.tools_menu.Remove(self.menu_item.GetId())
            except Exception:
                pass
        super().terminate()

    def on_menu_item(self, event):
        wx.CallAfter(self.show_dialog)

    def show_dialog(self):
        gui.mainFrame.prePopup()
        dlg = FeedFinderDialog(gui.mainFrame)
        dlg.ShowModal()
        dlg.Destroy()
        gui.mainFrame.postPopup()

    @scriptHandler.script(
        description=_("Opens RSS Feed & Category Finder dialog."),
        gesture="kb:NVDA+control+shift+f",
    )
    def script_openFeedFinder(self, gesture):
        if globalVars.appArgs.secure:
            return
        wx.CallAfter(self.show_dialog)
