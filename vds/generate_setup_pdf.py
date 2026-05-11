from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


OUTPUT = Path(__file__).with_name("VDS_WINDOWS_KURULUM_REHBERI.pdf")


def p(text, style):
    return Paragraph(text.replace("\n", "<br/>"), style)


def build_pdf():
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "TitleCustom",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1f3a5f"),
        alignment=TA_LEFT,
        spaceAfter=10,
    )
    h1 = ParagraphStyle(
        "H1Custom",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#1f3a5f"),
        spaceBefore=10,
        spaceAfter=6,
    )
    body = ParagraphStyle(
        "BodyCustom",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=15,
        spaceAfter=6,
    )
    code = ParagraphStyle(
        "CodeCustom",
        parent=styles["BodyText"],
        fontName="Courier",
        fontSize=9,
        leading=12,
        backColor=colors.HexColor("#f3f4f6"),
        borderPadding=6,
        borderColor=colors.HexColor("#d1d5db"),
        borderWidth=0.5,
        borderRadius=2,
        spaceAfter=8,
    )

    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title="RugsKilim VDS Windows Kurulum Rehberi",
        author="OpenAI Codex",
    )

    story = []
    story.append(p("RugsKilim VDS Windows Kurulum Rehberi", title))
    story.append(p("Bu belge, Windows bilgisayarlara worker kurup Streamlit'ten <b>ready</b> durumuna gelen urunleri pCloud'dan indirmek, video uretmek ve <b>downloaded</b> durumuna cekmek icin hazirlandi.", body))
    story.append(p("Ayni akisi 10 farkli bilgisayara kurabilirsiniz. Her bilgisayarda sadece <b>STORE_ID</b>, gerekirse <b>GOOGLE_SHEET_ID</b>, <b>TEMP_DIR</b> ve <b>PCLOUD_TOKEN</b> degisir.", body))

    story.append(p("1. Gerekli Programlar", h1))
    story.append(p("Her Windows bilgisayarda su iki program kurulu olmali:", body))
    reqs = ListFlowable(
        [
            ListItem(p("Git", body)),
            ListItem(p("Python 3.10 veya ustu", body)),
        ],
        bulletType="bullet",
        leftIndent=14,
    )
    story.append(reqs)
    story.append(p("Kontrol komutlari:", body))
    story.append(p("git --version<br/>py --version", code))

    story.append(p("2. Projeyi Indir", h1))
    story.append(p("Projeyi her bilgisayarda ayni klasore klonlayin:", body))
    story.append(p("cd C:\\<br/>git clone https://github.com/yasinayaz/rugskilim-panel.git", code))
    story.append(p("Proje klasoru standart olarak su olacak:", body))
    story.append(p("C:\\rugskilim-panel", code))

    story.append(p("3. Python Bagimliliklarini Kur", h1))
    story.append(p("Ilk kurulumdan sonra bu komutu bir kez calistirin:", body))
    story.append(p("cd C:\\rugskilim-panel<br/>py -m pip install gspread google-auth httpx opencv-python numpy requests", code))

    story.append(p("4. Google Credentials Dosyasini Kopyala", h1))
    story.append(p("Service account JSON dosyasini her bilgisayarda su klasore koyun:", body))
    story.append(p("C:\\rugskilim-panel\\streamlit\\credentials.json", code))
    story.append(p("Bu dosya Git ile gelmez; manuel kopyalanir.", body))

    story.append(p("5. VDS Ayar Dosyasini Olustur", h1))
    story.append(p("Repo guncellendikten sonra su dosya gelir:", body))
    story.append(p("C:\\rugskilim-panel\\vds\\OLDNEWRUGS_env.txt", code))
    story.append(p("Bu dosyayi Not Defteri ile acip <b>Farkli Kaydet</b> secenegiyle ayni klasore <b>.env</b> olarak kaydedin.", body))
    story.append(p("Hedef dosya:", body))
    story.append(p("C:\\rugskilim-panel\\vds\\.env", code))
    story.append(p("OldNewRugs ornek icerigi:", body))
    story.append(p("STORE_ID=OldNewRugs<br/>GOOGLE_SHEET_ID=12zcGd3Ila-y_aZWCldNZUeJp-1yBrz_Uvh4Yf3U0f7o<br/>GOOGLE_CREDS_JSON=C:\\rugskilim-panel\\streamlit\\credentials.json<br/>TEMP_DIR=C:\\etsy_temp\\OldNewRugs<br/>PCLOUD_TOKEN=GERCEK_TOKEN", code))

    story.append(p("6. Gecici Indirme Klasoru", h1))
    story.append(p("Worker urunleri bu klasore indirir:", body))
    story.append(p("C:\\etsy_temp\\<STORE_ID>\\<urun_id>\\", code))
    story.append(p("OldNewRugs icin ornek:", body))
    story.append(p("C:\\etsy_temp\\OldNewRugs\\1539\\", code))
    story.append(p("Klasoru onceden olusturabilirsiniz:", body))
    story.append(p("mkdir C:\\etsy_temp<br/>mkdir C:\\etsy_temp\\OldNewRugs", code))

    story.append(p("7. Worker'i Baslat", h1))
    story.append(p("OldNewRugs bilgisayarinda personel komut yazmadan su dosyaya cift tiklayabilir:", body))
    story.append(p("C:\\rugskilim-panel\\vds\\OLDNEWRUGS_BASLAT.bat", code))
    story.append(p("Genel baslatici da mevcuttur:", body))
    story.append(p("C:\\rugskilim-panel\\vds\\baslat.bat", code))

    story.append(p("8. Streamlit ile Dogru Eslesme", h1))
    story.append(p("Worker'in urun bulabilmesi icin su uc alan ayni olmali:", body))
    table = Table(
        [
            ["Alan", "Deger"],
            ["Streamlit Hedef Magaza", "OldNewRugs"],
            ["Windows STORE_ID", "OldNewRugs"],
            ["Google Sheet sekme adi", "OldNewRugs"],
        ],
        colWidths=[5.5 * cm, 9.7 * cm],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))

    story.append(p("9. Beklenen Calisma Akisi", h1))
    story.append(p("Basarili bir urunde sirayla su adimlar gorulur:", body))
    flow = ListFlowable(
        [
            ListItem(p("Sheet'te <b>ready</b> urun bulunur", body)),
            ListItem(p("<b>downloading</b> durumuna cekilir", body)),
            ListItem(p("pCloud'dan tum gorseller indirilir", body)),
            ListItem(p("Iki adet MP4 video uretilir", body)),
            ListItem(p("Dosyalar SEO isimleriyle yeniden adlandirilir", body)),
            ListItem(p("Sheet'te <b>downloaded</b> durumuna cekilir", body)),
        ],
        bulletType="1",
        leftIndent=16,
    )
    story.append(flow)

    story.append(p("10. Sik Hatalar ve Cozumler", h1))
    story.append(p("<b>PCLOUD_TOKEN ortam degiskeni eksik</b>: `.env` dosyasinda gercek token olmali.", body))
    story.append(p("<b>Directory does not exist</b>: Sheet'teki `pcloud_klasor_id` gecersiz olabilir; urunu Streamlit'ten tekrar kuyruga atmak gerekebilir.", body))
    story.append(p("<b>httpx bulunamadi</b>: Python paketleri kurulmamis; 3. adimi tekrar calistirin.", body))
    story.append(p("<b>git pull calismiyor</b>: komut `C:\\rugskilim-panel` klasoru icinde calismali.", body))

    story.append(p("11. 10 Bilgisayara Kurulum Icin Standart", h1))
    story.append(p("Tum bilgisayarlarda ayni dizin yapisini koruyun:", body))
    story.append(p("C:\\rugskilim-panel<br/>C:\\rugskilim-panel\\streamlit\\credentials.json<br/>C:\\rugskilim-panel\\vds\\.env<br/>C:\\etsy_temp\\<STORE_ID>", code))
    story.append(p("Her yeni bilgisayarda sadece su alanlari degistirin:", body))
    multi = ListFlowable(
        [
            ListItem(p("STORE_ID", body)),
            ListItem(p("TEMP_DIR", body)),
            ListItem(p("Gerekirse GOOGLE_SHEET_ID", body)),
            ListItem(p("PCLOUD_TOKEN", body)),
        ],
        bulletType="bullet",
        leftIndent=14,
    )
    story.append(multi)

    story.append(p("12. Guncelleme Komutu", h1))
    story.append(p("Repo guncellemesi gereken tum Windows bilgisayarlarda su komut yeterli:", body))
    story.append(p("cd C:\\rugskilim-panel && git pull", code))

    doc.build(story)
    return OUTPUT


if __name__ == "__main__":
    out = build_pdf()
    print(out)
