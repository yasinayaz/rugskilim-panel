"""
ai_icerik.py
Gemini Vision ile halı görselinden Etsy listing içeriği üretir.

Description yapısı:
  - DEĞİŞKEN: Açılış cümlesi (AI)
  - SABİT:    No Extra Fees
  - DEĞİŞKEN: Ürün detayları (AI renk/pattern/yıl + parser boyut/m2)
  - SABİT:    Easy Returns
  - DEĞİŞKEN: Hikaye paragrafları (AI)
  - SABİT:    Cleaned & Ready, Care, Shipping, Return, Cancellation, Wholesale, Color Note, Kapanış
"""

import base64
from copy import deepcopy
import json
import re
import os
import httpx
from pathlib import Path

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL          = "gemini-2.5-flash"   # Tier 1 Postpay → 2.5-flash geri alındı (daha kaliteli listing)
GEMINI_MODEL_FALLBACK = "gemini-1.5-flash"   # 2.5-flash 429 verirse fallback
GEMINI_URL     = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
GEMINI_RETRY_ATTEMPTS = 4
GEMINI_RETRY_BACKOFFS = (5, 12, 24)
# 429 rate-limit için ayrı, daha agresif bekleme süreleri (saniye)
# 62s: dakika kotası sıfırlanmasını garanti eder (kota dakika başında sıfırlanır)
GEMINI_RATE_LIMIT_BACKOFFS = (62, 90, 120)

# ── Global Rate Limiter ───────────────────────────────────────────────────────
# Tüm Streamlit oturumları (kullanıcılar) aynı process'i paylaşır.
# Tier 1 Postpay: gemini-2.5-flash 1000 RPM → 0.1s yeterli güvenli marj.
# Lock yine de korunuyor: eş zamanlı kullanıcılar sıraya girer, thread-safe.
import threading as _threading
_gemini_lock = _threading.Lock()
_gemini_last_call: list[float] = [0.0]  # list: mutable closure trick
_GEMINI_MIN_INTERVAL = 0.1  # saniye (Tier 1: 1000 RPM → pratikte limit yok)


# ── Sabit metin blokları ──────────────────────────────────────────────────────

_SABIT_NO_EXTRA_FEES = """\
✨ No Hidden Costs – Ever!
All customs duties and import taxes are on us. What you see is what you pay — shop freely and with full confidence.\
"""

_SABIT_EASY_RETURNS = """\
↩️ Hassle-Free Returns
Not fully satisfied? We'll make it right. Contact us within 14 days of delivery and we'll walk you through the return process — simple and stress-free.\
"""

_SABIT_ALT = """\
🧼 Cleaned & Ready to Use
Every rug is professionally cleaned before it leaves us. No odors, no hidden wear — just genuine vintage character arriving at your door.

🧽 Care Instructions
Easy to live with: light vacuuming regularly and gentle spot cleaning as needed. No specialist care required.

🚚 Shipping & Delivery:
- Dispatched within 1 business day
- Worldwide delivery in 2–4 business days
- Carefully packed to arrive in perfect condition

❌ Cancellation Policy:
Orders can be cancelled any time before dispatch — just send us a message.

🏠 Trade & Wholesale:
Interior designers and decorators are welcome. Contact us for bulk sourcing and trade pricing.

🎨 A Note on Colors:
Photos are taken in natural daylight. Colors may appear slightly different depending on your screen settings.

✨ Every piece here is one of a kind. If this one caught your eye, trust that feeling.
It's cleaned, carefully packed, and ready to find its new home.\
"""

_DEFAULT_PROMPT_RULES = {
    "title_target_min": 120,
    "title_target_max": 140,
    "title_max_length": 140,
    "tag_count": 13,
    "tag_max_length": 20,
    "title_brief": "",
    "tag_strategy": "",
    "description_brief": "",
    "description_example_template": "",
    "title_rules": """SIZE RULE: Round each ft dimension to the nearest whole number (2.8x9.9 → "3x10", 3.2x5.7 → "3x6", 3.6x9.3 → "4x9", 13.3x3.9 → "13x4"). Use ONLY the ROUNDED size in the title — never the raw decimal.
Pack in: size, style, colors, pattern, material, origin, room use, Etsy search terms.

FORMAT RULES (Etsy SEO):
- Structure: [Primary Keyword] | [Secondary Keyword + modifier] | [Occasion or Use]
- Use sentence case — capitalize only the first word and proper nouns. Do NOT title-case every word.
- Never repeat the same keyword twice in the title.
- Never include: shop name, price, "SALE", "free shipping", or promotional phrases.
- Use as much of the 140-character limit as possible — do not leave it short.

CRITICAL VARIETY RULE: Do NOT default to the same opening pattern for every rug. Look at this rug's most distinctive feature — its color, pattern, condition, size, or origin — and lead with THAT. Every title must feel written for this specific rug, not filled into a template.

Choose ONE of these five openers based on what makes THIS rug stand out. Do NOT always pick the same one:

1. Size-first (when size is the main selling point):
   "[size] ft [Origin] [Style] [Type] rug | [Color adjective] [Color] [Pattern] wool [Room] | [style/feel]"
   Example: "7x10 ft Turkish oushak area rug | aged terracotta medallion wool living room carpet | bohemian decor"

2. Color-first (when color is the most striking visual feature):
   "[Color adjective] [Color] [Pattern] Turkish rug — [size] ft [Type] | [Material] [Style] [Room] decor"
   Example: "Faded rust red medallion Turkish rug — 5x8 ft area | distressed wool bohemian living room decor"

3. Style/origin-first (when the weave, origin or style is rare/distinctive):
   "[Weave/style] Turkish [Type] [size] ft | [Color] [Pattern] wool — [Room] [Style] rug"
   Example: "Hand-knotted oushak runner 3x10 ft | muted sage green geometric wool — hallway bohemian rug"

4. Room/use-first (when the rug perfectly fits a specific space):
   "[Room] [Type] rug [size] ft | Turkish oushak [Color] [Pattern] wool | [Age/Condition] [Style]"
   Example: "Hallway runner rug 3x12 ft | Turkish oushak faded blue tribal wool | vintage distressed decor"

5. Condition/character-first (when patina, age, or distressing is a feature):
   "[Condition descriptor] [Color] Turkish [Type] rug | [size] ft [Pattern] wool | [Style] [Room] decor"
   Example: "Distressed ivory Turkish area rug | 6x9 ft floral wool | rustic bohemian living room carpet"

HARD RULES:
- The rounded size (e.g. "6x9", "3x10", "13x4") MUST always appear in the FIRST SEGMENT — before the first "|" separator — AND within the first 40 characters. No exceptions.
  ✅ "8x5 ft distressed beige Turkish area rug | faded floral wool..."
  ❌ "Distressed beige Turkish area rug | 8x5 ft faded floral wool..."  ← size is after the first "|", WRONG
- "Turkish" or "Oushak" MUST appear within the first 50 characters.
- Do NOT open with "Vintage" — let the size lead, then the origin keyword.
- Rug type keyword ("runner", "area rug", "accent rug") in the first 40 characters when it is a high-search term for this rug (e.g. "runner" for a narrow long rug is mandatory).
- Include somewhere in the title: color(s), pattern, origin (Turkish/Oushak/Anatolian), material (wool), room fit.
- Never go below {title_target_min} characters; never exceed {title_max_length}.
- BANNED WORD: Never use "Persian" anywhere in the title. These are Turkish rugs. Use "Turkish", "Oushak", "Anatolian" instead.""",
    "tag_rules": """Each tag = a strong Etsy long-tail keyword phrase (2-4 words). Total: exactly {tag_count} tags, each max {tag_max_length} chars.
Think like a buyer — what would someone search on Etsy to find THIS specific rug?

TAG FORMAT RULES (Etsy SEO):
- Every tag must be 2-4 words — NO single-word tags.
- No commas, periods, or special characters inside a tag.
- Tags must COMPLEMENT the title, not repeat it — use synonyms and variations.
- Never leave any tag empty or use "?" as a placeholder.
- Cover all buyer search angles: product type, recipient, occasion/season, style/aesthetic, long-tail variations.

REQUIRED coverage (all categories must appear):

SIZE tags — 2-3 tags, each a different word combination using the ROUNDED size:
  • [rounded size] + rug type  (e.g. "6x9 area rug")
  • [rounded size] + dominant color  (e.g. "6x9 beige rug")
  • [rounded size] + style keyword  (e.g. "6x9 vintage rug")  — optional 3rd
  Use ROUNDED size (not decimal) in all size tags. Max {tag_max_length} chars each.

COLOR tags — exactly 2 (MANDATORY — both must always appear):
  • dominant color + rug type  (e.g. "beige area rug", "red runner rug")
  • secondary color + descriptive modifier  (e.g. "muted teal rug", "faded blue wool rug")
  Use the actual colors you see in the photo — not generic placeholders.

ORIGIN/STYLE tags — exactly 2 (MANDATORY high-value keywords — both must always appear):
  • "oushak rug" or "oushak [type] rug"  ← always include this exact phrase
  • "vintage turkish rug"  ← always include this exact phrase

VISUAL/DESCRIPTIVE tags — 2-3 tags derived from what you actually SEE in this rug's photo:
  • Pattern: "medallion area rug", "tribal geometric rug", "floral wool rug"
  • Texture/condition: "distressed vintage rug", "low pile wool rug", "antique wash rug"
  Choose descriptors TRUE for THIS rug — do NOT reuse the same descriptors across different rugs.

ROOM/USE tags — 2-3 tags matched to this rug's actual size and type:
  Runner (narrow, long): "hallway runner rug", "kitchen runner rug", "entryway runner"
  Accent (small, under 4ft): "entryway accent rug", "bathroom accent rug", "bedside rug"
  Area — choose rooms that fit this rug's SIZE and home_style:
    • Large (6m²+): "living room rug", "dining room rug", "bedroom area rug"
    • Medium (3-6m²): 2-3 of: living room, bedroom, nursery, home office, reading nook
    • Small (1-3m²): 2-3 of: bedroom, entryway, kitchen, bathroom, kids room
  If home_style is Bohemian/eclectic: include "boho area rug" as one room/use tag.
  If home_style is Country/farmhouse: include "farmhouse rug decor" as one room/use tag.
  Do NOT always default to the same three rooms for every rug.

BUYER INTENT tags — 1-2 tags targeting specific buyer needs or occasions:
  Examples: "bohemian home decor", "farmhouse rug decor", "housewarming gift rug", "one of a kind rug", "eclectic home rug", "vintage rug gift", "turkish rug gift"
  Choose the one(s) that best match this rug's style and likely buyer.

HARD RULES:
- Never repeat the same word combination across tags.
- Use the ROUNDED size (not decimal) in size tags. Never use raw decimal sizes like "2.8x9.9".
- Include exactly 2 COLOR tags — one for dominant color, one for secondary color.
- Include 2-3 SIZE tags — all using the rounded size.
- Include 2-3 ROOM/USE tags — matched to this rug's actual size and type.
- Every tag must reflect what you actually observe for THIS rug.""",
    "opening_rules": """ONE punchy sentence that hooks the reader. This sentence is critical for Google indexing — it must contain the primary keyword naturally.
CRITICAL: This sentence must describe what you actually see in THIS rug's photo — a specific color, pattern detail, texture, or wear characteristic unique to this piece. Do NOT write a sentence that could apply to any rug.
Include: primary keyword (e.g. "vintage Turkish runner rug"), ROUNDED size, and one concrete visual observation from the photo.
Do NOT use raw decimal ft sizes like 3.6x9.2 in the opening sentence. Use rounded sizes like 4x9 ft in prose.
The first 160 characters of the description (opening sentence) should answer: what is it, what material, what size.
Example: "This 3x10 ft vintage Turkish runner rug stops you — its deep rust medallions fading into worn ivory give it the kind of patina that takes decades, not months." """,
    "story_rules": """Write 3–4 short paragraphs. Each paragraph max 2-3 sentences. Do NOT use bullet points here — flowing prose only.
- Para 1: Deepen the rug's visual identity from the photo — its actual colors, pattern density, fading or wear. Make the reader picture THIS exact rug.
- Para 2: Size/fit — what spaces it suits, how it anchors a room. Use the rounded ft size (e.g. "4x9 ft", "3x10 runner"). Do NOT use raw decimal sizes like 3.6x9.2 ft.
- Para 3: Material quality — handwoven wool, tactile warmth, durability. What makes it honest and lasting.
- Para 4 (optional): Style versatility + room suggestions + decoration style fit (Bohemian, farmhouse, Scandinavian, etc.) Tone should match the store's voice.
Close the story section with a call-to-action feel: "Questions? Message us before ordering." (adapt to the store's tone).
Use \\n between paragraphs. Keep it conversational, human, and warm.
SEO keywords to weave in naturally: the rounded size, dominant color + rug type, "vintage rug", "handmade", "wool", "Turkish", "antique area rug".
These same keywords appear in the tags — using them in the description too boosts Etsy SEO and Google indexing.""",
}

