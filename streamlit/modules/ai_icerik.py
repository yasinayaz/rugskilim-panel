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
GEMINI_MODEL   = "gemini-2.5-flash"
GEMINI_URL     = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


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
    "title_rules": """SIZE RULE: Round each ft dimension to the nearest whole number (2.8x9.9 → "3x10", 3.2x5.7 → "3x6", 3.6x9.3 → "4x9"). Use the ROUNDED size in the title.
Pack in: size, style, colors, pattern, material, origin, room use, Etsy search terms.

Use ONE of these two structures — vary between listings, do NOT always use the same one:

Structure A (size-first): [rounded size] ft [Style] [Origin] [Type] Rug | [Color] [Pattern] [Material] [Room] Rug
  Example: "3x10 ft Vintage Turkish Runner Rug | Faded Red Medallion Wool Hallway Carpet | Bohemian Oushak Accent Rug"

Structure B (material-first): [Weave] [Origin] [Style] [Type] [Size] ft – [Color adjective] [Color] – [Vintage/Age] [Material] [Room] Rug
  Example: "Handwoven Turkish Oushak Runner 3x10 ft – Muted Sage Green & Terracotta – Vintage Wool Kitchen Hallway Rug"

Choose the structure that sounds more natural for this specific rug.""",
    "tag_rules": """CRITICAL: Tags must be specific to THIS rug's photo — color, pattern, texture, size, origin you actually see.
Each tag = strong Etsy long-tail keyword phrase (2-3 words, not a single word).
Derive directly from: the visible colors, pattern type, weave style, probable origin, size category, room fit.
Do NOT use generic or copy-paste tags — every tag must reflect what you observe in this specific rug.

Think like an Etsy SEO expert. Cover a wide range of what buyers actually search for.
REQUIRED slots (use ALL core categories below, then fill remaining slots with color/pattern/texture tags):
- SIZE tags (MINIMUM 3 — each must be a DIFFERENT combination, no repeated words across them):
  slot 1: rounded size + rug type  → "3x8 runner rug"
  slot 2: rounded size + dominant color → "3x8 beige rug"
  slot 3: dominant color + rug type → "beige runner rug"  (no size here — avoids repeating "3x8")
- Core type (2-3 — ALWAYS include both an oushak tag and a handmade/vintage tag):
  "oushak rug" OR "oushak runner rug" (mandatory — high-value Etsy keyword), "handmade rug" or "vintage rug"
- Room fit (2-3): kitchen, hallway, entryway, living room, bedroom, etc.
- Color / pattern / texture (remaining): what you actually see — faded, muted, distressed, medallion, etc.

Do NOT repeat the same word combination.

Example for a 3x10 ft red geometric runner:
"3x10 runner rug", "3x10 red rug", "red runner rug",
"oushak runner rug", "handmade runner rug", "vintage runner rug",
"kitchen runner rug", "hallway runner rug", "entryway runner rug",
"medallion wool rug", "distressed wool rug", "turkish oushak rug", "living room rug" """,
    "opening_rules": """ONE punchy sentence that hooks the reader.
CRITICAL: Use the exact same core keywords from "baslik" — size, style, pattern, origin, material must appear here too.
Lead with the visual identity of the rug. Include size, style, and what feeling it gives.
Example: "This 2.8x9.9 ft Vintage Turkish Runner with its faded Medallion pattern carries the quiet confidence of a piece that has traveled decades to find the right room." """,
    "story_rules": """Write 4–5 short paragraphs.
- Para 1: Hook line ("Some rugs just fill a space. This brings soul.") + 1–2 sentences about the rug's era, pattern and dominant colors. Make it cinematic.
- Para 2: Size — what spaces it fits, how it anchors a room. Mention the raw ft size naturally. Also use the rounded size (e.g. "3x11") at least once here.
- Para 3: Material — what makes this rug honest and tactile. Wool? Cotton? Both?
- Para 4: Style versatility + room recommendations (Living room, Bedroom, Entryway, etc.) + decoration style fit (Bohemian, Country & farmhouse, etc.)
Use \\n between paragraphs. Do NOT use bullet points here. Keep it conversational, human, and warm.
SEO keywords to weave in naturally: the rounded size (e.g. "3x11 runner"), dominant color + rug type (e.g. "red runner rug"), vintage rug, handmade, wool, Turkish, antique area rug.
These same keywords appear in the tags — using them in the description too boosts Etsy SEO.""",
}

