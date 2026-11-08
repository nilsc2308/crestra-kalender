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
import email, imaplib, json, re, subprocess, sys, urllib.request, urllib.error
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
                    if name.isupper():
                        name = name.title()
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


def sb(methode, pfad, daten=None):
    req = urllib.request.Request(SB_URL + "/rest/v1/" + pfad, method=methode,
                                 data=json.dumps(daten).encode() if daten is not None else None,
                                 headers={"apikey": SB_KEY, "Authorization": "Bearer " + SB_KEY,
                                          "Content-Type": "application/json", "Prefer": "return=representation"})
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


if __name__ == "__main__":
    m = anmelden()
    print("Mails sortieren" + (" (Probe)" if PROBE else ""))
    sortieren(m)
    print("Termine aus Indeed-Mails")
    termine = termine_lesen(m)
    m.logout()
    try:
        eintragen(termine)
    except urllib.error.URLError as e:
        sys.exit(f"Supabase nicht erreichbar ({e}). Ist das Projekt pausiert?")