_DEFAULT_STATIC_TEXTS = {
    "no_extra_fees": _SABIT_NO_EXTRA_FEES,
    "easy_returns": _SABIT_EASY_RETURNS,
    "story_size_template": "",
    "footer": _SABIT_ALT,
}


def _description_framework_olustur(static_texts: dict) -> str:
    blocks = ["{opening}"]
    if str((static_texts or {}).get("no_extra_fees", "") or "").strip():
        blocks.append("{no_extra_fees_block}")
    blocks.append("{details_block}")
    if str((static_texts or {}).get("easy_returns", "") or "").strip():
        blocks.append("{easy_returns_block}")
    blocks.append("{hikaye}")
    if str((static_texts or {}).get("footer", "") or "").strip():
        blocks.append("{footer_block}")
    return "\n\n".join(blocks)


def _dinamik_placeholder_var_mi(text: str) -> bool:
    return bool(re.search(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", str(text or "")))


def _ornek_desci_dinamik_sablona_cevir(text: str) -> str:
    raw = str(text or "").strip()
    if not raw or _dinamik_placeholder_var_mi(raw):
        return raw

    satirlar = [s.rstrip() for s in raw.replace("\r\n", "\n").split("\n")]
    basliklar = ["Rug Details", "Shipping", "Care Instructions", "Returns & Support", "Discover More"]
    bolumler: dict[str, list[str]] = {}
    aktif = "__intro__"
    bolumler[aktif] = []
    for satir in satirlar:
        temiz = satir.strip()
        if temiz in basliklar:
            aktif = temiz
            bolumler.setdefault(aktif, [])
            continue
        bolumler.setdefault(aktif, []).append(satir)

    store_line = ""
    for satir in satirlar:
        temiz = satir.strip()
        if ".etsy.com" in temiz.lower():
            store_line = temiz
            break

    details_lines = [
        "✤ Authentic Vintage Turkish {tip} Rug",
        "✤ Handmade & Hand-Knotted",
        "✤ Origin: {koken}",
        "✤ Pattern: {pattern}",
        "✤ Color Palette: {renk_scheme}",
        "✤ Material: 50% Wool - 50% Cotton",
        "{pile_bullet}",
        "✤ Professionally Cleaned",
        "✤ Size: {rounded_ft_label}",
        "✤ Dimensions: {boyut_cm} cm",
        "✤ SKU: {urun_id}",
    ]

    parcalar = [
        "{opening}",
        "{hikaye}",
        "Rug Details",
        "\n".join([s for s in details_lines if s]),
    ]

    for baslik in ["Shipping", "Care Instructions", "Returns & Support", "Discover More"]:
        icerik = "\n".join([s for s in bolumler.get(baslik, []) if str(s).strip()])
        if icerik:
            parcalar.extend([baslik, icerik])

    tum_metin = "\n".join([p for p in parcalar if isinstance(p, str)])
    if store_line and store_line not in tum_metin:
        parcalar.append(store_line)

    return "\n\n".join([p.strip() for p in parcalar if str(p).strip()])

TEMPLATE_PLACEHOLDERS = {
    "boyut_ft": "Ham ft olcusu. Ornek: 2.8x9.9",
    "rounded_ft": "Yuvarlanmis ft olcusu. Ornek: 3x10",
    "rounded_ft_label": "Yuvarlanmis ft etiketi. Ornek: 3x10 ft",
    "boyut_cm": "CM olcusu. Ornek: 85x301",
    "metrekare": "m² degeri. Ornek: 2.56",
    "sqft": "ft² degeri. Ornek: 27.56",
    "tip": "Etsy type. Ornek: Runner",
    "tip_lower": "Kucuk harf type. Ornek: runner",
    "renk1": "Birincil Etsy rengi",
    "renk2": "Ikincil Etsy rengi",
    "renk_scheme": "Aciklama icin gorsel renk ifadesi",
    "pattern": "Pattern alani. Ornek: Floral",
    "tahmini_yil": "Tahmini donem. Ornek: Mid-Century",
    "stil": "Stil alani",
    "koken": "Koken alani",
    "home_style": "Home style alani",
    "shop_section": "Shop section alani",
    "ana_resim_tag": "SEO dosya etiketi",
    "baslik": "AI tarafindan uretilen baslik",
    "urun_id": "Urun kodu",
    "opening": "AI tarafindan uretilen acilis cumlesi",
    "hikaye": "AI tarafindan uretilen hikaye metni",
    "details_block": "Hazir product details blogu",
    "story_size_paragraph": "Dinamik olcu/kullanim paragrafi",
    "no_extra_fees_block": "No extra fees blogu",
    "easy_returns_block": "Easy returns blogu",
    "footer_block": "Footer / kapanis blogu",
}

ETSY_RENKLERI = [
    "Beige", "Black", "Blue", "Bronze", "Brown", "Clear", "Copper", "Gold",
    "Gray", "Green", "Orange", "Pink", "Purple", "Rainbow", "Red",
    "Rose gold", "Silver", "White", "Yellow",
]

# Canonical Etsy Pattern dropdown list shared by every store.
# AI must always save exactly one of these values for pattern_etsy.
ETSY_PATTERNLERI = [
    "Abstract", "Animal print", "Bordered", "Camouflage", "Check", "Floral",
    "Geometric", "Ikat", "Moroccan", "Ombré", "Oriental", "Paisley",
    "Patchwork", "Persian", "Plants & trees", "Polka dot", "Solid",
    "Southwestern", "Striped",
]

ETSY_HOME_STYLE = [
    "Bohemian & eclectic", "Coastal & tropical", "Contemporary",
    "Country & farmhouse", "Industrial & utility", "Rustic & primitive",
    "Scandinavian",
]

# Canonical Etsy type dropdown list shared by every store.
# AI must always save exactly one of these values for tip.
ETSY_TIPLERI = ["Accent", "Area", "Runner"]

# Canonical Etsy shop section dropdown list shared by every store.
# AI must always save exactly one of these values for shop_section.
ETSY_SHOP_SECTIONS = [
    "Oversized Rugs", "Large Rugs", "Medium Rugs", "Small Rugs", "Runner Rugs",
    "Hemp Rug Kilim", "Kilim Rugs", "Mini Rugs - Doormats", "Gifts",
]


# ── Yardımcı fonksiyonlar ─────────────────────────────────────────────────────

def _cm_to_feet_inches(cm: float) -> str:
    """85 → "2' 9\""""
    total_in = cm / 2.54
    ft = int(total_in // 12)
    inch = round(total_in % 12)
    if inch == 12:
        ft += 1
        inch = 0
    return f"{ft}' {inch}\""


def template_config_normallestir(template_config: dict = None,
                                 template_id: str = "default_v1",
                                 template_name: str = "Default (Standart)") -> dict:
    raw = deepcopy(template_config or {})
    prompt_rules = deepcopy(_DEFAULT_PROMPT_RULES)
    prompt_rules.update(raw.get("prompt_rules") or {})

    static_texts = deepcopy(_DEFAULT_STATIC_TEXTS)
    if "sabit_no_extra_fees" in raw:
        static_texts["no_extra_fees"] = raw.get("sabit_no_extra_fees") or ""
    if "sabit_easy_returns" in raw:
        static_texts["easy_returns"] = raw.get("sabit_easy_returns") or ""
    if "sabit_alt" in raw:
        static_texts["footer"] = raw.get("sabit_alt") or ""
    static_texts.update(raw.get("static_texts") or {})

    def _to_int(value, default):
        try:
            return int(value)
        except Exception:
            return default

    prompt_rules["tag_count"] = max(1, min(13, _to_int(prompt_rules.get("tag_count"), 13)))
    prompt_rules["tag_max_length"] = max(1, min(20, _to_int(prompt_rules.get("tag_max_length"), 20)))
    prompt_rules["title_max_length"] = max(10, min(140, _to_int(prompt_rules.get("title_max_length"), 140)))
    prompt_rules["title_target_min"] = max(10, min(prompt_rules["title_max_length"], _to_int(prompt_rules.get("title_target_min"), 120)))
    prompt_rules["title_target_max"] = max(prompt_rules["title_target_min"], min(prompt_rules["title_max_length"], _to_int(prompt_rules.get("title_target_max"), 140)))
    for _key in ["title_brief", "tag_strategy", "description_brief", "description_example_template",
                 "title_rules", "tag_rules", "opening_rules", "story_rules"]:
        prompt_rules[_key] = str(prompt_rules.get(_key, "") or "")
    prompt_rules["description_example_template"] = _ornek_desci_dinamik_sablona_cevir(prompt_rules["description_example_template"])
    if not prompt_rules["description_example_template"].strip():
        prompt_rules["description_example_template"] = _description_framework_olustur(static_texts)

    return {
        "template_id": raw.get("template_id", template_id),
        "template_name": raw.get("template_name", template_name),
        "prompt_extra_instructions": raw.get("prompt_extra_instructions", ""),
        "prompt_rules": prompt_rules,
        "static_texts": static_texts,
    }


def _rounded_ft_etiketi(boyut_ft: str) -> str:
    match = re.search(r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)", str(boyut_ft))
    if not match:
        return str(boyut_ft or "").replace(" ft", "").strip()
    w = max(1, round(float(match.group(1))))
    h = max(1, round(float(match.group(2))))
    return f"{w}x{h}"


def _boyut_ft_parse(boyut_ft: str) -> tuple[float | None, float | None]:
    match = re.search(r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)", str(boyut_ft or ""))
    if not match:
        return None, None
    try:
        return float(match.group(1)), float(match.group(2))
    except Exception:
        return None, None


def _enum_normalize(value: str, allowed: list[str], synonym_map: dict[str, str] | None = None) -> str:
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    if not raw:
        return ""
    lowered = raw.casefold()
    direct = {item.casefold(): item for item in allowed}
    if lowered in direct:
        return direct[lowered]
    for item in allowed:
        if item.casefold() in lowered or lowered in item.casefold():
            return item
    if synonym_map:
        for key, target in synonym_map.items():
            if key in lowered and target in allowed:
                return target
    return ""


def _etsy_renk_normalize(value: str) -> str:
    return _enum_normalize(value, ETSY_RENKLERI, {
        "beige": "Beige",
        "cream": "Beige",
        "ivory": "Beige",
        "sand": "Beige",
        "taupe": "Brown",
        "tan": "Brown",
        "brown": "Brown",
        "black": "Black",
        "charcoal": "Gray",
        "gray": "Gray",
        "grey": "Gray",
        "silver": "Silver",
        "white": "White",
        "off white": "White",
        "blue": "Blue",
        "navy": "Blue",
        "teal": "Blue",
        "green": "Green",
        "sage": "Green",
        "olive": "Green",
        "red": "Red",
        "burgundy": "Red",
        "crimson": "Red",
        "wine": "Red",
        "dark red": "Red",
        "rust red": "Red",
        "rust": "Red",        # görsel teste göre; AI prompt'ta ayrıca açıklanıyor
        "terracotta": "Orange",  # terracotta daha çok orange-dominant
        "orange": "Orange",
        "yellow": "Yellow",
        "mustard": "Yellow",
        "amber": "Yellow",
        "saffron": "Yellow",
        "gold": "Gold",
        "pink": "Pink",
        "rose": "Pink",
        "purple": "Purple",
        "lilac": "Purple",
        "copper": "Copper",
        "bronze": "Bronze",
        "rainbow": "Rainbow",
        "clear": "Clear",
    })


def _pattern_etsy_normalize(value: str) -> str:
    return _enum_normalize(value, ETSY_PATTERNLERI, {
        "medallion": "Oriental",
        "traditional": "Oriental",
        "classic": "Oriental",
        "vintage": "Oriental",
        "tribal": "Southwestern",
        "kilim": "Geometric",
        "flatweave": "Geometric",
        "flat weave": "Geometric",
        "plain": "Solid",
        "minimal": "Solid",
        "botanical": "Plants & trees",
        "tree": "Plants & trees",
        "plant": "Plants & trees",
    })


def _tip_normalize(value: str) -> str:
    return _enum_normalize(value, ETSY_TIPLERI, {
        "runner rug": "Runner",
        "runner": "Runner",
        "hallway runner": "Runner",
        "area rug": "Area",
        "area": "Area",
        "accent rug": "Accent",
        "small rug": "Accent",
        "entry rug": "Accent",
    })


def _home_style_normalize(value: str) -> str:
    return _enum_normalize(value, ETSY_HOME_STYLE, {
        "bohemian": "Bohemian & eclectic",
        "eclectic": "Bohemian & eclectic",
        "rustic": "Rustic & primitive",
        "primitive": "Rustic & primitive",
        "farmhouse": "Country & farmhouse",
        "country": "Country & farmhouse",
        "industrial": "Industrial & utility",
        "utility": "Industrial & utility",
        "scandinavian": "Scandinavian",
        "coastal": "Coastal & tropical",
        "tropical": "Coastal & tropical",
        "contemporary": "Contemporary",
        "modern": "Contemporary",
        "traditional": "Bohemian & eclectic",
    })


def _shop_section_normalize(value: str) -> str:
    return _enum_normalize(value, ETSY_SHOP_SECTIONS, {
        "runner": "Runner Rugs",
        "runner rug": "Runner Rugs",
        "small rug": "Small Rugs",
        "medium rug": "Medium Rugs",
        "large rug": "Large Rugs",
        "oversized rug": "Oversized Rugs",
        "doormat": "Mini Rugs - Doormats",
        "mini rug": "Mini Rugs - Doormats",
        "kilim": "Kilim Rugs",
        "hemp kilim": "Hemp Rug Kilim",
        "gift": "Gifts",
    })


def _pattern_etsy_tahmin(pattern_raw: str, style_raw: str = "", title_raw: str = "") -> str:
    # Pattern fallback should stay conservative. We prefer the model's direct
    # visual classification and only infer when the freeform pattern text is
    # strongly indicative.
    kaynak = str(pattern_raw or "").casefold()
    if not kaynak:
        return ""
    checks = [
        (["patchwork"], "Patchwork"),
        (["striped", "stripe"], "Striped"),
        (["check", "checked", "checker"], "Check"),
        (["polka"], "Polka dot"),
        (["animal"], "Animal print"),
        (["camouflage", "camo"], "Camouflage"),
        (["ombre", "ombré"], "Ombré"),
        (["plant", "tree", "botanical"], "Plants & trees"),
        (["paisley"], "Paisley"),
        (["ikat"], "Ikat"),
        (["moroccan", "beni"], "Moroccan"),
        (["southwestern", "south western", "aztec", "navajo"], "Southwestern"),
        (["persian"], "Persian"),
        (["geometric"], "Geometric"),
        (["floral", "flower", "rose"], "Floral"),
        (["medallion", "oriental", "traditional"], "Oriental"),
        (["solid", "plain", "minimal"], "Solid"),
        (["abstract"], "Abstract"),
        (["border", "bordered"], "Bordered"),
    ]
    for keys, target in checks:
        if any(key in kaynak for key in keys):
            return target
    return ""


def _pattern_etsy_karar_ver(mevcut: str, pattern_raw: str, style_raw: str = "", title_raw: str = "") -> str:
    mevcut_norm = _enum_normalize(mevcut, ETSY_PATTERNLERI)
    inferred = _pattern_etsy_tahmin(pattern_raw, style_raw, title_raw)

    # "Oriental" çok genel kalıyorsa, freeform pattern alanından daha spesifik
    # bir eşleşmeyi tercih et. Title/stil sinyallerini burada özellikle
    # kullanmıyoruz; bunlar tüm ürünlerde aynılaşmaya yol açabiliyor.
    if mevcut_norm == "Oriental" and inferred and inferred != "Oriental":
        return inferred
    if mevcut_norm:
        return mevcut_norm
    return inferred


def _renkleri_renk_schemeden_tamamla(renk1: str, renk2: str, renk_scheme: str) -> tuple[str, str]:
    bulunan: list[str] = []
    for parca in [p.strip() for p in re.split(r"[,\n/|;+]", str(renk_scheme or "")) if p.strip()]:
        renk = _etsy_renk_normalize(parca)
        if renk and renk not in bulunan:
            bulunan.append(renk)
    if not renk1 and bulunan:
        renk1 = bulunan[0]
    if not renk2:
        for renk in bulunan:
            if renk != renk1:
                renk2 = renk
                break
    return renk1, renk2


def _home_style_tahmin(style_raw: str, pattern_raw: str = "", title_raw: str = "") -> str:
    kaynak = " ".join([str(style_raw or ""), str(pattern_raw or ""), str(title_raw or "")]).casefold()
    if any(key in kaynak for key in ["scandinavian", "nordic", "minimal"]):
        return "Scandinavian"
    if any(key in kaynak for key in ["industrial", "utility", "loft"]):
        return "Industrial & utility"
    if any(key in kaynak for key in ["coastal", "tropical", "beach"]):
        return "Coastal & tropical"
    if any(key in kaynak for key in ["country", "farmhouse"]):
        return "Country & farmhouse"
    if any(key in kaynak for key in ["rustic", "primitive", "tribal", "southwestern"]):
        return "Rustic & primitive"
    if any(key in kaynak for key in ["modern", "contemporary", "abstract"]):
        return "Contemporary"
    return "Bohemian & eclectic"


def _tip_tahmin(boyut_ft: str) -> str:
    en, boy = _boyut_ft_parse(boyut_ft)
    if not en or not boy:
        return "Area"
    kisa, uzun = sorted([en, boy])
    if uzun >= kisa * 2.5 and kisa <= 4:
        return "Runner"
    if kisa < 4:
        return "Accent"
    return "Area"


def _shop_section_tahmin(boyut_ft: str, metrekare: float | None, tip: str, pattern_etsy: str, stil: str = "") -> str:
    pattern_kaynak = " ".join([str(pattern_etsy or ""), str(stil or "")]).casefold()
    if "hemp" in pattern_kaynak and "kilim" in pattern_kaynak:
        return "Hemp Rug Kilim"
    if "kilim" in pattern_kaynak:
        return "Kilim Rugs"
    if tip == "Runner":
        return "Runner Rugs"
    en, boy = _boyut_ft_parse(boyut_ft)
    kisa = min([v for v in [en, boy] if v is not None], default=None)
    alan = float(metrekare or 0)
    if alan >= 9 or (kisa is not None and kisa >= 9):
        return "Oversized Rugs"
    if 6 <= alan < 9:
        return "Large Rugs"
    if 3 <= alan < 6:
        return "Medium Rugs"
    if 1 <= alan < 3:
        return "Small Rugs"
    if 0 < alan < 1:
        return "Mini Rugs - Doormats"
    return "Gifts"


def _json_yanitini_coz(icerik: str) -> dict:
    temiz = re.sub(r"```json\s*|\s*```", "", str(icerik or "")).strip()
    adaylar = [temiz]
    ilk = temiz.find("{")
    son = temiz.rfind("}")
    if ilk != -1 and son != -1 and son > ilk:
        adaylar.append(temiz[ilk:son + 1].strip())
    for aday in adaylar:
        if not aday:
            continue
        try:
            return json.loads(aday)
        except json.JSONDecodeError:
            continue
    return json.loads(temiz)


def _etsy_alanlarini_tamamla(ai: dict, boyut_ft: str, metrekare: float | None) -> dict:
    norm = dict(ai or {})
    if str(norm.get("renk1", "")).strip():
        norm["renk1"] = _etsy_renk_normalize(norm.get("renk1", ""))
    if str(norm.get("renk2", "")).strip():
        norm["renk2"] = _etsy_renk_normalize(norm.get("renk2", ""))
    if str(norm.get("pattern_etsy", "")).strip():
        norm["pattern_etsy"] = _pattern_etsy_normalize(norm.get("pattern_etsy", ""))
    if str(norm.get("tip", "")).strip():
        norm["tip"] = _tip_normalize(norm.get("tip", ""))
    if str(norm.get("home_style", "")).strip():
        norm["home_style"] = _home_style_normalize(norm.get("home_style", ""))
    if str(norm.get("shop_section", "")).strip():
        norm["shop_section"] = _shop_section_normalize(norm.get("shop_section", ""))
    return norm


def _oda_taglari(tip: str, shop_section: str, home_style: str = "") -> list[str]:
    style_lower = (home_style or "").lower()
    if shop_section == "Mini Rugs - Doormats":
        return ["entryway rug", "bathroom rug", "door mat rug"]
    if tip == "Runner":
        return ["hallway runner rug", "kitchen runner rug", "entryway runner rug"]
    if tip == "Accent":
        return ["entryway accent rug", "bedroom accent rug", "bathroom accent rug"]
    # Area rugs — style-aware room selection
    if "bohemian" in style_lower or "eclectic" in style_lower:
        return ["boho area rug", "living room rug", "bedroom area rug"]
    if "farmhouse" in style_lower or "country" in style_lower:
        return ["farmhouse rug decor", "living room rug", "dining room rug"]
    if shop_section == "Large Rugs" or shop_section == "Oversized Rugs":
        return ["living room rug", "dining room rug", "bedroom area rug"]
    if shop_section == "Small Rugs":
        return ["bedroom accent rug", "entryway area rug", "kitchen small rug"]
    return ["living room rug", "bedroom area rug", "dining room rug"]


def _fallback_taglari_olustur(rounded_ft: str, tip: str, renk1: str, renk2: str, pattern_etsy: str,
                              koken: str, stil: str, shop_section: str, home_style: str = "") -> list[str]:
    tip_lower = tip.lower()
    size_tags = [
        f"{rounded_ft} {tip_lower} rug",
        f"{rounded_ft} {str(renk1 or 'vintage').lower()} rug",
        f"{rounded_ft} {str(pattern_etsy or 'vintage').lower()} rug",
    ]
    color_tags = []
    if renk1:
        color_tags.append(f"{renk1.lower()} {tip_lower} rug")
    if renk2:
        color_tags.append(f"{renk2.lower()} {tip_lower} rug")
    style_tags = [
        "oushak rug",
        "vintage turkish rug",
        "handmade wool rug",
        f"{str(pattern_etsy or 'vintage').lower()} wool rug",
        f"vintage {tip_lower} rug",
    ]
    oda_tags = _oda_taglari(tip, shop_section, home_style)
    tags = size_tags + color_tags + style_tags + oda_tags
    temiz = []
    for tag in tags:
        t = re.sub(r"\s+", " ", str(tag or "")).strip()
        if t and t not in temiz:
            temiz.append(t)
    return temiz[:13]


def _fallback_baslik_olustur(rounded_ft: str, tip: str, renk1: str, renk2: str, pattern_etsy: str,
                             koken: str, stil: str, shop_section: str) -> str:
    renk_parca = " & ".join([r for r in [renk1, renk2] if r]).strip()
    if renk_parca:
        renk_parca = f"Faded {renk_parca}"
    else:
        renk_parca = "Vintage Wool"
    tip_room = {
        "Runner": "Hallway Carpet",
        "Accent": "Entryway Accent Rug",
        "Area": "Living Room Carpet",
    }.get(tip, "Home Decor Rug")
    base = (
        f"{rounded_ft} ft Vintage {str(koken or 'Turkish')} {str(stil or 'Oushak')} {tip} Rug | "
        f"{renk_parca} {str(pattern_etsy or 'Patterned')} Wool {tip_room}"
    )
    if len(base) < 120:
        extra = f" | Handmade One of a Kind {shop_section or 'Home Decor'}"
        base = f"{base}{extra}"
    return base


def _baslik_kisalt(baslik: str, max_uzunluk: int) -> str:
    baslik = re.sub(r"\s+", " ", str(baslik or "")).strip()
    if len(baslik) <= max_uzunluk:
        return baslik
    kisaltilmis = baslik[:max_uzunluk].rstrip(" ,;:-|/")
    if " " in kisaltilmis and len(baslik) > max_uzunluk:
        son_bosluk = kisaltilmis.rfind(" ")
        if son_bosluk >= max_uzunluk - 20:
            kisaltilmis = kisaltilmis[:son_bosluk].rstrip(" ,;:-|/")
    return kisaltilmis or baslik[:max_uzunluk].rstrip()


def _taglari_normallestir(taglar, tag_sayisi: int, tag_max_uzunluk: int, pad_missing: bool = True) -> list:
    sonuc = []
    for tag in taglar or []:
        temiz = re.sub(r"\s+", " ", str(tag or "")).strip().strip('"')
        if temiz:
            sonuc.append(temiz[:tag_max_uzunluk].rstrip(" ,;:-|/"))
    sonuc = sonuc[:tag_sayisi]
    if pad_missing and len(sonuc) < tag_sayisi:
        sonuc.extend([""] * (tag_sayisi - len(sonuc)))
    return sonuc


def _ai_sonuc_normallestir(ai: dict, template_config: dict = None) -> dict:
    tc = template_config_normallestir(template_config)
    pr = tc["prompt_rules"]
    norm = dict(ai or {})
    norm["baslik"] = _baslik_kisalt(norm.get("baslik", ""), pr["title_max_length"])
    norm["taglar"] = _taglari_normallestir(
        norm.get("taglar", []),
        pr["tag_count"],
        pr["tag_max_length"],
        pad_missing=False,
    )
    for alan in [
        "opening", "hikaye", "renk_scheme", "pattern", "ana_resim_tag",
        "renk1", "renk2", "pattern_etsy", "tip", "home_style", "shop_section",
        "tahmini_yil", "stil", "koken",
    ]:
        norm[alan] = str(norm.get(alan, "") or "").strip()
    return norm


def _varsayilan_tip(boyut_ft: str) -> str:
    return _tip_tahmin(boyut_ft)


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _render_template_text(text: str, context: dict) -> str:
    if not text:
        return ""
    try:
        return str(text).format_map(_SafeDict(context)).strip()
    except Exception:
        return str(text).strip()


def _kural_birlesik(base_text: str, extra_label: str, extra_text: str) -> str:
    base = str(base_text or "").strip()
    extra = str(extra_text or "").strip()
    if not extra:
        return base
    return f"{base}\n\n{extra_label}\n{extra}".strip()


def _hikaye_paragraflari(hikaye: str) -> list:
    return [p.strip() for p in re.split(r"\n+", str(hikaye or "").strip().strip('"')) if p.strip()]


def _duzyazi_boyut_normallestir(text: str, boyut_ft: str) -> str:
    metin = str(text or "").strip()
    raw_size = str(boyut_ft or "").replace(" ft", "").strip()
    rounded_size = _rounded_ft_etiketi(boyut_ft)
    if not metin or not raw_size or not rounded_size or raw_size == rounded_size:
        return metin
    patterns = [
        rf"\b{re.escape(raw_size)}\s*ft\b",
        rf"\b{re.escape(raw_size)}\b",
    ]
    for pattern in patterns:
        metin = re.sub(pattern, f"{rounded_size} ft", metin, flags=re.IGNORECASE)
    metin = re.sub(rf"\b{re.escape(rounded_size)}\s*ft\s*ft\b", f"{rounded_size} ft", metin, flags=re.IGNORECASE)
    return metin


def _template_context(ai: dict, urun_id: str, boyut_ft: str, boyut_cm: str, metrekare: float) -> dict:
    rounded_ft = _rounded_ft_etiketi(boyut_ft)
    sqft = round(metrekare * 10.764, 2) if metrekare else ""
    tip = str(ai.get("tip") or "Rug").strip() or "Rug"
    pile_cm = str(ai.get("pile_cm") or "").strip()
    return {
        "urun_id": urun_id or "",
        "boyut_ft": boyut_ft or "",
        "rounded_ft": rounded_ft,
        "rounded_ft_label": f"{rounded_ft} ft" if rounded_ft else "",
        "boyut_cm": boyut_cm or "",
        "metrekare": metrekare if metrekare is not None else "",
        "sqft": sqft,
        "tip": tip,
        "tip_lower": tip.lower(),
        "renk1": ai.get("renk1", ""),
        "renk2": ai.get("renk2", ""),
        "renk_scheme": ai.get("renk_scheme", ""),
        "pattern": ai.get("pattern", ""),
        "tahmini_yil": ai.get("tahmini_yil", ""),
        "stil": ai.get("stil", ""),
        "koken": ai.get("koken", ""),
        "home_style": ai.get("home_style", ""),
        "shop_section": ai.get("shop_section", ""),
        "ana_resim_tag": ai.get("ana_resim_tag", ""),
        "baslik": ai.get("baslik", ""),
        "pile_bullet": f"✤ Low Pile: {pile_cm} cm" if pile_cm else "",
    }


def _boyut_satirlari(boyut_ft: str, boyut_cm: str, metrekare: float,
                     genislik_cm=None, uzunluk_cm=None) -> str:
    """Product Details içindeki boyut satırlarını oluşturur."""
    sqft = round(metrekare * 10.764, 2) if metrekare else "?"
    sqm  = metrekare or "?"

    boyut_str = f"Size: {boyut_ft} ft - {boyut_cm} cm"
    return f"{boyut_str}\nTotal SQFT: {sqft}\nTotal SQM: {sqm}"


def description_olustur(ai: dict, boyut_ft: str, boyut_cm: str, metrekare: float,
                         genislik_cm=None, uzunluk_cm=None,
                         template_config: dict = None,
                         urun_id: str = "") -> str:
    """
    AI alanları + sabit blokları birleştirerek tam Etsy description döndürür.
    template_config verilirse o mağazanın sabit metin bloklarını kullanır.
    """
    tc = template_config_normallestir(template_config)
    static_texts = tc["static_texts"]
    ctx = _template_context(ai, urun_id, boyut_ft, boyut_cm, metrekare)
    no_extra_fees = _render_template_text(static_texts.get("no_extra_fees", ""), ctx)
    easy_returns = _render_template_text(static_texts.get("easy_returns", ""), ctx)
    sabit_alt = _render_template_text(static_texts.get("footer", ""), ctx)

    boyut_satirlari = _boyut_satirlari(boyut_ft, boyut_cm, metrekare, genislik_cm, uzunluk_cm)

    pile_satir = ""
    if ai.get("pile_cm"):
        pile_satir = f"\nPile: {ai['pile_cm']} cm"

    detaylar = (
        f"📋 Product Details:\n"
        f"Color Scheme: {ai.get('renk_scheme', '')}\n"
        f"{boyut_satirlari}\n"
        f"Made in: {ai.get('tahmini_yil', 'Vintage')}\n"
        f"Pattern: {ai.get('pattern', '')}"
        f"{pile_satir}"
    )

    opening = ai.get("opening", "").strip().strip('"')
    opening = _duzyazi_boyut_normallestir(opening, boyut_ft)
    hikaye_paragraflari = _hikaye_paragraflari(ai.get("hikaye", ""))
    hikaye_paragraflari = [_duzyazi_boyut_normallestir(paragraf, boyut_ft) for paragraf in hikaye_paragraflari]
    size_story_template = _render_template_text(static_texts.get("story_size_template", ""), ctx)
    if size_story_template:
        if len(hikaye_paragraflari) >= 2:
            hikaye_paragraflari[1] = size_story_template
        else:
            hikaye_paragraflari.append(size_story_template)
    hikaye = "\n\n".join(hikaye_paragraflari)

    full_template = str(tc["prompt_rules"].get("description_example_template", "") or "").strip()
    if full_template and "{" in full_template and "}" in full_template:
        ctx.update({
            "opening": opening,
            "hikaye": hikaye,
            "details_block": detaylar,
            "story_size_paragraph": size_story_template,
            "no_extra_fees_block": no_extra_fees,
            "easy_returns_block": easy_returns,
            "footer_block": sabit_alt,
        })
        return _render_template_text(full_template, ctx)

    return "\n\n".join(filter(None, [
        opening,
        no_extra_fees,
        detaylar,
        easy_returns,
        hikaye,
        sabit_alt,
    ]))


def _rate_limit_fallback_ai(
    urun_id: str,
    boyut_ft: str,
    boyut_cm: str,
    metrekare: float,
    fiyat_usd: int,
    genislik_cm=None,
    uzunluk_cm=None,
    template_config: dict = None,
) -> dict:
    norm_template = template_config_normallestir(template_config)
    rounded_ft = _rounded_ft_etiketi(boyut_ft)
    tip = _tip_tahmin(boyut_ft)
    renk1 = "Beige"
    renk2 = "Brown"
    pattern_etsy = "Oriental"
    pattern = "Traditional"
    stil = "Vintage Oushak"
    koken = "Turkish"
    home_style = "Bohemian & eclectic"
    shop_section = _shop_section_tahmin(boyut_ft, metrekare, tip, pattern_etsy, stil)
    ana_resim_tag = "-".join([
        rounded_ft.lower(),
        "ft",
        "vintage",
        "turkish",
        tip.lower(),
        "rug",
        "beige",
        "brown",
        "wool",
        "handmade",
    ])
    ai = {
        "baslik": _fallback_baslik_olustur(rounded_ft, tip, renk1, renk2, pattern_etsy, koken, stil, shop_section),
        "taglar": _fallback_taglari_olustur(rounded_ft, tip, renk1, renk2, pattern_etsy, koken, stil, shop_section, home_style),
        "renk1": renk1,
        "renk2": renk2,
        "renk_scheme": "Neutral Beige, Warm Brown",
        "pattern": pattern,
        "tahmini_yil": "Vintage",
        "pile_cm": "",
        "stil": stil,
        "koken": koken,
        "opening": (
            f"This {rounded_ft} ft vintage Turkish {tip.lower()} brings a collected, time-softened character "
            f"that works beautifully when you need warmth, texture, and one-of-a-kind scale."
        ),
        "hikaye": "\n\n".join([
            "Its time-softened palette and vintage Turkish character create an easy, collected look that feels warm rather than overly formal.",
            f"With its versatile {rounded_ft} ft proportions, it works beautifully in interiors that need a longer visual line, soft texture, and authentic handmade presence.",
            "Handmade wool construction gives the piece a durable, tactile quality that feels honest underfoot and easy to layer into daily living spaces.",
            "It suits bohemian, farmhouse, rustic, and quietly traditional rooms while still feeling distinctive enough to stand out as a one-of-a-kind vintage find.",
        ]),
        "ana_resim_tag": ana_resim_tag,
        "pattern_etsy": pattern_etsy,
        "tip": tip,
        "home_style": home_style,
        "shop_section": shop_section,
    }
    ai = _ai_sonuc_normallestir(ai, norm_template)
    ai = _etsy_alanlarini_tamamla(ai, boyut_ft, metrekare)
    _validate(ai, norm_template)
    aciklama = description_olustur(
        ai,
        boyut_ft,
        boyut_cm,
        metrekare,
        genislik_cm,
        uzunluk_cm,
        norm_template,
        urun_id=urun_id,
    )
    return {
        **ai,
        "aciklama": aciklama,
        "basarili": True,
        "hata": None,
        "fallback_kullanildi": True,
        "uyari": "Gemini 429 nedeniyle yedek listing icerigi kullanildi.",
    }


# ── Gemini API ────────────────────────────────────────────────────────────────

def gorsel_to_base64(dosya_yolu: str) -> str:
    with open(dosya_yolu, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def url_to_base64(url: str) -> tuple[str, str]:
    with httpx.Client(timeout=30.0) as client:
        r = client.get(url)
        r.raise_for_status()
    ct = r.headers.get("content-type", "image/jpeg").split(";")[0]
    return base64.b64encode(r.content).decode("utf-8"), ct


def _429_turu_tespit_et(response: httpx.Response) -> str:
    """429 hatasının türünü döner: 'rpd' (günlük kota) veya 'rpm' (dakika kotası)."""
    try:
        metin = response.text.lower()
        if "perday" in metin or "per_day" in metin or "daily" in metin or "requests_per_day" in metin:
            return "rpd"
    except Exception:
        pass
    return "rpm"


def _gemini_hata_mesaji(response: httpx.Response) -> str:
    try:
        veri = response.json()
    except Exception:
        veri = {}
    detay = ""
    if isinstance(veri, dict):
        error = veri.get("error", {})
        if isinstance(error, dict):
            detay = str(error.get("message", "") or "").strip()
    if not detay:
        detay = str(response.text or "").strip()[:300]
    return detay


def _gemini_isle(prompt: str, gorsel_b64: str, mime: str) -> dict:
    import time
    # ── Rate limiter: tüm kullanıcılar için global sıra ──────────────────────
    with _gemini_lock:
        _gecen = time.monotonic() - _gemini_last_call[0]
        if _gecen < _GEMINI_MIN_INTERVAL:
            time.sleep(_GEMINI_MIN_INTERVAL - _gecen)
        _gemini_last_call[0] = time.monotonic()
    # ─────────────────────────────────────────────────────────────────────────
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ValueError("GEMINI_API_KEY environment variable eksik.")

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": gorsel_b64}}
            ]
        }],
        "generationConfig": {"temperature": 0.5, "maxOutputTokens": 8192}
    }

    son_hata = None
    for deneme in range(GEMINI_RETRY_ATTEMPTS):
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    GEMINI_URL,
                    params={"key": key},
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
        except httpx.TimeoutException as e:
            son_hata = e
            if deneme < GEMINI_RETRY_ATTEMPTS - 1:
                time.sleep(GEMINI_RETRY_BACKOFFS[min(deneme, len(GEMINI_RETRY_BACKOFFS) - 1)])
                continue
            raise Exception("Gemini istegi zaman asimina ugradi. Ag veya servis yogun olabilir; biraz sonra tekrar deneyin.") from e
        except httpx.HTTPError as e:
            son_hata = e
            if deneme < GEMINI_RETRY_ATTEMPTS - 1:
                time.sleep(GEMINI_RETRY_BACKOFFS[min(deneme, len(GEMINI_RETRY_BACKOFFS) - 1)])
                continue
            raise

        if response.status_code == 429:
            _tur = _429_turu_tespit_et(response)
            if _tur == "rpd":
                # Günlük kota dolmuş — retry faydasız, hemen hata fırlat
                raise Exception(
                    "Gemini gunluk kota doldu (429 RPD). "
                    "Kota gece yarisi (UTC) sifirlanir. Yarin tekrar deneyin."
                )
            # RPM (dakika kotası) → backoff ile retry
            son_hata = Exception(_gemini_hata_mesaji(response) or "Gemini rate limit (429)")
            if deneme < GEMINI_RETRY_ATTEMPTS - 1:
                # 429 için çok daha uzun bekleme: dakika sıfırlanmasını bekle
                time.sleep(GEMINI_RATE_LIMIT_BACKOFFS[min(deneme, len(GEMINI_RATE_LIMIT_BACKOFFS) - 1)])
                continue
            raise Exception(
                "Gemini dakika kotasi doldu (429 RPM). "
                "1-2 dakika bekleyip tekrar deneyin. "
                "Cok yogun kullanim icin aistudio.google.com/apikey billing kontrol edin."
            )
        if response.status_code == 403:
            raise Exception("Gemini API key yetkisiz (403). Key geçerli mi ve Generative Language API aktif mi? aistudio.google.com/apikey adresini kontrol edin.")
        if response.status_code >= 500:
            son_hata = Exception(_gemini_hata_mesaji(response) or f"Gemini sunucu hatasi ({response.status_code})")
            if deneme < GEMINI_RETRY_ATTEMPTS - 1:
                time.sleep(GEMINI_RETRY_BACKOFFS[min(deneme, len(GEMINI_RETRY_BACKOFFS) - 1)])
                continue
        response.raise_for_status()
        break
    else:
        raise son_hata or Exception("Gemini istegi basarisiz oldu.")

    veri    = response.json()
    icerik  = veri["candidates"][0]["content"]["parts"][0]["text"]
    return _json_yanitini_coz(icerik)


