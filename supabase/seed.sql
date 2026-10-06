-- Kummo demo seed data
--
-- Locally: applied automatically by `supabase db reset` ([db.seed] in config.toml),
-- after the CLI migrations have created the kummo schema.
--
-- Hosted: by hand, pasted into the dashboard SQL editor. There is no command for it on
-- purpose -- see "Seed data" in supabase/README.md.
--
-- The DELETEs below are what make this re-runnable, and are also why it must never be
-- applied to an environment holding data worth keeping: they clear all three tables
-- before re-inserting the fixtures.

-- Idempotent: the rows below carry fixed UUIDs, so clear them first rather than
-- failing on a second run. DELETE, not TRUNCATE — the foreign keys below are
-- unqualified and TRUNCATE would need CASCADE.
DELETE FROM kummo.activities;
DELETE FROM kummo.clients;
DELETE FROM kummo.vendors;

-- =============================================================================
-- Vendors (10 Berlin-based providers)
-- =============================================================================
INSERT INTO kummo.vendors (
  id, name, address, latitude, longitude, phone, email, website, activity_type, picture
) VALUES

('a1000000-0000-0000-0000-000000000001',
 'Kreativwerkstatt Kreuzberg',
 'Oranienstraße 45, 10969 Berlin',
 52.5029425,
 13.4142022,
 '+49 30 12345678',
 'info@kreativwerkstatt-kreuzberg.de',
 'https://kreativwerkstatt-kreuzberg.de',
 ARRAY['kunst','workshop'],
 'https://images.unsplash.com/photo-1513364776144-60967b0f800f?w=600'),

('a1000000-0000-0000-0000-000000000002',
 'Tierpark Berlin',
 'Am Tierpark 125, 10319 Berlin',
 52.504132,
 13.523214,
 '+49 30 511880',
 'info@tierpark-berlin.de',
 'https://tierpark-berlin.de',
 ARRAY['natur','tier'],
 'https://images.unsplash.com/photo-1534567153574-2b12153a87f0?w=600'),

('a1000000-0000-0000-0000-000000000003',
 'Musikschule Pankow',
 'Schönhauser Allee 80, 10439 Berlin',
 52.549243,
 13.4155955,
 '+49 30 44556677',
 'hello@musikschule-pankow.de',
 'https://musikschule-pankow.de',
 ARRAY['musik','kultur'],
 'https://images.unsplash.com/photo-1511379938547-c1f69419868d?w=600'),

('a1000000-0000-0000-0000-000000000004',
 'Sportpark Neukölln',
 'Karl-Marx-Straße 231, 12043 Berlin',
 52.4686178,
 13.442591,
 '+49 30 66778899',
 'info@sportpark-neukoelln.de',
 'https://sportpark-neukoelln.de',
 ARRAY['sport','fitness'],
 'https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=600'),

('a1000000-0000-0000-0000-000000000005',
 'Naturwerkstatt Grunewald',
 'Hüttenweg 100, 14195 Berlin',
 52.4672167,
 13.2615891,
 '+49 30 33445566',
 'kontakt@naturwerkstatt-grunewald.de',
 'https://naturwerkstatt-grunewald.de',
 ARRAY['natur','outdoor'],
 'https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=600'),

('a1000000-0000-0000-0000-000000000006',
 'Kinderkochstudio Mitte',
 'Torstraße 120, 10119 Berlin',
 52.5295325,
 13.4019364,
 '+49 30 22334455',
 'kochen@kinderkochstudio-mitte.de',
 'https://kinderkochstudio-mitte.de',
 ARRAY['kochen','workshop'],
 'https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=600'),

('a1000000-0000-0000-0000-000000000007',
 'Theater Liliput',
 'Kastanienallee 77, 10435 Berlin',
 52.5364741,
 13.4078031,
 '+49 30 99887766',
 'info@theater-liliput.de',
 'https://theater-liliput.de',
 ARRAY['theater','kultur'],
 'https://images.unsplash.com/photo-1503095396549-807759245b35?w=600'),

