-- Bootstrap Admin User and Organization Script
-- You can run this in DataGrip or any PostgreSQL client connected to your database.
-- 
-- This creates:
-- 1. A default organization: "Default Organization" (slug: "default")
-- 2. An admin user: "admin@example.com" with password "password"
-- 3. The membership linking the user to the organization as an administrator.

BEGIN;

-- Insert the Default Organization
-- We use a hardcoded UUID so we can easily reference it, or you could use gen_random_uuid() 
-- but doing it this way ensures we can link the user cleanly in standard SQL.
INSERT INTO organizations (
    id, 
    name, 
    slug, 
    status, 
    settings, 
    created_at, 
    updated_at
) VALUES (
    '438c379b-5017-42f6-a3fc-e0abb1d35927', 
    'Default Organization', 
    'default', 
    'active', 
    '{}'::jsonb, 
    now(), 
    now()
) ON CONFLICT (slug) DO NOTHING;

-- Insert the Admin User
-- Email: admin@example.com
-- Password: password (hashed with bcrypt via passlib)
INSERT INTO users (
    id, 
    email, 
    type, 
    password_hash, 
    created_at
) VALUES (
    '9f0019ed-ed1a-4609-a451-c7acf73e5b18', 
    'admin@example.com', 
    'human', 
    '$2b$12$Yye1jOPVSLOL5sNLaHzd.OPq0Flyrxau791ZU5ijo/Ca0zBCLs5N.', 
    now()
) ON CONFLICT (email) DO NOTHING;

-- Link User and Organization
-- Note: we use subqueries here just in case the rows already existed with different UUIDs
-- to ensure we don't fail if the script is run multiple times.
INSERT INTO users_orgs (
    user_id, 
    org_id, 
    role, 
    display_name
) VALUES (
    (SELECT id FROM users WHERE email = 'admin@example.com'),
    (SELECT id FROM organizations WHERE slug = 'default'),
    'administrator',
    'admin'
) ON CONFLICT (user_id, org_id) DO NOTHING;

COMMIT;
