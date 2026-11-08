#!/usr/bin/env python3
"""Mail-Abgleich für den crestra Kalender.

1. Sortiert neue Mails im Posteingang von info@crestra.de in Ordner (nichts wird gelöscht).
2. Liest die Kalender-Einladungen (.ics) von Indeed und trägt die Vorstellungsgespräche
   in die Supabase-Tabelle `termine` ein. Verschiebungen und Absagen werden übernommen.
   Was im Kalender von Hand geändert wurde (Status erledigt, Zuständig, Notiz, Titel), bleibt.

Aufruf:  python3 -I werkzeug/mail_sync.py           (sortieren + Termine)
         python3 -I werkzeug/mail_sync.py --probe   (nur anzeigen, nichts ändern)

Zugang: Mail-Passwort im macOS-Schlüsselbund (imap.strato.de), Supabase-service-key in ~/.config/crestra.
"""
import email, html, imaplib, json, re, subprocess, sys, urllib.request, urllib.error
from datetime import datetime
from email.header import decode_header, make_header
from pathlib import Path
from zoneinfo import ZoneInfo

ADRESSE = "info@crestra.de"
PROBE = "--probe" in sys.argv
CFG = Path.home() / ".config/crestra"
SB_URL = "https://" + (CFG / "project-ref").read_text().strip() + ".supabase.co"
SB_KEY = (CFG / "service-key").read_text().strip()
BERLIN = ZoneInfo("Europe/Berlin")

SPAM = ["bizaudit.com", "alfareviews.com", "de-ltd.cc", "kanzlei-rheinknie.de", "gerloff-partner.com", "akinrolesamuel123@icloud.com"]


def ordner_fuer(absender, betreff):
    a = email.utils.parseaddr(absender)[1].lower()
    if any(x in a for x in SPAM):
        return "Spam"
    if a.endswith("indeedemail.com") or a == "heinrichrobert88@gmail.com":
        return "Bewerbungen"
    if "indeed" in a:
        if re.search(r"Vorstellungsgespr|Telefongespr|Videogespr", betreff):
            return "Bewerbungen.Termine"
        return "Indeed"
    if any(x in a for x in ["freelancermap", "kleinanzeigen", "resend.com"]):
        return "Plattformen"
    if "businessprofile-noreply@google" in a:
        return "Google Unternehmensprofil"
    if a == "noreply@github.com":
        return "GitHub"
    return None  # bleibt im Posteingang


def kopf(msg, feld):
    return str(make_header(decode_header(msg.get(feld, "") or ""))).strip()


def q(name):
    return '"' + name + '"'


def anmelden():
    pw = subprocess.run(["security", "find-internet-password", "-a", ADRESSE, "-s", "imap.strato.de", "-w"],
                        capture_output=True, text=True).stdout.strip()
    if not pw:
        sys.exit("Kein Mail-Passwort im Schlüsselbund (imap.strato.de / info@crestra.de).")
    m = imaplib.IMAP4_SSL("imap.strato.de", 993)
    m.login(ADRESSE, pw)
    return m


def sortieren(m):
    m.select("INBOX", readonly=PROBE)
    _, d = m.uid("SEARCH", None, "ALL")
    plan = {}
    for u in d[0].split():
        _, r = m.uid("FETCH", u, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
        h = email.message_from_bytes(r[0][1])
        ziel = ordner_fuer(kopf(h, "From"), kopf(h, "Subject"))
        if ziel:
            plan.setdefault(ziel, []).append(u.decode())
    for ziel, uids in plan.items():
        print(f"  {len(uids):3d} → {ziel}")
        if not PROBE:
            if ziel != "Spam":
                m.create(q(ziel))  # existiert er schon, meldet der Server nur einen harmlosen Fehler
            m.uid("MOVE", ",".join(uids), q(ziel))
    if not plan:
        print("  nichts Neues zu sortieren")


def ics_aus(msg):
    for p in msg.walk():
        if p.get_content_type() in ("text/calendar", "application/ics"):
            yield p.get_payload(decode=True).decode("utf-8", "ignore").replace("\r\n ", "").replace("\n ", "")


def text_aus(msg):
    for p in msg.walk():
        if p.get_content_type() == "text/plain":
            return p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "ignore")
    return ""


def zeit(wert, tz):
    dt = datetime.strptime(wert[:15], "%Y%m%dT%H%M%S")
    if wert.endswith("Z"):
        return dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.replace(tzinfo=ZoneInfo(tz) if tz else BERLIN)