def _prompt_olustur(boyut_ft: str, boyut_cm: str, metrekare: float, fiyat_usd: int,
                    template_config: dict = None) -> str:
    tc = template_config_normallestir(template_config)
    pr = tc["prompt_rules"]
    extra_instructions = tc.get("prompt_extra_instructions", "")
    _extra_block = f"ADDITIONAL STORE INSTRUCTIONS:\n{extra_instructions}\n\n" if extra_instructions else ""
    title_rules = _kural_birlesik(pr["title_rules"], "STORE TITLE BRIEF:", pr.get("title_brief", ""))
    tag_rules = _kural_birlesik(pr["tag_rules"], "STORE TAG STRATEGY:", pr.get("tag_strategy", ""))
    story_rules = _kural_birlesik(pr["story_rules"], "STORE DESCRIPTION BRIEF:", pr.get("description_brief", ""))
    if pr.get("description_example_template", "").strip():
        story_rules = _kural_birlesik(
            story_rules,
            "DESCRIPTION EXAMPLE FRAMEWORK (keep the structure and tone logic, but rewrite dynamically for this rug):",
            pr.get("description_example_template", ""),
        )
    tag_example = ", ".join(['"..."'] * pr["tag_count"])
    return f"""You are an expert Etsy copywriter and SEO specialist for vintage & antique rugs.
Analyze this rug photo carefully and return ONLY a valid JSON object.

PRODUCT DATA (use exactly as given — do not alter):
- Size: {boyut_ft} ft ({boyut_cm} cm)
- Area: {metrekare} m²
- Price: ${fiyat_usd} USD

OUTPUT FIELDS — follow every rule exactly:

1. "baslik" (string, target {pr["title_target_min"]}–{pr["title_target_max"]} chars, hard max {pr["title_max_length"]})
   {title_rules}
   HARD RULES:
   - The first 40 characters matter most; make them keyword-rich and specific to this rug.
   - Do NOT make every listing start with the same phrase pattern.
   - Never go below {pr["title_target_min"]} characters unless impossible; never exceed {pr["title_max_length"]}.

2. "taglar" (array of exactly {pr["tag_count"]} strings, each max {pr["tag_max_length"]} chars)
   {tag_rules}
   HARD RULES:
   - Never use "?" or any placeholder in any tag.
   - Use the rounded size, not raw decimal size, in size tags.
   - Include at least 3 size-based tags.
   - Include at least 2 color-based tags using the visible rug colors.
   - If the rug is a Runner, use runner wording in relevant size/type tags; do not use area rug wording for those tags.
   - Keep tags varied; avoid repeating the same opening words across listings.

3. "renk1" (string) — dominant color. MUST be EXACTLY one of these Etsy values (case-sensitive):
   Beige, Black, Blue, Bronze, Brown, Clear, Copper, Gold, Gray, Green, Orange, Pink, Purple, Rainbow, Red, Rose gold, Silver, White, Yellow
   Pick the closest match to what you see. No other values allowed.
   Map non-allowed color words to the nearest allowed Etsy value before replying:
   Ivory/Cream/Off-white/Sand -> Beige
   Taupe/Tan -> Brown
   Burgundy/Crimson/Wine/Dark red -> Red
   Sage/Olive -> Green
   Teal/Navy -> Blue
   Mustard/Amber/Saffron -> Yellow
   Rust/Terracotta — VISUAL TEST (look at the rug, not the word):
     • If the color reads as RED first when you look at it (deep, dark, clearly red-dominant) → Red
     • If the color reads as ORANGE first (warm, earthy, orange-dominant) → Orange
     • A deep rust-red like this example rug = Red. A bright burnt-orange = Orange.
     • When in doubt: compare to a traffic-light red vs a pumpkin orange. Which is closer?
   Reply with the allowed Etsy value only, never the raw synonym.

4. "renk2" (string) — second color. MUST be EXACTLY one of the same Etsy list above.
   Apply the same nearest-allowed-value mapping rules above.

5. "renk_scheme" (string) — two descriptive color names for the description text, separated by comma.
   Write what you actually see in the rug — be visual and specific.
   The customer must instantly picture the color — do NOT use abstract names like "Desert Clay" or "Smoky Quartz".
   Good examples: "Warm Ivory, Faded Terracotta" / "Soft Camel, Dusty Blue" / "Aged Cream, Rustic Red"

6. "pattern" (string) — one word: Geometric, Floral, Medallion, Tribal, Abstract, Kilim, etc.

7. "tahmini_yil" (string) — estimated decade based on visual style.
   Format: "1930s" or "Early 20th century" or "Mid-Century" etc.
   Be honest — if unclear, write "Vintage".

8. "pile_cm" (string or null) — estimated pile height in cm, e.g. "0.50". Null if flat-weave/kilim.

9. "stil" (string) — 1-2 style keywords: Vintage, Bohemian, Traditional, Oushak, Kilim, etc.
10. "koken" (string) — best origin guess: Turkish, Persian, Moroccan, Central Asian, etc.

11. "opening" (string)
    {pr["opening_rules"]}

12. "hikaye" (string)
    {story_rules}

13. "ana_resim_tag" (string) — a long-tail SEO filename for the hero/main photo.
    Use 8-13 keywords joined by hyphens only (lowercase, no spaces, no special chars).
    Include: ft size, style, color(s), material, origin. This will be used as the image filename.
    Example: "5x8-ft-vintage-turkish-oushak-rug-red-beige-wool-handmade-bohemian-bedroom"

14. "pattern_etsy" (string) — MUST be EXACTLY one of these Etsy pattern values (case-sensitive):
    Abstract, Animal print, Bordered, Camouflage, Check, Floral, Geometric, Ikat, Moroccan,
    Ombré, Oriental, Paisley, Patchwork, Persian, Plants & trees, Polka dot, Solid, Southwestern, Striped
    This is the canonical shared dropdown list used across ALL stores.
    Pick the closest match to what you see. No other values allowed.
    Map non-allowed rug jargon to the nearest allowed Etsy value before replying:
    Medallion/Traditional/Classic -> Oriental
    Kilim/Flatweave -> Geometric
    Botanical/Tree motif -> Plants & trees
    Minimal/Plain -> Solid
    Tribal -> Southwestern
    Reply with the allowed Etsy value only, never the raw synonym.
    Do NOT default to "Oriental" unless the rug truly reads as traditional/oriental rather than something more specific like Geometric, Floral, Moroccan, Kilim-like, or Patchwork.
    IMPORTANT: Decide from the rug image itself first. Do not choose "Geometric" for every rug. If the rug reads as medallion/traditional, choose Oriental or Persian; if floral motifs dominate, choose Floral; if patchwork blocks are visible, choose Patchwork; if striped bands dominate, choose Striped.

15. "tip" (string) — MUST be EXACTLY one of these Etsy type values (case-sensitive):
    Accent, Area, Runner
    This is the canonical shared dropdown list used across ALL stores.
    Accent = small rugs (under 4 ft on shortest side)
    Runner = long narrow rugs (length ≥ 2.5× width — e.g. 2x6, 2x8, 3x8, 3x10, 2x12)
    Area = everything else
    Never return phrases like "Runner Rug" or "Area Rug". Reply with Accent, Area, or Runner only.

16. "home_style" (string) — MUST be EXACTLY one of these Etsy home style values (case-sensitive):
    Bohemian & eclectic, Coastal & tropical, Contemporary, Country & farmhouse,
    Industrial & utility, Rustic & primitive, Scandinavian
    Pick the best match for this rug's aesthetic. No other values allowed.

17. "shop_section" (string) — MUST be EXACTLY one of these values (case-sensitive):
    Oversized Rugs, Large Rugs, Medium Rugs, Small Rugs, Runner Rugs, Hemp Rug Kilim, Kilim Rugs, Mini Rugs - Doormats, Gifts
    This is the canonical shared dropdown list used across ALL stores.
    Selection rules based on size and type:
    - Runner Rugs → length ≥ 2.5× width (typical runners: 2x6, 2x8, 3x8, 3x10, 2x12, etc.)
    - Oversized Rugs → area ≥ 9 m² or shortest side ≥ 9 ft
    - Large Rugs → area 6–9 m² or typical 8x10, 9x12 ft
    - Medium Rugs → area 3–6 m² or typical 5x8, 6x9 ft
    - Small Rugs → area 1–3 m² or typical 3x5, 4x6 ft
    - Mini Rugs - Doormats → area < 1 m² or under 2x3 ft
    - Kilim Rugs → flat-weave kilim pattern (no pile)
    - Hemp Rug Kilim → hemp material kilim
    No other values allowed.
    Reply with the allowed section label only.

{_extra_block}Respond ONLY with valid JSON, no markdown, no extra text:
NON-NEGOTIABLE:
- Do not invent labels outside the allowed lists.
- If you would naturally say Ivory, Cream, Off-white or Medallion, convert it to the nearest allowed Etsy value before replying.
- If an enum field is uncertain, still choose the single closest allowed value from its allowed list.
- Do not leave any required field empty.
{{
  "baslik": "...",
  "taglar": [{tag_example}],
  "renk1": "...",
  "renk2": "...",
  "renk_scheme": "...",
  "pattern": "...",
  "tahmini_yil": "...",
  "pile_cm": "...",
  "stil": "...",
  "koken": "...",
  "opening": "...",
  "hikaye": "...",
  "ana_resim_tag": "5x8-ft-vintage-turkish-oushak-rug-red-beige-wool-handmade-bohemian-bedroom",
  "pattern_etsy": "...",
  "tip": "...",
  "home_style": "...",
  "shop_section": "..."
}}"""