('a1000000-0000-0000-0000-000000000008',
 'Forscherwerkstatt Charlottenburg',
 'Kantstraße 150, 10623 Berlin',
 52.5055102,
 13.3249082,
 '+49 30 55667788',
 'forschen@forscherwerkstatt-charlottenburg.de',
 'https://forscherwerkstatt-charlottenburg.de',
 ARRAY['wissenschaft','bildung'],
 'https://images.unsplash.com/photo-1532094349884-543bc11b234d?w=600'),

('a1000000-0000-0000-0000-000000000009',
 'Schwimmakademie Spandau',
 'Wilhelmstraße 45, 13585 Berlin',
 52.5118093,
 13.3836264,
 '+49 30 11223344',
 'schwimmen@schwimmakademie-spandau.de',
 'https://schwimmakademie-spandau.de',
 ARRAY['sport','schwimmen'],
 'https://images.unsplash.com/photo-1530549387789-4c1017266635?w=600'),

('a1000000-0000-0000-0000-000000000010',
 'Geburtstagsparty-Service Berlin',
 'Schönhauser Allee 180, 10119 Berlin',
 52.5307885,
 13.4109712,
 '+49 30 77889900',
 'party@geburtstagsparty-berlin.de',
 'https://geburtstagsparty-berlin.de',
 ARRAY['geburtstagsfeier','event'],
 'https://images.unsplash.com/photo-1530103862676-de8c9debad1d?w=600');


-- =============================================================================
-- Clients (4 test profiles — auth_user_id left null, they have no Supabase Auth identity)
-- =============================================================================
INSERT INTO kummo.clients (id, first_name, last_name, email, age, interests, number_children) VALUES

('b2000000-0000-0000-0000-000000000001',
 'Anna', 'Schmidt', 'anna.schmidt@example.de', 34,
 ARRAY['kunst','natur','kochen'], 2),

('b2000000-0000-0000-0000-000000000002',
 'Mehmet', 'Yilmaz', 'mehmet.yilmaz@example.de', 41,
 ARRAY['sport','musik','theater'], 3),

('b2000000-0000-0000-0000-000000000003',
 'Renate', 'Müller', 'renate.mueller@example.de', 67,
 ARRAY['natur','kultur','kochen'], 0),

('b2000000-0000-0000-0000-000000000004',
 'Thomas', 'Weber', 'thomas.weber@example.de', 38,
 ARRAY['sport','wissenschaft','outdoor'], 2);


-- =============================================================================
-- Activities (20+ across all vendors)
-- =============================================================================
INSERT INTO kummo.activities (id, vendor_id, title, description, price, participants_max, duration, age_group, picture) VALUES

-- Kreativwerkstatt Kreuzberg
('d4000000-0000-0000-0000-000000000001',
 'a1000000-0000-0000-0000-000000000001',
 'Malen mit Kindern',
 'Gemeinsam mit Acrylfarben auf Leinwand kreativ werden. Alle Materialien sind inklusive.',
 18.00, 12, '2 Stunden', '4-10 Jahre',
 'https://images.unsplash.com/photo-1513364776144-60967b0f800f?w=400'),

('d4000000-0000-0000-0000-000000000002',
 'a1000000-0000-0000-0000-000000000001',
 'Töpfern für Anfänger',
 'Töpferscheibe ausprobieren und eine eigene Schale formen. Geeignet ab 6 Jahren.',
 22.00, 8, '1,5 Stunden', '6-14 Jahre',
 'https://images.unsplash.com/photo-1565193566173-7a0ee3dbe261?w=400'),

('d4000000-0000-0000-0000-000000000003',
 'a1000000-0000-0000-0000-000000000001',
 'Familien-Bastelnachmittag',
 'Gemeinsam basteln: Papier, Stoff, Farbe. Für die ganze Familie.',
 12.00, 20, '2,5 Stunden', 'Familie',
 'https://images.unsplash.com/photo-1513364776144-60967b0f800f?w=400'),

