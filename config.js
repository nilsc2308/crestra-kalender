// Zugangsdaten zur Supabase-Datenbank. Der „anon“-Schlüssel ist öffentlich gedacht:
// Er erlaubt nur, was die Sicherheitsregeln in supabase/schema.sql zulassen
// (jeder angemeldete Nutzer sieht ausschließlich seine eigenen Daten).
export const SUPABASE_URL = "https://mvcwhvntbvnldqimjiki.supabase.co";
export const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im12Y3dodm50YnZubGRxaW1qaWtpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTA2MDE3MzAsImV4cCI6MjEwNjE3NzczMH0._Ar5wQHzxZInIL9VhbtEFjLjb7VxZ9WishHm6lGJtFo";

// Konten: Nils + Kollegen (Tabelle kalender_team). Neue Konten: node werkzeug/team.js
