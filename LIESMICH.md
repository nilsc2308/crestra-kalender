# crestra Kalender

Gemeinsamer Terminkalender für Nils und Kollegen. Geplante Adresse: https://nilsc2308.github.io/crestra-kalender/
(auf dem iPhone in Safari öffnen → Teilen → „Zum Home-Bildschirm“).

- Daten: Supabase-Projekt „claude“ (wie das Kundenboard), Tabellen `termine` + `kalender_team` (supabase/schema.sql).
  Nur wer in `kalender_team` steht, sieht die Termine.
- Kollegen freischalten: `node werkzeug/team.js hinzufuegen "Name" mail@beispiel.de` (gibt Start-Passwort aus).
- Indeed-Termine aus info@crestra.de holen + Mails sortieren: `python3 -I werkzeug/mail_sync.py` (`--probe` = nur anzeigen).
- Veröffentlichen: git push (GitHub Pages, Konto nilsc2308).