-- Tierpark Berlin
('d4000000-0000-0000-0000-000000000004',
 'a1000000-0000-0000-0000-000000000002',
 'Zoo-Führung für Familien',
 'Geführte Tour durch den Tierpark mit Fütterungszeiten und spannenden Geschichten.',
 8.00, 25, '2 Stunden', 'Familie',
 'https://images.unsplash.com/photo-1534567153574-2b12153a87f0?w=400'),

('d4000000-0000-0000-0000-000000000005',
 'a1000000-0000-0000-0000-000000000002',
 'Tierpflege-Workshop',
 'Helft bei der Fütterung und Pflege von Kaninchen, Meerschweinchen und Ziegen.',
 15.00, 10, '1,5 Stunden', '4-8 Jahre',
 'https://images.unsplash.com/photo-1534567153574-2b12153a87f0?w=400'),

-- Musikschule Pankow
('d4000000-0000-0000-0000-000000000006',
 'a1000000-0000-0000-0000-000000000003',
 'Gitarre lernen (Anfänger)',
 'In 6 Wochen die Grundlagen der Gitarre. Eigene Gitarre wird gestellt.',
 45.00, 6, '1 Stunde', '8-14 Jahre',
 'https://images.unsplash.com/photo-1511379938547-c1f69419868d?w=400'),

('d4000000-0000-0000-0000-000000000007',
 'a1000000-0000-0000-0000-000000000003',
 'Musikalisches Frühschichten',
 'Singen, Klatschen und Tanzen für die Kleinsten. Eltern begleiten ihr Kind.',
 10.00, 15, '45 Minuten', '1-4 Jahre',
 'https://images.unsplash.com/photo-1511379938547-c1f69419868d?w=400'),

-- Sportpark Neukölln
('d4000000-0000-0000-0000-000000000008',
 'a1000000-0000-0000-0000-000000000004',
 'Kinder-Turnen',
 'Beweglichkeit, Koordination und Spaß im Turnsaal.',
 8.00, 16, '1 Stunde', '3-6 Jahre',
 'https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=400'),

('d4000000-0000-0000-0000-000000000009',
 'a1000000-0000-0000-0000-000000000004',
 'Familien-Yoga',
 'Entspannungsübungen und Yoga-Positionen für Eltern mit Kindern.',
 12.00, 12, '1 Stunde', 'Familie',
 'https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=400'),

-- Naturwerkstatt Grunewald
('d4000000-0000-0000-0000-000000000010',
 'a1000000-0000-0000-0000-000000000005',
 'Natur-Entdeckungspfad',
 'Mit Lupen und Bestimmungsbüchern die Tier- und Pflanzenwelt erkunden.',
 6.00, 20, '2 Stunden', '5-12 Jahre',
 'https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=400'),

('d4000000-0000-0000-0000-000000000011',
 'a1000000-0000-0000-0000-000000000005',
 'Wald-Olympiade',
 'Viel Bewegung in der Natur: Klettern, Balancieren, Verstecken.',
 9.00, 15, '2,5 Stunden', '6-12 Jahre',
 'https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=400'),

-- Kinderkochstudio Mitte
('d4000000-0000-0000-0000-000000000012',
 'a1000000-0000-0000-0000-000000000006',
 'Pizza selber machen',
 'Teig kneten, belegen und im Holzofen backen. Mitnehmen erlaubt!',
 20.00, 10, '2 Stunden', '6-12 Jahre',
 'https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=400'),

('d4000000-0000-0000-0000-000000000013',
 'a1000000-0000-0000-0000-000000000006',
 'Smoothie-Workshop',
 'Gesunde Smoothies mixen mit frischem Obst und Gemüse.',
 14.00, 12, '1 Stunde', '4-10 Jahre',
 'https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=400'),

