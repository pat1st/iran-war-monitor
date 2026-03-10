import re
import os
import time
import threading

import feedparser
import trafilatura
from flask import Flask, render_template, jsonify, request
from datetime import datetime, timezone
from dateutil import parser as dateparser
from deep_translator import GoogleTranslator

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Monetisation config  (set via environment variables on Render)
# ---------------------------------------------------------------------------
MONETISATION = {
    # Google AdSense — set ADSENSE_CLIENT to your pub-XXXXXXXXXX ID
    "adsense_client":   os.environ.get("ADSENSE_CLIENT", ""),
    # AdSense ad-slot IDs (create these in your AdSense dashboard)
    "adsense_slot_banner":  os.environ.get("ADSENSE_SLOT_BANNER", ""),
    "adsense_slot_infeed":  os.environ.get("ADSENSE_SLOT_INFEED", ""),
    # VPN affiliate link — sign up at nordvpn.com/affiliates or similar
    "vpn_affiliate_url":    os.environ.get("VPN_AFFILIATE_URL", ""),
    "vpn_affiliate_label":  os.environ.get("VPN_AFFILIATE_LABEL", "Stay private — try NordVPN"),
    # Buy Me a Coffee — your username at buymeacoffee.com
    "bmac_username":        os.environ.get("BMAC_USERNAME", ""),
}

# ---------------------------------------------------------------------------
# Supported languages  (code -> display label)
# ---------------------------------------------------------------------------
LANGUAGES = {
    "en": "English",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "ar": "العربية",
    "fa": "فارسی",
    "ru": "Русский",
    "he": "עברית",
    "zh-CN": "中文",
    "tr": "Türkçe",
    "uk": "Українська",
    "pt": "Português",
}

