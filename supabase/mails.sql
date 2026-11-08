-- Spiegel des Postfachs info@crestra.de für die Kalender-App (nur Team, nur lesen + Status).
-- Befüllt von werkzeug/mail_sync.py (service-key). Die App setzt nur gelesen/erledigt.
create table if not exists public.mails (
  id           text        primary key,           -- sha1 der Message-ID
  ordner       text        not null,
  von_name     text        not null default '',
  von_adresse  text        not null default '',
  antwort_an   text        not null default '',
  betreff      text        not null default '',
  datum        timestamptz not null,
  vorschau     text        not null default '',
  text         text        not null default '',
  kategorie    text        not null default 'sonstiges',
  wichtig      boolean     not null default false,
  gelesen      boolean     not null default false,
  erledigt     boolean     not null default false,
  bearbeitet_von uuid,
  updated_at   timestamptz not null default now()
);
create index if not exists mails_datum on public.mails (datum desc);
alter table public.mails enable row level security;
drop policy if exists "team liest mails" on public.mails;
drop policy if exists "team markiert mails" on public.mails;
create policy "team liest mails" on public.mails for select to authenticated using (public.ist_kalender_team());
create policy "team markiert mails" on public.mails for update to authenticated using (public.ist_kalender_team()) with check (public.ist_kalender_team());
revoke update on public.mails from authenticated;
grant update (gelesen, erledigt, bearbeitet_von) on public.mails to authenticated;
do $$ begin
  alter publication supabase_realtime add table public.mails;
exception when duplicate_object then null; end $$;
