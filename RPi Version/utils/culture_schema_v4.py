"""DDL unique de la migration 3 → 4 du carnet (lots D à H). Ne pas modifier après livraison.

Ce fichier est la seule source du schéma 4 : il est écrit une fois, avant les lots D à H,
et aucun lot ne le modifie ensuite. Une évolution ultérieure exige une migration 5, jamais
une retouche de celle-ci — une migration déjà appliquée sur une base de production ne peut
plus changer de contenu sans rendre deux bases de même `user_version` différentes.

Contenu : vérifications versionnées (lot D), plages cibles pH/EC (lot E), repères
d'éclairage (lot F), contexte et affectations d'équipements (lot G), observations d'espace,
photos généralisées et journal transversal (lot H), plus les index dont les lots A et B ont
besoin pour rester bornés. Aucune ligne n'est inventée : ce que le schéma 3 ne connaissait
pas devient NULL, ou '{}' pour un contexte d'équipement inconnu.
"""

V4_TABLES = ("culture_targets", "culture_light_targets", "culture_equipment_links", "space_events")
V4_VIEWS = ("culture_journal",)

SCHEMA4_SQL = """
-- === Lot D : vérifications versionnées (recréation avec copie) ==============
CREATE TABLE culture_checklists_v4 (
  id TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK(revision >= 1),
  subject_id TEXT NOT NULL REFERENCES subjects(id),
  space TEXT CHECK(space IS NULL OR space IN ('space_1','space_2')),
  stage TEXT NOT NULL,
  stage_at TEXT,
  stage_precision TEXT CHECK(stage_precision IS NULL OR stage_precision IN ('date','approximative','instant')),
  subject_version INTEGER,
  effective_at TEXT NOT NULL,
  precision TEXT NOT NULL DEFAULT 'date' CHECK(precision IN ('date','approximative','instant')),
  recorded_at TEXT NOT NULL,
  clock_reliable INTEGER CHECK(clock_reliable IS NULL OR clock_reliable IN (0,1)),
  lighting INTEGER NOT NULL CHECK(lighting IN (0,1)),
  pump INTEGER NOT NULL CHECK(pump IN (0,1)),
  ventilation INTEGER NOT NULL CHECK(ventilation IN (0,1)),
  note TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  cancelled INTEGER NOT NULL DEFAULT 0 CHECK(cancelled IN (0,1)),
  equipment_context TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY(id, revision));

INSERT INTO culture_checklists_v4
  (id, revision, subject_id, space, stage, effective_at, precision, recorded_at,
   lighting, pump, ventilation, note)
  SELECT id, 1, subject_id, space, stage, effective_at, 'date', recorded_at,
         lighting, pump, ventilation, note
  FROM culture_checklists;

DROP TABLE culture_checklists;
ALTER TABLE culture_checklists_v4 RENAME TO culture_checklists;
CREATE INDEX culture_checklists_subject ON culture_checklists(subject_id, effective_at, id);
CREATE INDEX culture_checklists_recorded ON culture_checklists(recorded_at);

-- === Lot E : plages cibles pH/EC ===========================================
CREATE TABLE culture_targets (
  id TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK(revision >= 1),
  scope TEXT NOT NULL CHECK(scope IN ('subject','reservoir')),
  subject_id TEXT REFERENCES subjects(id),
  reservoir_id TEXT REFERENCES reservoirs(id),
  stage TEXT,
  label TEXT NOT NULL DEFAULT '',
  ph_min REAL CHECK(ph_min IS NULL OR (ph_min >= 0 AND ph_min <= 14)),
  ph_max REAL CHECK(ph_max IS NULL OR (ph_max >= 0 AND ph_max <= 14)),
  ec_min REAL CHECK(ec_min IS NULL OR (ec_min >= 0 AND ec_min <= 100)),
  ec_max REAL CHECK(ec_max IS NULL OR (ec_max >= 0 AND ec_max <= 100)),
  start_at TEXT NOT NULL,
  start_precision TEXT NOT NULL CHECK(start_precision IN ('date','approximative','instant')),
  start_sort_at TEXT NOT NULL,
  end_at TEXT,
  end_precision TEXT CHECK(end_precision IS NULL OR end_precision IN ('date','approximative','instant')),
  end_sort_at TEXT,
  note TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '',
  cancelled INTEGER NOT NULL DEFAULT 0 CHECK(cancelled IN (0,1)),
  recorded_at TEXT NOT NULL,
  clock_reliable INTEGER CHECK(clock_reliable IS NULL OR clock_reliable IN (0,1)),
  PRIMARY KEY(id, revision),
  CHECK((subject_id IS NULL) <> (reservoir_id IS NULL)),
  CHECK((scope = 'subject') = (subject_id IS NOT NULL)),
  CHECK(ph_min IS NOT NULL OR ph_max IS NOT NULL OR ec_min IS NOT NULL OR ec_max IS NOT NULL),
  CHECK(ph_min IS NULL OR ph_max IS NULL OR ph_min <= ph_max),
  CHECK(ec_min IS NULL OR ec_max IS NULL OR ec_min <= ec_max),
  CHECK((end_at IS NULL) = (end_sort_at IS NULL)),
  CHECK(end_sort_at IS NULL OR end_sort_at > start_sort_at));

CREATE INDEX culture_targets_window ON culture_targets(scope, subject_id, reservoir_id, start_sort_at);
CREATE INDEX culture_targets_dates ON culture_targets(start_sort_at, end_sort_at);

-- === Lot F : repères d'éclairage ===========================================
CREATE TABLE culture_light_targets (
  id TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK(revision >= 1),
  scope TEXT NOT NULL CHECK(scope IN ('global','subject','space')),
  subject_id TEXT REFERENCES subjects(id),
  space TEXT CHECK(space IS NULL OR space IN ('space_1','space_2')),
  stage TEXT,
  label TEXT NOT NULL,
  on_minutes INTEGER NOT NULL CHECK(on_minutes BETWEEN 0 AND 1440),
  off_minutes INTEGER NOT NULL CHECK(off_minutes BETWEEN 0 AND 1440),
  start_at TEXT NOT NULL,
  start_precision TEXT NOT NULL CHECK(start_precision IN ('date','approximative','instant')),
  start_sort_at TEXT NOT NULL,
  end_at TEXT,
  end_precision TEXT CHECK(end_precision IS NULL OR end_precision IN ('date','approximative','instant')),
  end_sort_at TEXT,
  note TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '',
  cancelled INTEGER NOT NULL DEFAULT 0 CHECK(cancelled IN (0,1)),
  recorded_at TEXT NOT NULL,
  clock_reliable INTEGER CHECK(clock_reliable IS NULL OR clock_reliable IN (0,1)),
  PRIMARY KEY(id, revision),
  CHECK(on_minutes + off_minutes = 1440),
  CHECK((scope = 'subject') = (subject_id IS NOT NULL)),
  CHECK((scope = 'space') = (space IS NOT NULL)),
  CHECK((end_at IS NULL) = (end_sort_at IS NULL)),
  CHECK(end_sort_at IS NULL OR end_sort_at > start_sort_at));

CREATE INDEX culture_light_scope ON culture_light_targets(scope, stage, start_sort_at);

-- === Lot G : contexte d'équipement et affectations datées ==================
ALTER TABLE solution_entries ADD COLUMN equipment_context TEXT NOT NULL DEFAULT '{}';

CREATE TABLE culture_equipment_links (
  id TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK(revision >= 1),
  equipment_id TEXT NOT NULL,
  scope TEXT NOT NULL CHECK(scope IN ('space','reservoir','greenhouse')),
  space TEXT CHECK(space IS NULL OR space IN ('space_1','space_2')),
  reservoir_id TEXT REFERENCES reservoirs(id),
  usage TEXT NOT NULL,
  display_name TEXT NOT NULL DEFAULT '',
  start_at TEXT NOT NULL,
  start_precision TEXT NOT NULL CHECK(start_precision IN ('date','approximative','instant')),
  start_sort_at TEXT NOT NULL,
  end_at TEXT,
  end_precision TEXT CHECK(end_precision IS NULL OR end_precision IN ('date','approximative','instant')),
  end_sort_at TEXT,
  source TEXT NOT NULL DEFAULT 'operator' CHECK(source IN ('operator','catalog_snapshot')),
  note TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '',
  cancelled INTEGER NOT NULL DEFAULT 0 CHECK(cancelled IN (0,1)),
  recorded_at TEXT NOT NULL,
  clock_reliable INTEGER CHECK(clock_reliable IS NULL OR clock_reliable IN (0,1)),
  PRIMARY KEY(id, revision),
  CHECK((scope = 'space') = (space IS NOT NULL)),
  CHECK((scope = 'reservoir') = (reservoir_id IS NOT NULL)),
  CHECK((end_at IS NULL) = (end_sort_at IS NULL)),
  CHECK(end_sort_at IS NULL OR end_sort_at > start_sort_at));

CREATE INDEX culture_equipment_window ON culture_equipment_links(equipment_id, start_sort_at);
CREATE INDEX culture_equipment_scope ON culture_equipment_links(scope, space, reservoir_id, start_sort_at);

-- === Lot H : observations d'espace, photos, journal ========================
CREATE TABLE space_events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK(revision >= 1),
  space TEXT NOT NULL CHECK(space IN ('space_1','space_2')),
  kind TEXT NOT NULL CHECK(kind IN ('observation','maintenance','incident')),
  effective_at TEXT NOT NULL,
  precision TEXT NOT NULL CHECK(precision IN ('date','approximative','instant')),
  sort_at TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  clock_reliable INTEGER NOT NULL CHECK(clock_reliable IN (0,1)),
  payload TEXT NOT NULL,
  cancelled INTEGER NOT NULL DEFAULT 0 CHECK(cancelled IN (0,1)),
  reason TEXT NOT NULL DEFAULT '',
  equipment_context TEXT NOT NULL DEFAULT '{}',
  UNIQUE(id, revision));

CREATE INDEX space_events_space ON space_events(space, sort_at);
CREATE INDEX space_events_sort ON space_events(sort_at, sequence);

CREATE TABLE culture_media_v4 (
  id TEXT PRIMARY KEY,
  owner_kind TEXT NOT NULL CHECK(owner_kind IN ('event','space_event')),
  subject_id TEXT REFERENCES subjects(id),
  space TEXT CHECK(space IS NULL OR space IN ('space_1','space_2')),
  event_id TEXT,
  event_revision INTEGER,
  space_event_id TEXT,
  space_event_revision INTEGER,
  name TEXT NOT NULL UNIQUE,
  sha256 TEXT NOT NULL,
  size INTEGER NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  caption TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  CHECK((owner_kind = 'event') = (event_id IS NOT NULL)),
  CHECK((owner_kind = 'space_event') = (space_event_id IS NOT NULL)),
  CHECK((event_id IS NULL) = (event_revision IS NULL)),
  CHECK((space_event_id IS NULL) = (space_event_revision IS NULL)),
  CHECK((owner_kind = 'event') = (subject_id IS NOT NULL)),
  CHECK((owner_kind = 'space_event') = (space IS NOT NULL)),
  FOREIGN KEY(event_id, event_revision) REFERENCES events(id, revision),
  FOREIGN KEY(space_event_id, space_event_revision) REFERENCES space_events(id, revision));

INSERT INTO culture_media_v4
  (id, owner_kind, subject_id, event_id, event_revision,
   name, sha256, size, width, height, caption, recorded_at)
  SELECT id, 'event', subject_id, event_id, event_revision,
         name, sha256, size, width, height, caption, recorded_at
  FROM culture_media;

DROP TABLE culture_media;
ALTER TABLE culture_media_v4 RENAME TO culture_media;
CREATE INDEX culture_media_owner ON culture_media(owner_kind, event_id, space_event_id);
CREATE INDEX culture_media_space ON culture_media(space, recorded_at);

CREATE VIEW culture_journal AS
  SELECT 'event' AS source, e.id AS entry_id, e.revision AS revision, e.kind AS kind,
         e.subject_id AS subject_id, NULL AS space, NULL AS reservoir_id,
         e.effective_at AS effective_at, e.precision AS precision, e.sort_at AS sort_at,
         e.recorded_at AS recorded_at, e.cancelled AS cancelled,
         (SELECT MIN(v.sequence) FROM events v WHERE v.id = e.id) AS ordinal
    FROM events e
   WHERE e.revision = (SELECT MAX(v.revision) FROM events v WHERE v.id = e.id)
  UNION ALL
  SELECT 'solution', s.id, s.revision, s.kind,
         NULL, NULL, s.reservoir_id,
         s.effective_at, s.precision, s.sort_at, s.recorded_at, s.cancelled,
         (SELECT MIN(v.sequence) FROM solution_entries v WHERE v.id = s.id)
    FROM solution_entries s
   WHERE s.revision = (SELECT MAX(v.revision) FROM solution_entries v WHERE v.id = s.id)
  UNION ALL
  SELECT 'space_event', p.id, p.revision, p.kind,
         NULL, p.space, NULL,
         p.effective_at, p.precision, p.sort_at, p.recorded_at, p.cancelled,
         (SELECT MIN(v.sequence) FROM space_events v WHERE v.id = p.id)
    FROM space_events p
   WHERE p.revision = (SELECT MAX(v.revision) FROM space_events v WHERE v.id = p.id);

-- === Index transversaux (lots A, B, H) =====================================
CREATE INDEX events_sort ON events(sort_at, sequence);
CREATE INDEX solution_entries_sort ON solution_entries(sort_at, sequence);
CREATE INDEX solution_targets_subject ON solution_targets(subject_id, entry_id, revision);
CREATE INDEX solution_entries_kind ON solution_entries(kind, sort_at);
CREATE INDEX climate_hours_hour ON climate_hours(hour, sensor);
"""
