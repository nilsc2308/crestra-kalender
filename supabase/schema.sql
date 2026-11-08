-- crestra Kalender – gemeinsamer Terminkalender für das crestra-Team (Supabase / Postgres)
-- Wer in kalender_team steht, sieht und bearbeitet alle Termine. Alle anderen Konten
-- (z. B. Vertriebler aus dem Kundenboard) sehen hier nichts.

create table if not exists public.kalender_team (
  user_id    uuid        primary key references auth.users(id) on delete cascade,
  name       text        not null default '',
  farbe      text        not null default '',
  created_at timestamptz not null default now()
);
alter table public.kalender_team enable row level security;

create or replace function public.ist_kalender_team()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.kalender_team where user_id = auth.uid());
$$;
grant execute on function public.ist_kalender_team() to authenticated;

drop policy if exists "team lesen" on public.kalender_team;
create policy "team lesen" on public.kalender_team for select to authenticated using (public.ist_kalender_team());

create table if not exists public.termine (
  id          uuid        primary key default gen_random_uuid(),
  titel       text        not null,
  art         text        not null default 'termin' check (art in ('interview', 'kunde', 'intern', 'termin')),
  beginn      timestamptz not null,
  ende        timestamptz not null,
  ganztag     boolean     not null default false,
  person      text        not null default '',
  telefon     text        not null default '',
  ort         text        not null default '',
  notiz       text        not null default '',
  status      text        not null default 'geplant' check (status in ('geplant', 'erledigt', 'abgesagt')),
  zustaendig  uuid        references public.kalender_team(user_id) on delete set null,
  quelle      text        not null default 'manuell',
  quelle_id   text        unique,
  erstellt_von uuid       default auth.uid(),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  check (ende >= beginn)
);
create index if not exists termine_beginn on public.termine (beginn);
alter table public.termine enable row level security;

drop policy if exists "team liest termine" on public.termine;
drop policy if exists "team schreibt termine" on public.termine;
drop policy if exists "team ändert termine" on public.termine;
drop policy if exists "team löscht termine" on public.termine;
create policy "team liest termine"   on public.termine for select to authenticated using (public.ist_kalender_team());
create policy "team schreibt termine" on public.termine for insert to authenticated with check (public.ist_kalender_team());
create policy "team ändert termine"  on public.termine for update to authenticated using (public.ist_kalender_team()) with check (public.ist_kalender_team());
create policy "team löscht termine"  on public.termine for delete to authenticated using (public.ist_kalender_team());

create or replace function public.termine_touch() returns trigger language plpgsql as $$
begin new.updated_at := now(); return new; end $$;
drop trigger if exists termine_touch on public.termine;
create trigger termine_touch before update on public.termine for each row execute function public.termine_touch();

do $$ begin
  alter publication supabase_realtime add table public.termine;
exception when duplicate_object then null; end $$;