_DEFAULT_STATIC_TEXTS = {
    "no_extra_fees": _SABIT_NO_EXTRA_FEES,
    "easy_returns": _SABIT_EASY_RETURNS,
    "story_size_template": "",
    "footer": _SABIT_ALT,
}

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
        "rust": "Orange",
        "terracotta": "Orange",
        "orange": "Orange",
        "yellow": "Yellow",
        "mustard": "Yellow",
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
    norm["renk1"] = _etsy_renk_normalize(norm.get("renk1", ""))
    norm["renk2"] = _etsy_renk_normalize(norm.get("renk2", ""))
    norm["renk1"], norm["renk2"] = _renkleri_renk_schemeden_tamamla(
        norm.get("renk1", ""),
        norm.get("renk2", ""),
        norm.get("renk_scheme", ""),
    )

    norm["pattern_etsy"] = _pattern_etsy_karar_ver(
        norm.get("pattern_etsy", ""),
        norm.get("pattern", ""),
        norm.get("stil", ""),
        norm.get("baslik", ""),
    )

    beklenen_tip = _tip_tahmin(boyut_ft)
    norm["tip"] = _enum_normalize(norm.get("tip", ""), ETSY_TIPLERI)
    if not norm["tip"] or norm["tip"] != beklenen_tip:
        norm["tip"] = beklenen_tip

    norm["home_style"] = _enum_normalize(norm.get("home_style", ""), ETSY_HOME_STYLE, {
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
    })
    if not norm["home_style"]:
        norm["home_style"] = _home_style_tahmin(
            norm.get("stil", ""),
            norm.get("pattern", ""),
            norm.get("baslik", ""),
        )

    beklenen_shop_section = _shop_section_tahmin(
        boyut_ft,
        metrekare,
        norm.get("tip", ""),
        norm.get("pattern_etsy", ""),
        norm.get("stil", ""),
    )
    norm["shop_section"] = _enum_normalize(norm.get("shop_section", ""), ETSY_SHOP_SECTIONS)
    if not norm["shop_section"] or norm["shop_section"] != beklenen_shop_section:
        norm["shop_section"] = beklenen_shop_section
    return norm


def _oda_taglari(tip: str, shop_section: str) -> list[str]:
    if shop_section == "Mini Rugs - Doormats":
        return ["entryway rug", "bathroom rug", "door mat rug"]
    if tip == "Runner":
        return ["hallway runner rug", "kitchen runner rug", "entryway runner rug"]
    if tip == "Accent":
        return ["entryway accent rug", "bedroom accent rug", "bathroom accent rug"]
    return ["living room rug", "bedroom area rug", "dining room rug"]


def _fallback_taglari_olustur(rounded_ft: str, tip: str, renk1: str, renk2: str, pattern_etsy: str,
                              koken: str, stil: str, shop_section: str) -> list[str]:
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
        f"vintage {tip_lower} rug",
        f"handmade wool rug",
        f"{str(koken or 'turkish').lower()} rug",
        f"{str(stil or 'oushak').lower()} rug",
        f"{str(pattern_etsy or 'vintage').lower()} wool rug",
    ]
    oda_tags = _oda_taglari(tip, shop_section)
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


def _taglari_normallestir(taglar, tag_sayisi: int, tag_max_uzunluk: int) -> list:
    sonuc = []
    for tag in taglar or []:
        temiz = re.sub(r"\s+", " ", str(tag or "")).strip().strip('"')
        if temiz:
            sonuc.append(temiz[:tag_max_uzunluk].rstrip(" ,;:-|/"))
    sonuc = sonuc[:tag_sayisi]
    if len(sonuc) < tag_sayisi:
        sonuc.extend([""] * (tag_sayisi - len(sonuc)))
    return sonuc