# ---------------------------------------------------------------------------
# Per-language RSS feeds
# ---------------------------------------------------------------------------
FEEDS_BY_LANG: dict[str, list[dict]] = {
    "en": [
        # Wire services & broadcasters
        {"name": "Al Jazeera",          "url": "https://www.aljazeera.com/xml/rss/all.xml"},
        {"name": "BBC – Middle East",   "url": "http://feeds.bbci.co.uk/news/world/middle_east/rss.xml"},
        {"name": "Reuters – World",     "url": "https://feeds.reuters.com/reuters/worldNews"},
        {"name": "AP – World",          "url": "https://feeds.apnews.com/rss/apf-intlnews"},
        {"name": "NPR – World",         "url": "https://feeds.npr.org/1004/rss.xml"},
        {"name": "CNN – World",         "url": "http://rss.cnn.com/rss/edition_world.rss"},
        {"name": "France 24 EN",        "url": "https://www.france24.com/en/rss"},
        {"name": "RFI English",         "url": "https://www.rfi.fr/en/rss"},
        # Newspapers
        {"name": "The Guardian – World","url": "https://www.theguardian.com/world/rss"},
        {"name": "NY Times – World",    "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
        {"name": "Washington Post",     "url": "https://feeds.washingtonpost.com/rss/world"},
        {"name": "The Independent",     "url": "https://www.independent.co.uk/news/world/rss"},
        {"name": "The Telegraph – World","url": "https://www.telegraph.co.uk/news/world/rss.xml"},
        # Middle East specialists
        {"name": "Middle East Eye",     "url": "https://www.middleeasteye.net/rss"},
        {"name": "Iran International",  "url": "https://www.iranintl.com/en/rss"},
        {"name": "Al-Monitor",          "url": "https://www.al-monitor.com/rss"},
        {"name": "RFE/RL – Iran",       "url": "https://www.rferl.org/api/zrqotpvitot"},
        {"name": "The Economist – ME",  "url": "https://www.economist.com/middle-east-and-africa/rss.xml"},
        {"name": "Foreign Policy",      "url": "https://foreignpolicy.com/feed/"},
        # Israel-focused
        {"name": "Times of Israel",     "url": "https://www.timesofisrael.com/feed/"},
        {"name": "Jerusalem Post",      "url": "https://www.jpost.com/rss/rssfeedsfrontpage.aspx"},
        {"name": "Haaretz – English",   "url": "https://www.haaretz.com/arc/outboundfeeds/rss/?outputType=xml"},
        # Defence & security
        {"name": "Defense One",         "url": "https://www.defenseone.com/rss/all/"},
        {"name": "Breaking Defense",    "url": "https://breakingdefense.com/feed/"},
    ],
    "de": [
        # Public broadcasters
        {"name": "Tagesschau – Ausland","url": "https://www.tagesschau.de/xml/rss2_3254.xml"},
        {"name": "ARD – Nachrichten",   "url": "https://www.tagesschau.de/xml/rss2/"},
        {"name": "ZDF – Nachrichten",   "url": "https://www.zdf.de/rss/zdf/nachrichten"},
        {"name": "Deutsche Welle",      "url": "https://rss.dw.com/rdf/rss-de-all"},
        {"name": "Phoenix",             "url": "https://www.phoenix.de/service/rss/rss.xml"},
        # Newspapers & magazines
        {"name": "Spiegel – Ausland",   "url": "https://www.spiegel.de/ausland/index.rss"},
        {"name": "Zeit Online",         "url": "https://newsfeed.zeit.de/index"},
        {"name": "FAZ – Außenpolitik",  "url": "https://www.faz.net/rss/aktuell/politik/ausland/"},
        {"name": "Süddeutsche Zeitung", "url": "https://rss.sueddeutsche.de/rss/Ausland"},
        {"name": "Welt – Ausland",      "url": "https://www.welt.de/feeds/latest.rss"},
        {"name": "Focus – Ausland",     "url": "https://rss.focus.de/fol/XML/rss_folaudev2.xml"},
        {"name": "n-tv – Nachrichten",  "url": "https://www.n-tv.de/rss"},
        {"name": "Handelsblatt",        "url": "https://www.handelsblatt.com/contentexport/feed/schlagzeilen"},
        {"name": "Stern – Ausland",     "url": "https://www.stern.de/feed/standard/politik/"},
    ],
    "fr": [
        {"name": "France 24 FR", "url": "https://www.france24.com/fr/rss"},
        {"name": "RFI Français", "url": "https://www.rfi.fr/fr/rss"},
        {"name": "Le Monde",     "url": "https://www.lemonde.fr/rss/une.xml"},
    ],
    "es": [
        {"name": "BBC Mundo",             "url": "https://feeds.bbci.co.uk/mundo/rss.xml"},
        {"name": "France 24 ES",          "url": "https://www.france24.com/es/rss"},
        {"name": "El País Internacional", "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada"},
    ],
    "ar": [
        {"name": "الجزيرة",         "url": "https://www.aljazeera.net/xml/rss/all.xml"},
        {"name": "بي بي سي عربي",   "url": "https://feeds.bbci.co.uk/arabic/rss.xml"},
        {"name": "فرانس 24 عربي",   "url": "https://www.france24.com/ar/rss"},
        {"name": "سكاي نيوز عربية", "url": "https://www.skynewsarabia.com/web/rss"},
    ],
    "fa": [
        {"name": "بی‌بی‌سی فارسی",  "url": "https://feeds.bbci.co.uk/persian/rss.xml"},
        {"name": "رادیو فردا",       "url": "https://www.radiofarda.com/api/zqovveiri-u"},
        {"name": "ایران اینترنشنال", "url": "https://www.iranintl.com/rss"},
        {"name": "VOA فارسی",        "url": "https://www.voanews.com/api/z-pqekvkqikm"},
    ],
    "ru": [
        {"name": "BBC Русский", "url": "https://feeds.bbci.co.uk/russian/rss.xml"},
        {"name": "ТАСС",        "url": "https://tass.com/rss/v2.xml"},
        {"name": "Meduza",      "url": "https://meduza.io/rss/all"},
    ],
    "he": [
        {"name": "ynet",               "url": "https://www.ynet.co.il/Integration/StoryRss946.xml"},
        {"name": "Walla! חדשות",       "url": "https://rss.walla.co.il/?w=/2"},
        {"name": "Times of Israel",    "url": "https://www.timesofisrael.com/feed/"},
        {"name": "Jerusalem Post",     "url": "https://www.jpost.com/rss/rssfeedsfrontpage.aspx"},
    ],
    "zh-CN": [
        {"name": "BBC 中文",  "url": "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml"},
        {"name": "法广中文",  "url": "https://www.rfi.fr/cn/rss"},
        {"name": "法国24中文","url": "https://www.france24.com/zh-CN/rss"},
    ],
    "tr": [
        {"name": "BBC Türkçe",       "url": "https://feeds.bbci.co.uk/turkce/rss.xml"},
        {"name": "TRT Haber",        "url": "https://www.trthaber.com/sondakika.rss"},
        {"name": "Al Jazeera Türkçe","url": "https://www.aljazeera.com.tr/rss"},
    ],
    "uk": [
        {"name": "BBC Українська", "url": "https://feeds.bbci.co.uk/ukrainian/rss.xml"},
        {"name": "Укрінформ",      "url": "https://www.ukrinform.ua/rss/block-lastnews"},
        {"name": "Радіо Свобода",  "url": "https://www.radiosvoboda.org/api/zrqouveuyt"},
    ],
    "pt": [
        {"name": "BBC Brasil",    "url": "https://feeds.bbci.co.uk/portuguese/rss.xml"},
        {"name": "France 24 PT",  "url": "https://www.france24.com/pt/rss"},
        {"name": "RFI Português", "url": "https://www.rfi.fr/pt/rss"},
    ],
}

# Per-language keywords for topic filtering (native script + transliterations)
KEYWORDS_BY_LANG: dict[str, list[str]] = {
    "en": ["iran", "tehran", "khamenei", "irgc", "revolutionary guard",
           "israel iran", "us iran", "iran war", "iran strike", "iran attack",
           "iran nuclear", "iran missile", "iran drone", "iran sanction",
           "middle east war", "iran conflict", "persian gulf",
           "iran deal", "iran proxy", "hezbollah iran", "houthi iran",
           "iranian", "islamic republic", "mullahs", "ayatollah",
           "iran oil", "strait of hormuz", "iran ballistic"],
    "de": ["iran", "teheran", "chamenei", "revolutionsgarde", "irgc",
           "naher osten", "persischer golf", "atomstreit iran",
           "iran krieg", "iran angriff", "iran rakete", "iran drohne",
           "iran sanktion", "iran konflikt", "iranisch", "nahostkrieg",
           "islamische republik", "mullahs", "iran abkommen"],
    "fr": ["iran", "téhéran", "khamenei", "gardiens de la révolution",
           "moyen-orient", "golfe persique", "nucléaire iranien",
           "guerre iran", "frappe iran", "drone iran"],
    "es": ["irán", "teherán", "jamenéi", "guardia revolucionaria",
           "oriente medio", "golfo pérsico", "nuclear iraní",
           "guerra irán", "ataque irán", "misil iraní"],
    "ar": ["إيران", "طهران", "خامنئي", "الحرس الثوري", "الشرق الأوسط",
           "الخليج الفارسي", "النووي الإيراني", "حرب إيران", "ضربة إيران",
           "صواريخ إيران", "طائرات مسيّرة", "حزب الله", "الحوثيون"],
    "fa": ["ایران", "تهران", "خامنه‌ای", "سپاه پاسداران", "جنگ", "حمله",
           "خاورمیانه", "خلیج فارس", "هسته‌ای", "موشک", "پهپاد", "تحریم"],
    "ru": ["иран", "тегеран", "хаменеи", "ксир", "революционная гвардия",
           "ближний восток", "персидский залив", "ядерная программа ирана",
           "война иран", "удар по ирану", "иранские дроны"],
    "he": ["איראן", "טהרן", "חמינאי", "משמרות המהפכה", "המזרח התיכון",
           "המפרץ הפרסי", "הגרעין האיראני", "מלחמה", "תקיפה",
           "iran", "nuclear", "war"],
    "zh-CN": ["伊朗", "德黑兰", "哈梅内伊", "伊斯兰革命卫队", "中东",
              "波斯湾", "伊朗核", "战争", "袭击", "导弹", "无人机"],
    "tr": ["iran", "tahran", "hamaney", "devrim muhafızları",
           "orta doğu", "basra körfezi", "nükleer iran",
           "savaş", "saldırı", "füze", "insansız hava aracı"],
    "uk": ["іран", "тегеран", "хаменеї", "корпус вартових революції",
           "близький схід", "перська затока", "ядерна програма ірану",
           "війна", "удар", "ракета", "дрон"],
    "pt": ["irã", "irão", "teerã", "teerão", "khamenei",
           "guardas revolucionários", "oriente médio", "golfo pérsico",
           "nuclear iraniano", "guerra", "ataque", "míssil"],
}

# ---------------------------------------------------------------------------
# Article cache — one entry per language  { lang -> {articles, fetched_at} }
# ---------------------------------------------------------------------------
_cache: dict[str, dict] = {}
_lock  = threading.Lock()
CACHE_TTL = 300  # seconds

# ---------------------------------------------------------------------------
# Translation cache  { (lang, original_text) -> translated_text }
# ---------------------------------------------------------------------------
_trans_cache: dict[tuple, str] = {}
_trans_lock = threading.Lock()

BATCH_SEP   = "\n||||\n"
MAX_CHARS   = 4500


def translate_batch(texts: list[str], target_lang: str) -> list[str]:
    """Translate a list of strings efficiently using batched API calls."""
    if target_lang == "en" or not texts:
        return texts

    results = list(texts)
    to_translate: list[tuple[int, str]] = []

    with _trans_lock:
        for i, text in enumerate(texts):
            if not text:
                continue
            key = (target_lang, text)
            if key in _trans_cache:
                results[i] = _trans_cache[key]
            else:
                to_translate.append((i, text))

    if not to_translate:
        return results

    # Build chunks that fit within MAX_CHARS
    chunks: list[list[tuple[int, str]]] = []
    current_chunk: list[tuple[int, str]] = []
    current_len = 0

    for item in to_translate:
        segment_len = len(item[1]) + len(BATCH_SEP)
        if current_chunk and current_len + segment_len > MAX_CHARS:
            chunks.append(current_chunk)
            current_chunk = [item]
            current_len = segment_len
        else:
            current_chunk.append(item)
            current_len += segment_len

    if current_chunk:
        chunks.append(current_chunk)

    for chunk in chunks:
        batch_text = BATCH_SEP.join(t for _, t in chunk)
        try:
            translated = GoogleTranslator(source="auto", target=target_lang).translate(batch_text)
            parts = translated.split("||||")
            with _trans_lock:
                for (i, original), part in zip(chunk, parts):
                    clean = part.strip()
                    _trans_cache[(target_lang, original)] = clean
                    results[i] = clean
        except Exception as e:
            app.logger.warning(f"Translation failed for lang={target_lang}: {e}")
            # fallback: keep originals for this chunk

    return results


# ---------------------------------------------------------------------------
# RSS fetch + filtering
# ---------------------------------------------------------------------------
def matches_topic(title: str, summary: str, keywords: list[str]) -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in keywords)


