// Team des crestra Kalenders verwalten (nur lokal, nutzt den service-key aus ~/.config/crestra).
//   node werkzeug/team.js hinzufuegen "Name" mail@beispiel.de   → Konto anlegen (oder vorhandenes nehmen) + freischalten
//   node werkzeug/team.js passwort mail@beispiel.de              → neues Start-Passwort
//   node werkzeug/team.js entfernen mail@beispiel.de             → Zugriff auf den Kalender entziehen (Konto bleibt)
//   node werkzeug/team.js liste
const fs = require("fs");
const crypto = require("crypto");
const h = require("os").homedir() + "/.config/crestra/";
const URL = "https://" + fs.readFileSync(h + "project-ref", "utf8").trim() + ".supabase.co";
const KEY = fs.readFileSync(h + "service-key", "utf8").trim();
const H = { apikey: KEY, Authorization: "Bearer " + KEY, "Content-Type": "application/json" };
const APP = "https://nilsc2308.github.io/crestra-kalender/";

async function api(path, opt = {}) {
  const res = await fetch(URL + path, Object.assign({}, opt, { headers: Object.assign({}, H, opt.headers) }));
  const text = await res.text();
  if (!res.ok) throw new Error(res.status + " " + text);
  return text ? JSON.parse(text) : null;
}
const neuesPasswort = () => crypto.randomBytes(9).toString("base64").replace(/[+/=]/g, "").slice(0, 12);
async function userByMail(mail) {
  const { users } = await api("/auth/v1/admin/users?per_page=1000");
  return users.find((u) => u.email === mail.trim().toLowerCase());
}

const [cmd, a, b] = process.argv.slice(2);
(async () => {
  if (cmd === "hinzufuegen") {
    const name = a, mail = (b || "").trim().toLowerCase();
    if (!name || !mail.includes("@")) throw new Error('Aufruf: node werkzeug/team.js hinzufuegen "Name" mail@beispiel.de');
    let u = await userByMail(mail), pw = null;
    if (!u) {
      pw = neuesPasswort();
      u = await api("/auth/v1/admin/users", { method: "POST", body: JSON.stringify({ email: mail, password: pw, email_confirm: true }) });
    }
    await api("/rest/v1/kalender_team?on_conflict=user_id", { method: "POST", headers: { Prefer: "resolution=merge-duplicates,return=minimal" },
      body: JSON.stringify({ user_id: u.id, name }) });
    console.log(`Freigeschaltet: ${name} <${mail}>` + (pw ? `\nStart-Passwort: ${pw}` : "\n(Konto gab es schon – bisheriges Passwort gilt)") + `\nApp: ${APP}`);
  } else if (cmd === "passwort") {
    const u = await userByMail(a || "");
    if (!u) throw new Error("Kein Konto mit dieser E-Mail");
    const pw = neuesPasswort();
    await api("/auth/v1/admin/users/" + u.id, { method: "PUT", body: JSON.stringify({ password: pw }) });
    console.log(`Neues Passwort für ${u.email}: ${pw}`);
  } else if (cmd === "entfernen") {
    const u = await userByMail(a || "");
    if (!u) throw new Error("Kein Konto mit dieser E-Mail");
    await api("/rest/v1/kalender_team?user_id=eq." + u.id, { method: "DELETE" });
    console.log(`Kein Kalender-Zugriff mehr: ${u.email}`);
  } else if (cmd === "liste") {
    const team = await api("/rest/v1/kalender_team?select=user_id,name");
    const { users } = await api("/auth/v1/admin/users?per_page=1000");
    team.forEach((t) => console.log(`${t.name} <${(users.find((u) => u.id === t.user_id) || {}).email || "?"}>`));
  } else {
    console.log('Befehle: hinzufuegen "Name" mail | passwort mail | entfernen mail | liste');
  }
})().catch((e) => { console.error("FEHLER:", e.message); process.exit(1); });
