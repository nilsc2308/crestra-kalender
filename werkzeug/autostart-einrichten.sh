#!/bin/zsh
# Richtet ein, dass werkzeug/mail_sync.py alle 10 Minuten läuft (solange der Mac an ist).
# Abschalten: launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/de.crestra.mailsync.plist
DIR="${0:A:h}"
P="$HOME/Library/LaunchAgents/de.crestra.mailsync.plist"
mkdir -p "$HOME/Library/Logs/crestra" "$HOME/Library/LaunchAgents"
cat > "$P" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>de.crestra.mailsync</string>
  <key>ProgramArguments</key><array><string>/usr/bin/python3</string><string>-I</string><string>$DIR/mail_sync.py</string></array>
  <key>StartInterval</key><integer>600</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/crestra/mailsync.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/crestra/mailsync.log</string>
</dict></plist>
PL
launchctl bootout gui/$(id -u) "$P" 2>/dev/null
launchctl bootstrap gui/$(id -u) "$P" && echo "✓ Mail-Abgleich läuft jetzt alle 10 Minuten."