-- Theater Liliput
('d4000000-0000-0000-0000-000000000014',
 'a1000000-0000-0000-0000-000000000007',
 'Kinder-Theaterworkshop',
 'Szenen einstudieren, Kostüme anprobieren und am Ende eine kleine Aufführung.',
 16.00, 14, '2 Stunden', '6-12 Jahre',
 'https://images.unsplash.com/photo-1503095396549-807759245b35?w=400'),

('d4000000-0000-0000-0000-000000000015',
 'a1000000-0000-0000-0000-000000000007',
 'Puppentheater: Der kleine Drache',
 'Eine interaktive Puppenshow mit Mitmach-Elementen.',
 7.00, 30, '45 Minuten', '3-8 Jahre',
 'https://images.unsplash.com/photo-1503095396549-807759245b35?w=400'),

-- Forscherwerkstatt Charlottenburg
('d4000000-0000-0000-0000-000000000016',
 'a1000000-0000-0000-0000-000000000008',
 'Kleine Forscher: Chemie-Experimente',
 'Blasen, Farben, Reaktionen — sicher experimentieren im Labor.',
 18.00, 8, '1,5 Stunden', '6-12 Jahre',
 'https://images.unsplash.com/photo-1532094349884-543bc11b234d?w=400'),

('d4000000-0000-0000-0000-000000000017',
 'a1000000-0000-0000-0000-000000000008',
 'Robotik für Kinder',
 'Programmierbare Roboter bauen und steuern. Mit LEGO Mindstorms.',
 25.00, 6, '2 Stunden', '8-14 Jahre',
 'https://images.unsplash.com/photo-1532094349884-543bc11b234d?w=400'),

-- Schwimmakademie Spandau
('d4000000-0000-0000-0000-000000000018',
 'a1000000-0000-0000-0000-000000000009',
 'Schwimmkurs für Anfänger',
 'Sicherheit im Wasser: Tauchen, Gleiten, Kraul-Grundlagen.',
 30.00, 6, '1 Stunde', '4-8 Jahre',
 'https://images.unsplash.com/photo-1530549387789-4c1017266635?w=400'),

('d4000000-0000-0000-0000-000000000019',
 'a1000000-0000-0000-0000-000000000009',
 'Familien-Schwimmen',
 'Freischwimmen mit Aufsicht. Spielzeug und Rettungswesten vorhanden.',
 5.00, 30, '1,5 Stunden', 'Familie',
 'https://images.unsplash.com/photo-1530549387789-4c1017266635?w=400'),

-- Geburtstagsparty-Service Berlin
('d4000000-0000-0000-0000-000000000020',
 'a1000000-0000-0000-0000-000000000010',
 'Geburtstagsparty: Piratenabenteuer',
 'Schatzsuche, Piratenspiele und Kostüme. Inkl. Kuchen und Getränke.',
 150.00, 15, '3 Stunden', '5-10 Jahre',
 'https://images.unsplash.com/photo-1530103862676-de8c9debad1d?w=400'),

('d4000000-0000-0000-0000-000000000021',
 'a1000000-0000-0000-0000-000000000010',
 'Geburtstagsparty: Prinzessinnenfest',
 'Schminken, Krone basteln und Tanzen. Inkl. Kuchen und Getränke.',
 150.00, 15, '3 Stunden', '4-8 Jahre',
 'https://images.unsplash.com/photo-1530103862676-de8c9debad1d?w=400'),

('d4000000-0000-0000-0000-000000000022',
 'a1000000-0000-0000-0000-000000000010',
 'Senioren-Nachmittag: Kaffee & Kuchen',
 'Gemütlicher Nachmittag mit Gesellschaftsspielen und Kaffee.',
 8.00, 20, '2 Stunden', 'Senioren',
 'https://images.unsplash.com/photo-1530103862676-de8c9debad1d?w=400');