# ── Public API ────────────────────────────────────────────────────────────────

def ai_icerik_url(
    resim_url: str,
    urun_id: str,
    boyut_ft: str,
    boyut_cm: str,
    metrekare: float,
    fiyat_usd: int,
    genislik_cm=None,
    uzunluk_cm=None,
    template_config: dict = None,
) -> dict:
    """URL'den resim alarak AI içerik üretir."""
    try:
        gorsel_b64, mime = url_to_base64(resim_url)
        norm_template = template_config_normallestir(template_config)
        prompt = _prompt_olustur(boyut_ft, boyut_cm, metrekare, fiyat_usd, norm_template)
        son_hata = None
        # İlk deneme: normal çağrı
        # İkinci deneme: yalnızca non-429 hatalarında (JSON parse, validation vb.)
        # 429 gelirse hemen hata dön — sheet'e yanlış veri yazılmasın.
        for _ in range(2):
            try:
                ai = _gemini_isle(prompt, gorsel_b64, mime)
                ai = _ai_sonuc_normallestir(ai, norm_template)
                ai = _etsy_alanlarini_tamamla(ai, boyut_ft, metrekare)
                _validate(ai, norm_template)
                aciklama = description_olustur(ai, boyut_ft, boyut_cm, metrekare, genislik_cm, uzunluk_cm, norm_template, urun_id=urun_id)
                return {**ai, "aciklama": aciklama, "basarili": True, "hata": None}
            except Exception as e:
                son_hata = e
                _e_str = str(e).lower()
                if "429 rpd" in _e_str or "gunluk kota" in _e_str:
                    # Günlük kota dolmuş — retry faydasız, hemen çık
                    break
                if "rate limit (429)" in _e_str or "429 rpm" in _e_str:
                    # Dakika kotası — _gemini_isle() zaten backoff yaptı, çık
                    break
                # Diğer hatalar (JSON parse, validation): bir kez daha dene
        if son_hata:
            print(f"[AI:{urun_id}] URL uretim hatasi -> {type(son_hata).__name__}: {son_hata}")
        if isinstance(son_hata, json.JSONDecodeError):
            return {"basarili": False, "hata": f"JSON parse hatası: {son_hata}"}
        _e_str = str(son_hata).lower() if son_hata else ""
        if "429 rpd" in _e_str or "gunluk kota" in _e_str:
            return {
                "basarili": False,
                "hata": (
                    "⏳ Gemini günlük kotası doldu (429). "
                    "Kota gece yarısı (UTC) sıfırlanır — yarın tekrar deneyin."
                ),
                "rate_limit": True,
                "rate_limit_turu": "rpd",
            }
        if son_hata and ("rate limit (429)" in _e_str or "429 rpm" in _e_str):
            return {
                "basarili": False,
                "hata": (
                    "⏳ Gemini dakika kotası doldu (429). "
                    "1-2 dakika bekleyip bu ürünü tekrar AI kuyruğuna ekleyin."
                ),
                "rate_limit": True,
                "rate_limit_turu": "rpm",
            }
        return {"basarili": False, "hata": str(son_hata or 'AI uretimi basarisiz') }
    except Exception as e:
        print(f"[AI:{urun_id}] URL uretim dis hata -> {type(e).__name__}: {e}")
        return {"basarili": False, "hata": str(e)}


