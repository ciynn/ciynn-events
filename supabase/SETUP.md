# Switching on member accounts (about 10 minutes, once)

The website is ready; it needs a free Supabase project to hold the accounts. Do this signed in as the
network (ChadwickInstituteNetwork@outlook.com), so the project belongs to the network, not to one person.

## 1. Create the project

1. Go to https://supabase.com and choose **Start your project**. Sign up with the network email.
2. Create an **organisation** called "Chadwick Institute Young Nuclear Network" (Free plan).
3. Create a **project**:
   - Name: `ciynn-members`
   - Database password: choose a long one and keep it in the committee's password manager (the website never uses it)
   - Region: **West Europe (London)**
4. Wait a minute or two while it starts.

## 2. Make the database (one paste)

1. In the project, open **SQL Editor** > **New query**.
2. Paste the whole of `supabase/schema.sql` from this folder and choose **Run**. It should say "Success. No rows returned".

## 3. Sign-in settings

1. **Authentication > URL Configuration**
   - Site URL: `https://ciynn.github.io/ciynn-events/members.html`
   - Redirect URLs: add `https://ciynn.github.io/ciynn-events/members.html`
2. **Authentication > Providers > Email**: keep **Confirm email** on. Set the minimum password length to **10**.
3. **Authentication > Emails** (optional now, needed before a big launch): Supabase's built-in email service
   only sends a few emails an hour, enough for testing. Before advertising accounts widely, set up custom SMTP
   (Authentication > Emails > SMTP Settings) with a free sender such as Brevo (300 emails a day), so confirmation
   and password emails come from the network.

## 4. Connect the website

1. **Project Settings > API**: copy the **Project URL** and the **anon public** key.
   (The anon key is designed to be public: the database rules in `schema.sql` decide what it can do. Never copy
   the `service_role` key anywhere.)
2. Paste them into `site.json`:

   ```json
   "supabase_url": "https://xxxxxxxx.supabase.co",
   "supabase_anon_key": "eyJ..."
   ```
3. Push (or ask Claude to). The site rebuilds in about a minute and the Members page switches on.

## Running it

- **Member exclusives**: Table Editor > `exclusives` > Insert row. Fill in `title`, `kind` (e.g. Recording, Slides,
  Opportunity), `summary`, and either `link` (https://...) or `file_path`. For a file, upload it first under
  Storage > `exclusives`, and use its name as `file_path`. Set `expires_at` to take it down automatically.
- **Seeing members**: Table Editor > `profiles` (only committee members with a Supabase login can see this). Export
  to CSV for mailings, and only use the columns the email needs.
- **Committee access**: add other committee members under Organisation > Team, each with their own login.
- **Keeping to the privacy notice**: once a year, delete accounts unused for three years
  (Authentication > Users, sort by last sign-in), and remove dietary and access details after an event if they are
  no longer needed.
- **If something goes wrong**: Authentication > Users lets you resend confirmation emails or delete an account.