def termine_lesen(m):
    """Letzter Stand je Einladung (UID) aus allen Indeed-Mails."""
    stand = {}
    for box in ["INBOX", "Bewerbungen.Termine"]:
        if m.select(q(box), readonly=True)[0] != "OK":
            continue
        _, d = m.search(None, "FROM", "indeed")
        for i in d[0].split():
            _, r = m.fetch(i, "(BODY.PEEK[])")
            msg = email.message_from_bytes(r[0][1])
            gesendet = email.utils.parsedate_to_datetime(msg.get("Date"))
            for c in ics_aus(msg):
                methode = (re.search(r"^METHOD:(.*)$", c, re.M) or [None, ""])[1].strip()
                for v in re.findall(r"(?s)BEGIN:VEVENT(.*?)END:VEVENT", c):
                    g = lambda k: (re.search(rf"^{k}[^:\n]*:(.*)$", v, re.M) or [None, ""])[1].strip()
                    tz = (re.search(r"DTSTART;TZID=([^:]*)", v) or [None, ""])[1]
                    uid = g("UID")
                    titel = g("SUMMARY")
                    name = (re.search(r"interview with (.*?) for", titel) or [None, titel])[1].strip()
                    name = " ".join(w.title() if w.isupper() and len(w) > 2 else w for w in name.split())
                    tel = re.search(r"\[(\+?\d[\d ]{6,})\]", re.sub(r"\s+", " ", text_aus(msg)))
                    eintrag = dict(
                        quelle_id="indeed:" + uid, gesendet=gesendet, abgesagt=(methode == "CANCEL"),
                        art="interview", person=name,
                        titel=("Video" if titel.startswith("Video") else "Telefon") + "-Interview " + name,
                        beginn=zeit(g("DTSTART"), tz).isoformat(), ende=zeit(g("DTEND"), tz).isoformat(),
                        telefon=tel.group(1) if tel else "", ort=g("LOCATION") if titel.startswith("Video") else "",
                    )
                    alt = stand.get(eintrag["quelle_id"])
                    if not alt or alt["gesendet"] <= gesendet:
                        if alt and eintrag["abgesagt"] and not eintrag["telefon"]:
                            eintrag["telefon"] = alt["telefon"]
                        stand[eintrag["quelle_id"]] = eintrag
    return list(stand.values())


def sb(methode, pfad, daten=None, prefer="return=representation"):
    req = urllib.request.Request(SB_URL + "/rest/v1/" + pfad, method=methode,
                                 data=json.dumps(daten).encode() if daten is not None else None,
                                 headers={"apikey": SB_KEY, "Authorization": "Bearer " + SB_KEY,
                                          "Content-Type": "application/json", "Prefer": prefer})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return json.loads(body) if body else None


def eintragen(termine):
    vorhanden = {t["quelle_id"]: t for t in sb("GET", "termine?select=id,quelle_id,status,beginn,ende&quelle=eq.indeed")}
    neu = geaendert = 0
    for t in termine:
        hinweis = "Vorstellungsgespräch über Indeed (Selbstständiger Vertriebsmitarbeiter B2B)."
        if t["telefon"]:
            hinweis += " Zur Startzeit anrufen."
        alt = vorhanden.get(t["quelle_id"])
        if not alt:
            if t["abgesagt"] and datetime.fromisoformat(t["beginn"]) < datetime.now(BERLIN):
                continue  # alte, abgesagte Einladungen nicht nachtragen
            zeile = dict(titel=t["titel"], art="interview", beginn=t["beginn"], ende=t["ende"], person=t["person"],
                         telefon=t["telefon"], ort=t["ort"], notiz=hinweis, quelle="indeed", quelle_id=t["quelle_id"],
                         status="abgesagt" if t["abgesagt"] else "geplant", erstellt_von=None)
            print(f"  neu: {t['beginn'][:16]} {t['titel']}{' (abgesagt)' if t['abgesagt'] else ''}")
            if not PROBE:
                sb("POST", "termine", zeile)
            neu += 1
            continue
        patch = {}
        if datetime.fromisoformat(alt["beginn"]) != datetime.fromisoformat(t["beginn"]) or \
           datetime.fromisoformat(alt["ende"]) != datetime.fromisoformat(t["ende"]):
            patch.update(beginn=t["beginn"], ende=t["ende"])
        if t["abgesagt"] and alt["status"] != "abgesagt":
            patch["status"] = "abgesagt"
        if patch:
            print(f"  geändert: {t['titel']} {patch}")
            if not PROBE:
                sb("PATCH", "termine?id=eq." + alt["id"], patch)
            geaendert += 1
    print(f"  {neu} neu, {geaendert} geändert")


# ---------- Postfach-Spiegel für die App ----------

SPIEGEL_ORDNER = ["INBOX", "Bewerbungen", "Indeed", "Plattformen", "Google Unternehmensprofil", "GitHub"]
TAGE = 45
WICHTIGE_WOERTER = re.compile(r"rechnung|zahlung|mahnung|vertrag|kündig|angebot|auftrag|anfrage|termin|rückruf|frage", re.I)