def ai_icerik_uret(
    ana_fotograf_yolu: str,
    urun_id: str,
    boyut_ft: str,
    genislik_ft: float,
    uzunluk_ft: float,
    boyut_cm: str,
    metrekare: float,
    fiyat_usd: int,
    genislik_cm=None,
    uzunluk_cm=None,
    template_config: dict = None,
) -> dict:
    """Dosya yolundan AI içerik üretir."""
    try:
        gorsel_b64 = gorsel_to_base64(ana_fotograf_yolu)
        uzanti = Path(ana_fotograf_yolu).suffix.lower().replace(".", "")
        mime = f"image/{'jpeg' if uzanti in ['jpg', 'jpeg'] else uzanti}"
        norm_template = template_config_normallestir(template_config)
        prompt = _prompt_olustur(boyut_ft, boyut_cm, metrekare, fiyat_usd, norm_template)
        son_hata = None
        for _ in range(2):
            try:
                ai = _gemini_isle(prompt, gorsel_b64, mime)
                ai = _ai_sonuc_normallestir(ai, norm_template)
                ai = _etsy_alanlarini_tamamla(ai, boyut_ft, metrekare)
                _validate(ai, norm_template)
                aciklama = description_olustur(ai, boyut_ft, boyut_cm, metrekare, genislik_cm, uzunluk_cm, norm_template, urun_id=urun_id)
                return {**ai, "aciklama": aciklama, "basarili": True, "hata": None}
            except Exception as e:
                son_hata = e
                _e_str = str(e).lower()
                if "429 rpd" in _e_str or "gunluk kota" in _e_str:
                    break
                if "rate limit (429)" in _e_str or "429 rpm" in _e_str:
                    break
        if son_hata:
            print(f"[AI:{urun_id}] Dosya uretim hatasi -> {type(son_hata).__name__}: {son_hata}")
        if isinstance(son_hata, json.JSONDecodeError):
            return {"basarili": False, "hata": f"JSON parse hatası: {son_hata}"}
        _e_str2 = str(son_hata).lower() if son_hata else ""
        if "429 rpd" in _e_str2 or "gunluk kota" in _e_str2:
            return {
                "basarili": False,
                "hata": (
                    "⏳ Gemini günlük kotası doldu (429). "
                    "Kota gece yarısı (UTC) sıfırlanır — yarın tekrar deneyin."
                ),
                "rate_limit": True,
                "rate_limit_turu": "rpd",
            }
        if son_hata and ("rate limit (429)" in _e_str2 or "429 rpm" in _e_str2):
            return {
                "basarili": False,
                "hata": (
                    "⏳ Gemini dakika kotası doldu (429). "
                    "1-2 dakika bekleyip bu ürünü tekrar AI kuyruğuna ekleyin."
                ),
                "rate_limit": True,
                "rate_limit_turu": "rpm",
            }
        return {"basarili": False, "hata": str(son_hata or 'AI uretimi basarisiz') }
    except Exception as e:
        print(f"[AI:{urun_id}] Dosya uretim dis hata -> {type(e).__name__}: {e}")
        return {"basarili": False, "hata": str(e)}


