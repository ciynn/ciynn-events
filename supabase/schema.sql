-- Chadwick Institute Young Nuclear Network: members' area database (Supabase / Postgres).
-- Run once in the Supabase dashboard: SQL Editor > New query > paste this file > Run.
-- Safe to run again: it only creates what is missing and replaces the policies and functions.
--
-- Who can see what (row-level security, enforced by the database itself):
--   * a member can read and change only their own profile, and delete their own account;
--   * signed-in members can read member exclusives; nobody else can;
--   * signed-in members can see the directory cards of members who chose to be listed (name, status,
--     department, research area, skills, mentoring) and nothing else about them;
--   * the committee sees everything through the Supabase dashboard (that login never touches the website).

create extension if not exists citext;

-- ------------------------------------------------------------------ profiles
create table if not exists public.profiles (
  id                uuid primary key references auth.users (id) on delete cascade,
  username          citext unique not null check (username ~ '^[A-Za-z0-9_.-]{3,30}$'),
  full_name         text not null check (char_length(full_name) between 1 and 120),
  pronouns          text check (char_length(pronouns) <= 30),
  -- study and work
  status            text check (status in ('undergraduate','msc','pgr','postdoc','staff','industry','other')),
  department        text check (char_length(department) <= 120),
  organisation      text check (char_length(organisation) <= 120),
  year_of_study     text check (char_length(year_of_study) <= 30),
  group_or_supervisor text check (char_length(group_or_supervisor) <= 120),
  expected_finish   text check (char_length(expected_finish) <= 30),
  -- research and interests
  research_area     text check (char_length(research_area) <= 200),
  bio               text check (char_length(bio) <= 1200),
  interests         text[] not null default '{}',
  travel            text check (travel in ('anywhere','europe','uk','online')),
  orcid             text check (orcid ~ '^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$'),
  linkedin          text check (linkedin ~ '^https://([a-z]+\.)?linkedin\.com/'),
  website           text check (website ~ '^https://'),
  -- mentoring and skills
  skills            text[] not null default '{}',
  mentoring         text check (mentoring in ('none','want','offer','both')),
  career_goals      text check (char_length(career_goals) <= 800),
  professional_bodies text[] not null default '{}',
  -- events
  email_updates     text[] not null default '{events}',
  heard_about_us    text check (char_length(heard_about_us) <= 120),
  -- health or belief data (dietary, accessibility): only with its own explicit consent
  needs_consent     boolean not null default false,
  dietary           text check (char_length(dietary) <= 300),
  accessibility     text check (char_length(accessibility) <= 500),
  -- directory and the For you model
  in_directory      boolean not null default false,
  for_you           jsonb not null default '{}'::jsonb check (pg_column_size(for_you) < 60000),
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  constraint needs_need_consent check (needs_consent or (dietary is null and accessibility is null))
);

alter table public.profiles enable row level security;

drop policy if exists "read own profile" on public.profiles;
drop policy if exists "update own profile" on public.profiles;
create policy "read own profile"   on public.profiles for select to authenticated using (id = auth.uid());
create policy "update own profile" on public.profiles for update to authenticated using (id = auth.uid()) with check (id = auth.uid());
-- no insert policy: profiles are made by the trigger below when an account is created

create or replace function public.touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at := now(); return new; end $$;
drop trigger if exists profiles_touch on public.profiles;
create trigger profiles_touch before update on public.profiles for each row execute function public.touch_updated_at();

-- a new account gets its profile from the sign-up form's username and name
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, username, full_name)
  values (new.id,
          coalesce(new.raw_user_meta_data ->> 'username', 'member_' || substr(new.id::text, 1, 8)),
          coalesce(new.raw_user_meta_data ->> 'full_name', ''));
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users for each row execute function public.handle_new_user();

-- is a username free? (lets the sign-up form say so before submitting; reveals nothing else)
create or replace function public.username_available(name text) returns boolean
language sql security definer set search_path = public stable as $$
  select not exists (select 1 from public.profiles where username = name::citext)
$$;
grant execute on function public.username_available(text) to anon, authenticated;

-- a member can delete their own account (and with it their profile)
create or replace function public.delete_my_account() returns void
language plpgsql security definer set search_path = public as $$
begin
  delete from auth.users where id = auth.uid();
end $$;
revoke all on function public.delete_my_account() from public, anon;
grant execute on function public.delete_my_account() to authenticated;

-- the members' directory: only members who opted in, and only these columns
create or replace view public.directory with (security_invoker = false) as
  select username, full_name, pronouns, status, department, organisation, research_area, skills, mentoring, linkedin, orcid
  from public.profiles where in_directory;
revoke all on public.directory from public, anon;
grant select on public.directory to authenticated;

-- ------------------------------------------------------------------ member exclusives
create table if not exists public.exclusives (
  id            bigint generated always as identity primary key,
  title         text not null,
  kind          text not null default 'Resource',      -- e.g. Recording, Slides, Opportunity, Discount, Resource
  summary       text,
  body          text,                                  -- plain text or simple Markdown
  link          text,                                  -- an outside link, or
  file_path     text,                                  -- a file in the private 'exclusives' storage bucket
  published_at  timestamptz not null default now(),
  expires_at    timestamptz
);
alter table public.exclusives enable row level security;
drop policy if exists "members read exclusives" on public.exclusives;
create policy "members read exclusives" on public.exclusives for select to authenticated
  using (published_at <= now() and (expires_at is null or expires_at > now()));
-- only the committee adds them, in the dashboard (Table Editor > exclusives > Insert row)

-- files for exclusives: a private bucket only signed-in members can read
insert into storage.buckets (id, name, public) values ('exclusives', 'exclusives', false) on conflict (id) do nothing;
drop policy if exists "members read exclusive files" on storage.objects;
create policy "members read exclusive files" on storage.objects for select to authenticated using (bucket_id = 'exclusives');