def _ai_sonuc_normallestir(ai: dict, template_config: dict = None) -> dict:
    tc = template_config_normallestir(template_config)
    pr = tc["prompt_rules"]
    norm = dict(ai or {})
    norm["baslik"] = _baslik_kisalt(norm.get("baslik", ""), pr["title_max_length"])
    norm["taglar"] = _taglari_normallestir(norm.get("taglar", []), pr["tag_count"], pr["tag_max_length"])
    for alan in ["opening", "hikaye", "renk_scheme", "pattern", "ana_resim_tag"]:
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


def _template_context(ai: dict, urun_id: str, boyut_ft: str, boyut_cm: str, metrekare: float) -> dict:
    rounded_ft = _rounded_ft_etiketi(boyut_ft)
    sqft = round(metrekare * 10.764, 2) if metrekare else ""
    tip = str(ai.get("tip") or "Rug").strip() or "Rug"
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
    hikaye_paragraflari = _hikaye_paragraflari(ai.get("hikaye", ""))
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


def _gemini_isle(prompt: str, gorsel_b64: str, mime: str) -> dict:
    import time
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

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            GEMINI_URL,
            params={"key": key},
            json=payload,
            headers={"Content-Type": "application/json"}
        )
    if response.status_code == 429:
        time.sleep(10)
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                GEMINI_URL,
                params={"key": key},
                json=payload,
                headers={"Content-Type": "application/json"}
            )
    if response.status_code == 429:
        raise Exception("Gemini rate limit (429). Billing aktif mi? aistudio.google.com/apikey kontrol edin.")
    response.raise_for_status()

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

4. "renk2" (string) — second color. MUST be EXACTLY one of the same Etsy list above.

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
    Do NOT default to "Oriental" unless the rug truly reads as traditional/oriental rather than something more specific like Geometric, Floral, Moroccan, Kilim-like, or Patchwork.
    IMPORTANT: Decide from the rug image itself first. Do not choose "Geometric" for every rug. If the rug reads as medallion/traditional, choose Oriental or Persian; if floral motifs dominate, choose Floral; if patchwork blocks are visible, choose Patchwork; if striped bands dominate, choose Striped.

15. "tip" (string) — MUST be EXACTLY one of these Etsy type values (case-sensitive):
    Accent, Area, Runner
    This is the canonical shared dropdown list used across ALL stores.
    Accent = small rugs (under 4 ft on shortest side)
    Runner = long narrow rugs (length ≥ 2.5× width — e.g. 2x6, 2x8, 3x8, 3x10, 2x12)
    Area = everything else

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

{_extra_block}Respond ONLY with valid JSON, no markdown, no extra text:
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
        if isinstance(son_hata, json.JSONDecodeError):
            return {"basarili": False, "hata": f"JSON parse hatası: {son_hata}"}
        return {"basarili": False, "hata": str(son_hata or 'AI uretimi basarisiz') }
    except Exception as e:
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
        if isinstance(son_hata, json.JSONDecodeError):
            return {"basarili": False, "hata": f"JSON parse hatası: {son_hata}"}
        return {"basarili": False, "hata": str(son_hata or 'AI uretimi basarisiz') }
    except Exception as e:
        return {"basarili": False, "hata": str(e)}