def _validate(ai: dict, template_config: dict = None):
    tc = template_config_normallestir(template_config)
    pr = tc["prompt_rules"]
    assert "baslik"    in ai, "baslik eksik"
    ai["baslik"] = _baslik_kisalt(ai.get("baslik", ""), pr["title_max_length"])
    assert ai["baslik"], "baslik bos"
    assert len(ai["baslik"]) <= pr["title_max_length"], f"Başlık çok uzun: {len(ai['baslik'])} karakter"
    assert "taglar"    in ai, "taglar eksik"
    ai["taglar"] = _taglari_normallestir(ai["taglar"], pr["tag_count"], pr["tag_max_length"], pad_missing=False)
    assert len(ai["taglar"]) == pr["tag_count"], f"Tag sayısı {pr['tag_count']} olmalı, {len(ai['taglar'])} var"
    assert all(ai["taglar"]), "taglar bos birakilamaz"
    assert "opening"      in ai and str(ai.get("opening", "")).strip(), "opening eksik"
    assert "hikaye"       in ai and str(ai.get("hikaye", "")).strip(), "hikaye eksik"
    assert "renk_scheme"  in ai and str(ai.get("renk_scheme", "")).strip(), "renk_scheme eksik"
    assert "pattern"      in ai and str(ai.get("pattern", "")).strip(), "pattern eksik"
    assert "ana_resim_tag" in ai and str(ai.get("ana_resim_tag", "")).strip(), "ana_resim_tag eksik"
    assert ai.get("renk1", "") in ETSY_RENKLERI, f"Gecersiz renk1: {ai.get('renk1', '')}"
    assert ai.get("renk2", "") in ETSY_RENKLERI, f"Gecersiz renk2: {ai.get('renk2', '')}"
    assert ai.get("pattern_etsy", "") in ETSY_PATTERNLERI, f"Gecersiz pattern_etsy: {ai.get('pattern_etsy', '')}"
    assert ai.get("tip", "") in ETSY_TIPLERI, f"Gecersiz tip: {ai.get('tip', '')}"
    assert ai.get("home_style", "") in ETSY_HOME_STYLE, f"Gecersiz home_style: {ai.get('home_style', '')}"
    assert ai.get("shop_section", "") in ETSY_SHOP_SECTIONS, f"Gecersiz shop_section: {ai.get('shop_section', '')}"
