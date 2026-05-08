"""
pcloud_indirici.py
pCloud API ile klasör içindeki dosyaları indirir.
Playwright gerektirmez — token ile direkt API çağrısı yapar.

Ortam değişkeni:
  PCLOUD_TOKEN=...
  TEMP_DIR=C:\etsy_temp  (opsiyonel)
"""

import os
import asyncio
import httpx
from pathlib import Path

def _token() -> str:
    return os.environ.get("PCLOUD_TOKEN", "")
TEMP_DIR     = Path(os.environ.get("TEMP_DIR", r"C:\etsy_temp"))
HOSTS        = ["https://api.pcloud.com", "https://eapi.pcloud.com"]
RESIM_UZANTI = {".jpg", ".jpeg", ".png", ".webp"}


def _host_sec() -> str:
    """Çalışan pCloud host'u döndürür."""
    for host in HOSTS:
        try:
            r = httpx.get(f"{host}/userinfo", params={"auth": _token()}, timeout=10)
            if r.json().get("result") == 0:
                return host
        except Exception:
            continue
    raise ConnectionError("pCloud API'ye bağlanılamadı. Token geçerli mi?")


def _klasor_id_bul(host: str, yol: str) -> int:
    """Yola göre pCloud klasör ID'si döndürür."""
    parcalar = [p for p in yol.split("/") if p]
    klasor_id = 0  # kök

    for parca in parcalar:
        r = httpx.get(
            f"{host}/listfolder",
            params={"auth": _token(), "folderid": klasor_id, "nofiles": 1},
            timeout=15,
        )
        d = r.json()
        if d.get("result") != 0:
            raise Exception(f"Klasör listelenemedi: {d.get('error')}")

        icerik = d["metadata"].get("contents", [])
        bulunan = next(
            (i for i in icerik if i.get("isfolder") and i["name"] == parca),
            None,
        )
        if not bulunan:
            raise Exception(f"Klasör bulunamadı: '{parca}' (yol: {yol})")
        klasor_id = bulunan["folderid"]

    return klasor_id


def _dosyalari_listele(host: str, klasor_id: int) -> list[dict]:
    """Klasördeki resim dosyalarını listeler."""
    r = httpx.get(
        f"{host}/listfolder",
        params={"auth": _token(), "folderid": klasor_id},
        timeout=15,
    )
    d = r.json()
    if d.get("result") != 0:
        raise Exception(f"Dosya listelenemedi: {d.get('error')}")

    return [
        f for f in d["metadata"].get("contents", [])
        if not f.get("isfolder")
        and Path(f["name"]).suffix.lower() in RESIM_UZANTI
    ]


def _indirme_linki_al(host: str, fileid: int) -> str:
    """Dosya için geçici indirme linki alır."""
    r = httpx.get(
        f"{host}/getfilelink",
        params={"auth": _token(), "fileid": fileid},
        timeout=10,
    )
    d = r.json()
    if d.get("result") != 0:
        raise Exception(f"İndirme linki alınamadı: {d.get('error')}")
    return f"https://{d['hosts'][0]}{d['path']}"


async def _dosya_indir(url: str, hedef: Path, deneme: int = 3) -> bool:
    """Dosyayı URL'den async olarak indirir, başarısız olursa 3 kez dener."""
    timeout = httpx.Timeout(connect=15, read=60, write=30, pool=10)
    for i in range(deneme):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                async with client.stream("GET", url) as r:
                    r.raise_for_status()
                    with open(hedef, "wb") as f:
                        async for chunk in r.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
            return True
        except Exception as e:
            print(f"  ✗ İndirme hatası ({hedef.name}), deneme {i+1}/{deneme}: {e}")
            if i < deneme - 1:
                await asyncio.sleep(3)
    return False


async def pcloud_klasor_indir(klasor_yolu: str, urun_id: str, klasor_id: int = None) -> dict:
    """
    pCloud'dan belirtilen klasörü indirir.

    Args:
        klasor_yolu: pCloud'daki tam yol, örn: "01-VİNTAGE RUG/2025/13,11,2025/4102"
        urun_id:     Ürün kodu, örn: "4102"

    Returns:
        {"basarili": bool, "dosyalar": [...], "temp_klasor": str, "hata": str|None}
    """
    if not _token():
        return {"basarili": False, "dosyalar": [], "temp_klasor": "",
                "hata": "PCLOUD_TOKEN ortam değişkeni eksik"}

    temp_klasor = TEMP_DIR / urun_id
    temp_klasor.mkdir(parents=True, exist_ok=True)

    try:
        print(f"[pCloud] Host seçiliyor...")
        host = _host_sec()
        print(f"[pCloud] ✓ {host}")

        if klasor_id:
            print(f"[pCloud] Klasör ID ile direkt erişim: {klasor_id}")
        else:
            print(f"[pCloud] Klasör aranıyor: {klasor_yolu}")
            klasor_id = _klasor_id_bul(host, klasor_yolu)
            print(f"[pCloud] ✓ Klasör ID: {klasor_id}")

        dosyalar = _dosyalari_listele(host, klasor_id)
        print(f"[pCloud] {len(dosyalar)} resim bulundu")

        if not dosyalar:
            return {"basarili": False, "dosyalar": [], "temp_klasor": str(temp_klasor),
                    "hata": "Klasörde resim bulunamadı"}

        indirilen = []
        for dosya in dosyalar:
            ad   = dosya["name"]
            hedef = temp_klasor / ad
            print(f"[pCloud] İndiriliyor: {ad}")
            url = _indirme_linki_al(host, dosya["fileid"])
            if await _dosya_indir(url, hedef):
                indirilen.append(str(hedef))
                print(f"  ✓ {ad}")
            else:
                print(f"  ✗ {ad} atlandı")

        return {
            "basarili":    True,
            "dosyalar":    indirilen,
            "temp_klasor": str(temp_klasor),
            "hata":        None,
        }

    except Exception as e:
        return {
            "basarili":    False,
            "dosyalar":    [],
            "temp_klasor": str(temp_klasor),
            "hata":        str(e),
        }


async def temp_klasoru_sil(urun_id: str):
    """İşlem bittikten sonra geçici klasörü temizler."""
    import shutil
    klasor = TEMP_DIR / urun_id
    if klasor.exists():
        shutil.rmtree(klasor)
        print(f"[Temizlik] {klasor} silindi.")


# ── Test ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if not _token():
        print("HATA: PCLOUD_TOKEN ortam değişkenini set edin.")
        print("  Windows: set PCLOUD_TOKEN=...")
        sys.exit(1)

    sonuc = asyncio.run(pcloud_klasor_indir(
        klasor_yolu="01-VİNTAGE RUG/2025/13,11,2025/4102",
        urun_id="4102",
    ))

    print("\n" + "="*50)
    print("SONUÇ:", "✓ Başarılı" if sonuc["basarili"] else "✗ Hata")
    if sonuc["hata"]:
        print("Hata:", sonuc["hata"])
    else:
        print(f"İndirilen: {len(sonuc['dosyalar'])} dosya")
        for d in sonuc["dosyalar"]:
            print(f"  {d}")