def _validate(ai: dict, template_config: dict = None):
    tc = template_config_normallestir(template_config)
    pr = tc["prompt_rules"]
    assert "baslik"    in ai, "baslik eksik"
    ai["baslik"] = _baslik_kisalt(ai.get("baslik", ""), pr["title_max_length"])
    assert len(ai["baslik"]) <= pr["title_max_length"], f"Başlık çok uzun: {len(ai['baslik'])} karakter"
    assert "taglar"    in ai, "taglar eksik"
    ai["taglar"] = _taglari_normallestir(ai["taglar"], pr["tag_count"], pr["tag_max_length"])
    assert len(ai["taglar"]) == pr["tag_count"], f"Tag sayısı {pr['tag_count']} olmalı, {len(ai['taglar'])} var"
    assert "opening"      in ai, "opening eksik"
    assert "hikaye"       in ai, "hikaye eksik"
    assert "renk_scheme"  in ai, "renk_scheme eksik"
    assert "pattern"      in ai, "pattern eksik"
    assert "ana_resim_tag" in ai, "ana_resim_tag eksik"
    assert ai.get("pattern_etsy", "") in ETSY_PATTERNLERI, f"Gecersiz pattern_etsy: {ai.get('pattern_etsy', '')}"
    assert ai.get("tip", "") in ETSY_TIPLERI, f"Gecersiz tip: {ai.get('tip', '')}"
    assert ai.get("home_style", "") in ETSY_HOME_STYLE, f"Gecersiz home_style: {ai.get('home_style', '')}"
    assert ai.get("shop_section", "") in ETSY_SHOP_SECTIONS, f"Gecersiz shop_section: {ai.get('shop_section', '')}"


def fallback_ai_icerik(
    urun_id: str,
    boyut_ft: str,
    boyut_cm: str,
    metrekare: float,
    fiyat_usd: int,
    genislik_cm=None,
    uzunluk_cm=None,
    template_config: dict = None,
    hata_mesaji: str = "",
) -> dict:
    tc = template_config_normallestir(template_config)
    rounded_ft = _rounded_ft_etiketi(boyut_ft)
    tip = _varsayilan_tip(boyut_ft)
    koken = "Turkish"
    stil = "Oushak"
    pattern_etsy = "Oriental"
    home_style = "Bohemian & eclectic"
    shop_section = _shop_section_tahmin(boyut_ft, metrekare, tip, pattern_etsy, stil)
    renk1 = "Beige" if tip != "Runner" else "Red"
    renk2 = "Brown" if tip != "Runner" else "Gray"
    baslik = _fallback_baslik_olustur(rounded_ft, tip, renk1, renk2, pattern_etsy, koken, stil, shop_section).strip()
    taglar = _fallback_taglari_olustur(rounded_ft, tip, renk1, renk2, pattern_etsy, koken, stil, shop_section)
    ai = {
        "baslik": baslik,
        "taglar": taglar,
        "opening": f"This {rounded_ft} ft vintage Turkish {tip.lower()} brings soft character and timeless handmade texture into the room.",
        "hikaye": (
            f"This handmade vintage Turkish {tip.lower()} carries the quiet depth that makes one-of-a-kind rugs feel collected rather than decorated.\n\n"
            f"With a {boyut_ft} ft profile and a rounded {rounded_ft} fit, it works beautifully in spaces that need warmth, movement, and visual balance.\n\n"
            "Its woven texture and aged character make it easy to place in bohemian, collected, rustic, or layered interiors.\n\n"
            "A distinctive piece like this adds soul underfoot while staying versatile enough for everyday living."
        ),
        "renk1": renk1,
        "renk2": renk2,
        "renk_scheme": f"Faded {renk1}, Muted {renk2}",
        "pattern": pattern_etsy,
        "pattern_etsy": pattern_etsy,
        "shop_section": shop_section,
        "tip": tip,
        "ana_resim_tag": f"{rounded_ft} vintage turkish rug".strip(),
        "tahmini_yil": "Vintage",
        "stil": stil,
        "koken": koken,
        "home_style": home_style,
        "hata_notu": str(hata_mesaji or "").strip(),
    }
    ai = _ai_sonuc_normallestir(ai, tc)
    ai = _etsy_alanlarini_tamamla(ai, boyut_ft, metrekare)
    ai["aciklama"] = description_olustur(
        ai,
        boyut_ft,
        boyut_cm,
        metrekare,
        genislik_cm,
        uzunluk_cm,
        tc,
        urun_id=urun_id,
    )
    ai["basarili"] = True
    ai["hata"] = None
    ai["fallback_kullanildi"] = True
    return ai
