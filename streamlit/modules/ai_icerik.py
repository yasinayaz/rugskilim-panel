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
    match = re.search(r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)", str(boyut_ft))
    if not match:
        return "Rug"
    try:
        en = float(match.group(1))
        boy = float(match.group(2))
    except Exception:
        return "Rug"
    kisa, uzun = sorted([en, boy])
    return "Runner" if kisa <= 4 and uzun >= 6 else "Area Rug"


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
    icerik  = re.sub(r"```json\s*|\s*```", "", icerik).strip()
    return json.loads(icerik)


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

2. "taglar" (array of exactly {pr["tag_count"]} strings, each max {pr["tag_max_length"]} chars)
   {tag_rules}

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
    Pick the closest match to what you see. No other values allowed.

15. "tip" (string) — MUST be EXACTLY one of these Etsy type values (case-sensitive):
    Accent, Area, Runner
    Accent = small rugs (under 4 ft on shortest side)
    Runner = long narrow rugs (length ≥ 2.5× width — e.g. 2x6, 2x8, 3x8, 3x10, 2x12)
    Area = everything else

16. "home_style" (string) — MUST be EXACTLY one of these Etsy home style values (case-sensitive):
    Bohemian & eclectic, Coastal & tropical, Contemporary, Country & farmhouse,
    Industrial & utility, Rustic & primitive, Scandinavian
    Pick the best match for this rug's aesthetic. No other values allowed.

17. "shop_section" (string) — MUST be EXACTLY one of these values (case-sensitive):
    Oversized Rugs, Large Rugs, Medium Rugs, Small Rugs, Runner Rugs, Hemp Rug Kilim, Kilim Rugs, Mini Rugs - Doormats, Gifts
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
        ai = _gemini_isle(prompt, gorsel_b64, mime)
        ai = _ai_sonuc_normallestir(ai, norm_template)
        _validate(ai, norm_template)
        aciklama = description_olustur(ai, boyut_ft, boyut_cm, metrekare, genislik_cm, uzunluk_cm, norm_template, urun_id=urun_id)
        return {**ai, "aciklama": aciklama, "basarili": True, "hata": None}
    except json.JSONDecodeError as e:
        return {"basarili": False, "hata": f"JSON parse hatası: {e}"}
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
        ai = _gemini_isle(prompt, gorsel_b64, mime)
        ai = _ai_sonuc_normallestir(ai, norm_template)
        _validate(ai, norm_template)
        aciklama = description_olustur(ai, boyut_ft, boyut_cm, metrekare, genislik_cm, uzunluk_cm, norm_template, urun_id=urun_id)
        return {**ai, "aciklama": aciklama, "basarili": True, "hata": None}
    except json.JSONDecodeError as e:
        return {"basarili": False, "hata": f"JSON parse hatası: {e}"}
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
    tip_tag = "runner rug" if tip == "Runner" else "area rug"
    baslik = f"{rounded_ft} ft Vintage Turkish {tip} | Handmade Wool Oushak Home Decor".strip()
    taglar = [
        f"{rounded_ft} {tip_tag}",
        f"{rounded_ft} turkish rug",
        "vintage turkish rug",
        "oushak rug",
        "handmade wool rug",
        "boho home decor",
        "turkish home decor",
        "entryway rug",
        "hallway rug",
        "living room rug",
        "one of a kind rug",
        "vintage wool rug",
        "anatolian rug",
    ]
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
        "renk1": "",
        "renk2": "",
        "renk_scheme": "Soft, timeworn vintage tones",
        "pattern": "Vintage Anatolian pattern",
        "pattern_etsy": "Anatolian",
        "shop_section": "",
        "tip": tip,
        "ana_resim_tag": f"{rounded_ft} vintage turkish rug".strip(),
        "tahmini_yil": "Vintage",
        "stil": "Vintage",
        "koken": "Turkish",
        "home_style": "Bohemian",
        "hata_notu": str(hata_mesaji or "").strip(),
    }
    ai = _ai_sonuc_normallestir(ai, tc)
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