def fetch_articles(lang: str) -> list[dict]:
    feeds    = FEEDS_BY_LANG.get(lang, FEEDS_BY_LANG["en"])
    keywords = KEYWORDS_BY_LANG.get(lang, KEYWORDS_BY_LANG["en"])
    articles = []
    for feed_meta in feeds:
        try:
            feed = feedparser.parse(feed_meta["url"])
            for entry in feed.entries:
                title   = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                link    = entry.get("link", "#")

                pub_str = entry.get("published", entry.get("updated", ""))
                try:
                    pub_dt = dateparser.parse(pub_str)
                    if pub_dt and pub_dt.tzinfo is None:
                        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                    pub_iso     = pub_dt.isoformat() if pub_dt else ""
                    pub_display = pub_dt.strftime("%d %b %Y, %H:%M UTC") if pub_dt else "Unknown"
                except Exception:
                    pub_iso, pub_display = "", "Unknown"

                if matches_topic(title, summary, keywords):
                    clean_summary = re.sub(r"<[^>]+>", "", summary).strip()[:300]
                    articles.append({
                        "title":       title,
                        "summary":     clean_summary,
                        "link":        link,
                        "source":      feed_meta["name"],
                        "pub_iso":     pub_iso,
                        "pub_display": pub_display,
                    })
        except Exception as e:
            app.logger.warning(f"Failed to fetch {feed_meta['name']}: {e}")

    articles.sort(key=lambda a: a["pub_iso"], reverse=True)
    seen, unique = set(), []
    for a in articles:
        key = a["title"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique


def get_articles(lang: str = "en", force: bool = False):
    with _lock:
        now   = time.time()
        entry = _cache.get(lang, {"articles": [], "fetched_at": 0})
        if force or (now - entry["fetched_at"]) > CACHE_TTL:
            app.logger.info(f"Fetching fresh articles for lang={lang}…")
            entry = {"articles": fetch_articles(lang), "fetched_at": now}
            _cache[lang] = entry
        return entry["articles"], datetime.fromtimestamp(entry["fetched_at"], tz=timezone.utc)


def apply_translation(articles: list[dict], lang: str) -> list[dict]:
    if lang == "en":
        return articles
    titles   = translate_batch([a["title"]   for a in articles], lang)
    summaries = translate_batch([a["summary"] for a in articles], lang)
    translated = []
    for a, t, s in zip(articles, titles, summaries):
        ta = dict(a)
        ta["title"]   = t
        ta["summary"] = s
        translated.append(ta)
    return translated


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html", languages=LANGUAGES, mon=MONETISATION)


@app.route("/privacy")
def privacy():
    return render_template("privacy.html", mon=MONETISATION)


@app.route("/refresh")
def refresh():
    lang = request.args.get("lang", "en")
    if lang not in LANGUAGES:
        lang = "en"
    articles, fetched_at = get_articles(lang, force=True)
    return jsonify({
        "status": "ok",
        "total": len(articles),
        "fetched_at": fetched_at.isoformat(),
    })


@app.route("/api/articles")
def api_articles():
    lang = request.args.get("lang", "en")
    if lang not in LANGUAGES:
        lang = "en"
    articles, fetched_at = get_articles(lang)
    # Native-language feeds need no translation; only translate if lang has no
    # dedicated feeds (falls back to English feed) and lang != "en".
    has_native = lang in FEEDS_BY_LANG
    if not has_native:
        articles = apply_translation(articles, lang)
    return jsonify({
        "fetched_at": fetched_at.isoformat(),
        "lang": lang,
        "total": len(articles),
        "articles": articles,
    })


@app.route("/api/article-content")
def article_content():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return jsonify({"error": "Could not fetch article"}), 502
        result = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            output_format="json",
            with_metadata=True,
        )
        if not result:
            return jsonify({"error": "Could not extract article content"}), 422
        import json as _json
        data = _json.loads(result)
        return jsonify({
            "title":    data.get("title", ""),
            "author":   data.get("author", ""),
            "date":     data.get("date", ""),
            "text":     data.get("text", ""),
            "url":      url,
        })
    except Exception as e:
        app.logger.warning(f"Reader error for {url}: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