def roh_text(msg):
    teile_plain, teile_html = [], []
    for p in msg.walk():
        if p.get_content_maintype() == "multipart" or p.get_filename():
            continue
        try:
            inhalt = p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "ignore")
        except Exception:
            continue
        if p.get_content_type() == "text/plain":
            teile_plain.append(inhalt)
        elif p.get_content_type() == "text/html":
            teile_html.append(inhalt)
    if teile_plain:
        t = "\n".join(teile_plain)
    else:
        h = "\n".join(teile_html)
        h = re.sub(r"(?is)<(style|script|head).*?</\1>", "", h)
        h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h\d>", "\n", h)
        t = html.unescape(re.sub(r"<[^>]+>", " ", h))
    t = re.sub("[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180e\u200b-\u200f\u2028-\u202f\u2060-\u206f\ufeff]", "", t)
    t = re.sub("[ \t\u00a0]+", " ", t)
    t = re.sub(r"(?m)^ +| +$", "", t)
    indeed = re.search(r"Sie haben eine neue Nachricht von [^\n]+\n+(.*?)\n+(?:Selbstst\u00e4ndiger|Antworten\b)", t, re.S)
    if indeed:
        return indeed.group(1).strip()[:8000]
    t = re.sub(r"\n\s*\n\s*(\n\s*)+", "\n\n", t).strip()
    # zitierte Vorgänger-Mails abschneiden
    t = re.split(r"\n(?:Am .{5,80} schrieb .{0,80}:|On .{5,80} wrote:|-{3,} ?(?:Original|Ursprüngliche).{0,30}-{3,}|Von: .+\nGesendet: )", t)[0]
    return t.strip()[:8000]


def einordnen(ordner, adresse, betreff, kopf_liste):
    """→ (kategorie, wichtig)"""
    a = adresse.lower()
    if ordner == "Bewerbungen":
        if re.search(r"Neue Bewerbung", betreff):
            return "bewerbung", False  # Hinweis auf neue Bewerbung – steht in der Rubrik „Neue Bewerbungen“
        return "nachricht", True     # Bewerber hat geschrieben → braucht Antwort
    if ordner in ("Indeed", "Plattformen", "Google Unternehmensprofil", "GitHub"):
        return "benachrichtigung", bool(re.search(r"zahlung|rechnung|abgelehnt|gesperrt|appeal", betreff, re.I)) and "indeed" in a
    # Posteingang: alles, was keiner Regel zugeordnet wurde
    if re.search(r"rechnung|zahlung|mahnung|invoice|beleg", betreff, re.I):
        return "rechnung", True
    if kopf_liste or re.search(r"no-?reply|newsletter|news@|info@.*mailing", a):
        return "benachrichtigung", False
    return "kontakt", True


def mails_spiegeln(m):
    import hashlib
    seit = (datetime.now(BERLIN).date().toordinal() - TAGE)
    seit_imap = datetime.fromordinal(seit).strftime("%d-%b-%Y")
    zeilen = []
    for box in SPIEGEL_ORDNER:
        if m.select(q(box), readonly=True)[0] != "OK":
            continue
        _, d = m.search(None, "SINCE", seit_imap)
        for i in d[0].split():
            _, r = m.fetch(i, "(BODY.PEEK[])")
            msg = email.message_from_bytes(r[0][1])
            mid = (msg.get("Message-ID") or "").strip() or (kopf(msg, "From") + kopf(msg, "Date") + kopf(msg, "Subject"))
            name, adr = email.utils.parseaddr(kopf(msg, "From"))
            reply = email.utils.parseaddr(kopf(msg, "Reply-To"))[1] or adr
            betreff = re.sub(r"\s+", " ", kopf(msg, "Subject"))
            try:
                datum = email.utils.parsedate_to_datetime(msg.get("Date")).isoformat()
            except Exception:
                continue
            text = roh_text(msg)
            kat, wichtig = einordnen(box, adr, betreff, bool(msg.get("List-Unsubscribe")) and box == "INBOX")
            zeilen.append(dict(
                id=hashlib.sha1(mid.encode()).hexdigest(), ordner="Posteingang" if box == "INBOX" else box,
                von_name=name or adr, von_adresse=adr, antwort_an=reply, betreff=betreff or "(ohne Betreff)",
                datum=datum, vorschau=re.sub(r"\s+", " ", text)[:220], text=text, kategorie=kat, wichtig=wichtig))
    if PROBE:
        for z in sorted(zeilen, key=lambda z: z["datum"])[-15:]:
            print(f"  {'★' if z['wichtig'] else ' '} {z['kategorie']:16} {z['von_name'][:28]:28} {z['betreff'][:60]}")
        print(f"  {len(zeilen)} Mails, davon {sum(z['wichtig'] for z in zeilen)} wichtig")
        return
    eindeutig = {z["id"]: z for z in zeilen}
    zeilen = list(eindeutig.values())
    for k in range(0, len(zeilen), 100):
        sb("POST", "mails?on_conflict=id", zeilen[k:k + 100], prefer="resolution=merge-duplicates,return=minimal")
    print(f"  {len(zeilen)} Mails gespiegelt, davon {sum(z['wichtig'] for z in zeilen)} wichtig")


if __name__ == "__main__":
    m = anmelden()
    print("Mails sortieren" + (" (Probe)" if PROBE else ""))
    sortieren(m)
    print("Termine aus Indeed-Mails")
    termine = termine_lesen(m)
    print("Postfach für die App spiegeln")
    try:
        mails_spiegeln(m)
        m.logout()
        eintragen(termine)
    except urllib.error.URLError as e:
        sys.exit(f"Supabase nicht erreichbar ({e}). Ist das Projekt pausiert?")
