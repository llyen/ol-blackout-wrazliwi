import { getRayfinClient, isLocalBackend } from './rayfinClient';

/**
 * Zapis zwrotny pulpitu „Tarcza Zimowa”.
 *
 * Zasady z `fabric-app/APP_SPEC.md`:
 * 1. Nic się nie usuwa. Odwołanie decyzji krajowej to nowy wpis wskazujący
 *    poprzedni, a nie zmiana istniejącego — rejestr ma być dowodem.
 * 2. Zakres uprawnień wynika z roli. RCB widzi kraj bez list osób, wojewoda
 *    swoje województwo, gmina i OSP wyłącznie własny teren.
 * 3. **Dane osobowe nie opuszczają warstwy źródłowej.** Osoba jest wszędzie
 *    identyfikowana tokenem; kontakt jest fikcyjny i służy wyłącznie do
 *    pokazania, że aplikacja terenowa go potrzebuje.
 *
 * Bez skonfigurowanego backendu zapisy trafiają do pamięci, żeby aplikację
 * dało się zademonstrować bez połączenia z Fabric.
 */

export type UserRole =
  | 'RCB'
  | 'wojewoda / WCZK'
  | 'gmina'
  | 'OSP'
  | 'koordynator medyczny';

export const USER_ROLES: UserRole[] = [
  'RCB',
  'wojewoda / WCZK',
  'gmina',
  'OSP',
  'koordynator medyczny',
];

/** Role z widokiem krajowym — wyłącznie agregaty, bez list osób. */
export const NATIONAL_ROLES: UserRole[] = ['RCB'];

/** Role uprawnione do zatwierdzania przydziału agregatów. */
export const ASSIGNING_ROLES: UserRole[] = ['wojewoda / WCZK'];

/** Role uprawnione do zapisania wyniku wizyty kontrolnej. */
export const VISIT_ROLES: UserRole[] = ['gmina', 'OSP'];

/** Role uprawnione do raportowania z punktu grzewczego. */
export const HEATING_ROLES: UserRole[] = ['gmina', 'OSP'];

export interface Actor {
  id: string;
  name: string;
  role: UserRole;
  /** Kod województwa; pusty = zakres krajowy. */
  voivodeshipCode: string;
  /** Kod gminy dla ról lokalnych; pusty = brak ograniczenia gminnego. */
  gminaCode: string;
  /** Identyfikator zespołu OSP — ogranicza kolejkę wizyt do przydzielonych osób. */
  teamId: string;
}

export interface ValidationResult {
  ok: boolean;
  errors: string[];
}

/* ------------------------------------------------------------------ */
/* Zakres widoczności                                                  */
/* ------------------------------------------------------------------ */

/**
 * Czy aktor może działać w danej gminie. Reguły są tutaj, a nie w komponencie,
 * żeby dało się je sprawdzić testem bez renderowania ekranu.
 */
export function canActOn(actor: Actor, gminaCode: string, voivodeshipCode: string): boolean {
  switch (actor.role) {
    case 'RCB':
      return true;
    case 'wojewoda / WCZK':
      return !actor.voivodeshipCode || actor.voivodeshipCode === voivodeshipCode;
    case 'gmina':
    case 'OSP':
      return !actor.gminaCode || actor.gminaCode === gminaCode;
    case 'koordynator medyczny':
      // Koordynator ma wgląd w kategorie medyczne w całym kraju, ale niczego
      // nie zapisuje — o tym decydują walidacje poszczególnych formularzy.
      return true;
  }
}

/**
 * Czy rola może zobaczyć listę osób (a nie tylko liczbę).
 *
 * RCB jest tu świadomie wykluczone. Widok krajowy pracuje na agregatach —
 * to jeden z testów akceptacyjnych ze specyfikacji.
 */
export function canSeePersonList(role: UserRole): boolean {
  return role === 'gmina' || role === 'OSP' || role === 'koordynator medyczny';
}

/** Czy rola może zobaczyć fikcyjny kontakt do osoby (tylko zespół w terenie). */
export function canSeeContact(role: UserRole): boolean {
  return role === 'gmina' || role === 'OSP';
}

/* ------------------------------------------------------------------ */
/* Identyfikatory i skrót kontrolny                                    */
/* ------------------------------------------------------------------ */

let sequence = 0;

export function newId(prefix: string, sceneTime: string): string {
  sequence += 1;
  const day = sceneTime.slice(0, 10).replace(/-/g, '');
  return `${prefix}-${day}-${String(sequence).padStart(3, '0')}`;
}

/**
 * Skrót przesłanek decyzji. Nie jest to podpis kryptograficzny — służy do
 * pokazania, że decyzja niesie ze sobą migawkę danych, na podstawie których
 * zapadła, więc da się ją później zweryfikować.
 */
export function auditHash(payload: Record<string, unknown>): string {
  const text = JSON.stringify(payload, Object.keys(payload).sort());
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, '0');
}

/* ------------------------------------------------------------------ */
/* Decyzja krajowa                                                     */
/* ------------------------------------------------------------------ */

export const DECISION_TYPES = [
  { key: 'zwolanie_RZZK', label: 'Zwołanie RZZK' },
  { key: 'uruchomienie_SPO-5', label: 'Uruchomienie SPO-5 (ewakuacja)' },
  { key: 'uruchomienie_SPO-12', label: 'Uruchomienie SPO-12 (ochrona wrażliwych)' },
  { key: 'wniosek_o_wsparcie_SZ', label: 'Wniosek o wsparcie Sił Zbrojnych' },
  { key: 'stan_kleski', label: 'Wniosek o stan klęski żywiołowej' },
  { key: 'odwolanie', label: 'Odwołanie wcześniejszej decyzji' },
] as const;

export interface NationalDecisionRecord {
  id: string;
  decision_id: string;
  scene_time: string;
  decision_type: string;
  scope: string;
  critical_gminas: number;
  vulnerable_without_power: number;
  justification: string;
  supersedes: string;
  author_id: string;
  author_name: string;
  author_role: string;
  created_at: Date;
}

export interface NationalDecisionDraft {
  scene_time: string;
  decision_type: string;
  scope: string;
  critical_gminas: number;
  vulnerable_without_power: number;
  justification: string;
  supersedes: string;
}

export function validateNationalDecision(
  draft: NationalDecisionDraft,
  actor: Actor,
): ValidationResult {
  const errors: string[] = [];
  if (!draft.decision_type) errors.push('Wybierz rodzaj decyzji.');
  if (draft.justification.trim().length < 20)
    errors.push('Uzasadnienie musi mieć co najmniej 20 znaków — to zapis dla protokołu RZZK.');
  if (draft.justification.trim().length > 1500)
    errors.push('Uzasadnienie nie może przekraczać 1500 znaków.');
  if (draft.decision_type === 'odwolanie' && !draft.supersedes)
    errors.push('Odwołanie musi wskazywać decyzję, której dotyczy.');
  if (draft.decision_type !== 'odwolanie' && draft.supersedes)
    errors.push('Wskazanie poprzedniej decyzji dotyczy wyłącznie odwołania.');
  if (actor.role !== 'RCB' && actor.role !== 'wojewoda / WCZK')
    errors.push('Decyzję tego szczebla podejmuje RCB albo wojewoda.');
  if (actor.role === 'wojewoda / WCZK' && draft.scope === 'kraj')
    errors.push('Wojewoda podejmuje decyzje w zakresie własnego województwa.');
  return { ok: errors.length === 0, errors };
}

/* ------------------------------------------------------------------ */
/* Przydział agregatu                                                  */
/* ------------------------------------------------------------------ */

export type AssignmentStatus = 'zatwierdzony' | 'zmieniony' | 'odrzucony' | 'wniosek_o_wiecej';

export interface GeneratorAssignmentRecord {
  id: string;
  assignment_id: string;
  scene_time: string;
  generator_id: string;
  target_type: string;
  target_id: string;
  target_name: string;
  gmina_code: string;
  gmina_name: string;
  voivodeship_code: string;
  power_kw: number;
  power_need_kw: number;
  eta_minutes: number;
  covered_vulnerable: number;
  status: string;
  comment: string;
  recommended_generator_id: string;
  author_id: string;
  author_name: string;
  author_role: string;
  created_at: Date;
}

export type GeneratorAssignmentDraft = Omit<
  GeneratorAssignmentRecord,
  'id' | 'assignment_id' | 'author_id' | 'author_name' | 'author_role' | 'created_at'
>;

export function validateAssignment(
  draft: GeneratorAssignmentDraft,
  actor: Actor,
): ValidationResult {
  const errors: string[] = [];
  if (!draft.target_id) errors.push('Wskaż punkt grzewczy albo placówkę.');
  if (draft.status !== 'wniosek_o_wiecej' && !draft.generator_id)
    errors.push('Wskaż agregat do przydzielenia.');
  if (!Number.isFinite(draft.power_kw) || draft.power_kw <= 0)
    errors.push('Moc agregatu musi być większa od zera.');
  if (!Number.isFinite(draft.eta_minutes) || draft.eta_minutes < 0 || draft.eta_minutes > 1440)
    errors.push('Czas dojazdu musi mieścić się w zakresie 0–1440 minut.');
  if (
    (draft.status === 'zmieniony' || draft.status === 'odrzucony') &&
    draft.comment.trim().length < 10
  )
    errors.push('Zmiana i odrzucenie wymagają komentarza o długości co najmniej 10 znaków.');
  if (draft.comment.trim().length > 1200)
    errors.push('Komentarz nie może przekraczać 1200 znaków.');
  if (!ASSIGNING_ROLES.includes(actor.role))
    errors.push('Przydział agregatu zatwierdza wojewoda albo WCZK.');
  else if (!canActOn(actor, draft.gmina_code, draft.voivodeship_code))
    errors.push('Cel leży poza województwem, którym dysponuje ta rola.');
  return { ok: errors.length === 0, errors };
}

/**
 * Czy moc agregatu pokrywa zapotrzebowanie celu.
 *
 * Nie jest to błąd walidacji — wojewoda może świadomie wysłać słabszy agregat,
 * żeby utrzymać samo ogrzewanie bez oświetlenia. Aplikacja ma to pokazać,
 * a nie zablokować.
 */
export function powerShortfall(draft: {
  power_kw: number;
  power_need_kw: number;
}): number {
  return Math.max(0, Math.round((draft.power_need_kw - draft.power_kw) * 10) / 10);
}

/* ------------------------------------------------------------------ */
/* Wynik wizyty kontrolnej                                             */
/* ------------------------------------------------------------------ */

export interface WelfareVisitRecord {
  id: string;
  visit_result_id: string;
  scene_time: string;
  person_token: string;
  category: string;
  gmina_code: string;
  gmina_name: string;
  team_id: string;
  result: string;
  destination: string;
  autonomy_hours_left: number;
  notes: string;
  offline_sync_id: string;
  capture_mode: string;
  author_id: string;
  author_name: string;
  author_role: string;
  created_at: Date;
}

export type WelfareVisitDraft = Omit<
  WelfareVisitRecord,
  'id' | 'visit_result_id' | 'author_id' | 'author_name' | 'author_role' | 'created_at'
>;

export function validateVisit(
  draft: WelfareVisitDraft,
  actor: Actor,
  assignedTokens: Set<string>,
): ValidationResult {
  const errors: string[] = [];
  if (!draft.person_token) errors.push('Wskaż osobę z kolejki.');
  if (!draft.result) errors.push('Wybierz wynik wizyty.');
  if (draft.result === 'evacuation' && !draft.destination.trim())
    errors.push('Przy ewakuacji podaj miejsce docelowe.');
  if (draft.result !== 'evacuation' && draft.destination.trim())
    errors.push('Miejsce docelowe dotyczy wyłącznie ewakuacji.');
  if (draft.notes.length > 500) errors.push('Notatka nie może przekraczać 500 znaków.');
  if (!draft.team_id) errors.push('Wskaż zespół, który przeprowadził wizytę.');
  if (!VISIT_ROLES.includes(actor.role))
    errors.push('Wynik wizyty zapisuje gmina albo zespół OSP.');
  else if (assignedTokens.size > 0 && !assignedTokens.has(draft.person_token))
    errors.push('Osoba nie jest w przydziale tego zespołu — wynik zapisze zespół właściwy.');
  else if (!canActOn(actor, draft.gmina_code, ''))
    errors.push('Osoba jest spoza gminy, którą obsługuje ta rola.');
  return { ok: errors.length === 0, errors };
}

/**
 * Odsiewa powtórzone zapisy z trybu offline.
 *
 * Urządzenie terenowe nadaje `offline_sync_id` przed wysyłką. Po odzyskaniu
 * łączności ta sama paczka może pójść drugi raz — ten sam identyfikator
 * oznacza ten sam wynik, a nie drugą wizytę.
 */
export function dedupeVisits<T extends { offline_sync_id: string; created_at: Date }>(
  records: T[],
): T[] {
  const seen = new Map<string, T>();
  for (const r of records) {
    if (!r.offline_sync_id) {
      seen.set(`__${seen.size}`, r);
      continue;
    }
    const prev = seen.get(r.offline_sync_id);
    if (!prev || new Date(r.created_at) > new Date(prev.created_at)) {
      seen.set(r.offline_sync_id, r);
    }
  }
  return [...seen.values()];
}

/* ------------------------------------------------------------------ */
/* Raport z punktu grzewczego                                          */
/* ------------------------------------------------------------------ */

/** Checklista otwarcia punktu grzewczego — pozycje nieodhaczone trafiają do raportu. */
export const OPENING_CHECKLIST = [
  { key: 'heat', label: 'Źródło ciepła sprawne i uruchomione' },
  { key: 'power', label: 'Zasilanie awaryjne sprawdzone' },
  { key: 'co', label: 'Czujniki tlenku węgla rozmieszczone' },
  { key: 'water', label: 'Woda pitna i napoje ciepłe' },
  { key: 'beds', label: 'Miejsca do leżenia przygotowane' },
  { key: 'staff', label: 'Obsada dyżuru wyznaczona' },
  { key: 'medical', label: 'Apteczka i kontakt do koordynatora medycznego' },
  { key: 'comms', label: 'Łączność zapasowa (radio) sprawdzona' },
] as const;

export interface HeatingReportRecord {
  id: string;
  report_id: string;
  scene_time: string;
  heating_point_id: string;
  gmina_code: string;
  gmina_name: string;
  voivodeship_code: string;
  status: string;
  occupancy: number;
  capacity: number;
  needs_food: boolean;
  needs_medical_support: boolean;
  needs_generator: boolean;
  fuel_hours_remaining: number;
  comment: string;
  checklist_gaps: string;
  offline_sync_id: string;
  capture_mode: string;
  author_id: string;
  author_name: string;
  author_role: string;
  created_at: Date;
}

export type HeatingReportDraft = Omit<
  HeatingReportRecord,
  'id' | 'report_id' | 'author_id' | 'author_name' | 'author_role' | 'created_at'
>;

export function validateHeatingReport(
  draft: HeatingReportDraft,
  actor: Actor,
): ValidationResult {
  const errors: string[] = [];
  if (!draft.heating_point_id) errors.push('Wskaż punkt grzewczy.');
  if (!draft.status) errors.push('Wybierz status punktu.');
  if (!Number.isFinite(draft.occupancy) || draft.occupancy < 0)
    errors.push('Obłożenie nie może być ujemne.');
  if (draft.occupancy > draft.capacity && draft.comment.trim().length < 10)
    errors.push(
      `Obłożenie przekracza pojemność (${draft.capacity}) — wymagany komentarz wyjaśniający.`,
    );
  if (!Number.isFinite(draft.fuel_hours_remaining) || draft.fuel_hours_remaining < 0)
    errors.push('Zapas paliwa nie może być ujemny.');
  if (draft.status === 'open' && draft.checklist_gaps.split(',').filter(Boolean).length > 3)
    errors.push('Punkt można otworzyć po odhaczeniu co najmniej pięciu pozycji checklisty.');
  if (draft.comment.length > 600) errors.push('Komentarz nie może przekraczać 600 znaków.');
  if (!HEATING_ROLES.includes(actor.role))
    errors.push('Raport z punktu grzewczego składa gmina albo zespół OSP.');
  else if (!canActOn(actor, draft.gmina_code, draft.voivodeship_code))
    errors.push('Punkt leży poza gminą, którą obsługuje ta rola.');
  return { ok: errors.length === 0, errors };
}

/* ------------------------------------------------------------------ */
/* Kampania ostrzegawcza SPO-3                                         */
/* ------------------------------------------------------------------ */

/** Elementy, które komunikat SPO-3 musi zawierać. Sprawdzane wyrażeniem. */
export const MESSAGE_REQUIREMENTS = [
  { key: 'shelter', label: 'miejsce ogrzania', pattern: /punkt(y|ów)? grzewcz|miejsc\w* ogrzani/i },
  { key: 'emergency', label: 'numer alarmowy', pattern: /\b112\b|\b998\b/ },
  { key: 'co', label: 'zasady bezpieczeństwa (czad)', pattern: /czad|tlenk\w* węgla|CO\b/i },
  { key: 'update', label: 'godzina aktualizacji', pattern: /\b\d{1,2}[:.]\d{2}\b/ },
] as const;

export function missingMessageParts(text: string): string[] {
  return MESSAGE_REQUIREMENTS.filter((r) => !r.pattern.test(text)).map((r) => r.label);
}

export interface AlertCampaignRecord {
  id: string;
  campaign_id: string;
  scene_time: string;
  message_text: string;
  channels: string;
  target_gminas: string;
  target_gmina_count: number;
  target_population: number;
  low_coverage_gminas: number;
  approval_status: string;
  language: string;
  scope: string;
  author_id: string;
  author_name: string;
  author_role: string;
  created_at: Date;
}

export type AlertCampaignDraft = Omit<
  AlertCampaignRecord,
  'id' | 'campaign_id' | 'author_id' | 'author_name' | 'author_role' | 'created_at'
>;

export function validateCampaign(draft: AlertCampaignDraft, actor: Actor): ValidationResult {
  const errors: string[] = [];
  const text = draft.message_text.trim();
  if (text.length < 160) errors.push(`Komunikat ma ${text.length} znaków — wymagane co najmniej 160.`);
  if (text.length > 600) errors.push('Komunikat nie może przekraczać 600 znaków.');
  const missing = missingMessageParts(text);
  if (missing.length > 0) errors.push(`Komunikat nie zawiera: ${missing.join(', ')}.`);
  if (!draft.channels) errors.push('Wybierz co najmniej jeden kanał.');
  if (draft.target_gmina_count === 0) errors.push('Wskaż co najmniej jedną gminę.');
  if (actor.role === 'koordynator medyczny' || actor.role === 'OSP')
    errors.push('Kampanię ostrzegawczą uruchamia RCB, wojewoda albo gmina.');
  return { ok: errors.length === 0, errors };
}

/**
 * Czy przy wybranym pokryciu telekomunikacyjnym kanały dotrą do odbiorców.
 * Zwraca kanały, które w tych gminach nie zadziałają.
 */
export function uselessChannels(channels: string[], lowCoverageCount: number): string[] {
  if (lowCoverageCount === 0) return [];
  return channels.filter((c) => c === 'RSO' || c === 'SMS' || c === 'WWW' || c === 'social');
}

/* ------------------------------------------------------------------ */
/* Utrwalanie                                                          */
/* ------------------------------------------------------------------ */

const memory = {
  decisions: [] as NationalDecisionRecord[],
  assignments: [] as GeneratorAssignmentRecord[],
  visits: [] as WelfareVisitRecord[],
  reports: [] as HeatingReportRecord[],
  campaigns: [] as AlertCampaignRecord[],
};

const DECISION_COLS = [
  'id',
  'decision_id',
  'scene_time',
  'decision_type',
  'scope',
  'critical_gminas',
  'vulnerable_without_power',
  'justification',
  'supersedes',
  'author_id',
  'author_name',
  'author_role',
  'created_at',
] as const;

const ASSIGNMENT_COLS = [
  'id',
  'assignment_id',
  'scene_time',
  'generator_id',
  'target_type',
  'target_id',
  'target_name',
  'gmina_code',
  'gmina_name',
  'voivodeship_code',
  'power_kw',
  'power_need_kw',
  'eta_minutes',
  'covered_vulnerable',
  'status',
  'comment',
  'recommended_generator_id',
  'author_id',
  'author_name',
  'author_role',
  'created_at',
] as const;

const VISIT_COLS = [
  'id',
  'visit_result_id',
  'scene_time',
  'person_token',
  'category',
  'gmina_code',
  'gmina_name',
  'team_id',
  'result',
  'destination',
  'autonomy_hours_left',
  'notes',
  'offline_sync_id',
  'capture_mode',
  'author_id',
  'author_name',
  'author_role',
  'created_at',
] as const;

const REPORT_COLS = [
  'id',
  'report_id',
  'scene_time',
  'heating_point_id',
  'gmina_code',
  'gmina_name',
  'voivodeship_code',
  'status',
  'occupancy',
  'capacity',
  'needs_food',
  'needs_medical_support',
  'needs_generator',
  'fuel_hours_remaining',
  'comment',
  'checklist_gaps',
  'offline_sync_id',
  'capture_mode',
  'author_id',
  'author_name',
  'author_role',
  'created_at',
] as const;

const CAMPAIGN_COLS = [
  'id',
  'campaign_id',
  'scene_time',
  'message_text',
  'channels',
  'target_gminas',
  'target_gmina_count',
  'target_population',
  'low_coverage_gminas',
  'approval_status',
  'language',
  'scope',
  'author_id',
  'author_name',
  'author_role',
  'created_at',
] as const;

/* eslint-disable @typescript-eslint/no-explicit-any */
async function readAll<T>(
  entityName: string,
  cols: readonly string[],
  fallback: T[],
): Promise<T[]> {
  if (isLocalBackend()) return [...fallback];
  const client = getRayfinClient() as any;
  const rows = await client.data[entityName]
    .select([...cols])
    .orderBy({ created_at: 'desc' })
    .execute();
  return rows as T[];
}

async function writeOne<T extends { id: string }>(
  entityName: string,
  record: T,
  fallback: T[],
): Promise<T> {
  if (isLocalBackend()) {
    fallback.unshift(record);
    return record;
  }
  const client = getRayfinClient() as any;
  const { id: _ignored, ...payload } = record;
  void _ignored;
  const saved = await client.data[entityName].create(payload);
  return saved as T;
}
/* eslint-enable @typescript-eslint/no-explicit-any */

export const listDecisions = () =>
  readAll<NationalDecisionRecord>('NationalDecision', DECISION_COLS, memory.decisions);
export const listAssignments = () =>
  readAll<GeneratorAssignmentRecord>('GeneratorAssignment', ASSIGNMENT_COLS, memory.assignments);
export const listVisits = () =>
  readAll<WelfareVisitRecord>('WelfareVisitResult', VISIT_COLS, memory.visits);
export const listReports = () =>
  readAll<HeatingReportRecord>('HeatingPointReport', REPORT_COLS, memory.reports);
export const listCampaigns = () =>
  readAll<AlertCampaignRecord>('AlertCampaign', CAMPAIGN_COLS, memory.campaigns);

export async function saveNationalDecision(
  draft: NationalDecisionDraft,
  actor: Actor,
): Promise<NationalDecisionRecord> {
  const v = validateNationalDecision(draft, actor);
  if (!v.ok) throw new Error(v.errors.join(' '));
  const record: NationalDecisionRecord = {
    ...draft,
    justification: draft.justification.trim(),
    id: crypto.randomUUID(),
    decision_id: newId('DEC', draft.scene_time),
    author_id: actor.id,
    author_name: actor.name,
    author_role: actor.role,
    created_at: new Date(),
  };
  return writeOne('NationalDecision', record, memory.decisions);
}

export async function saveAssignment(
  draft: GeneratorAssignmentDraft,
  actor: Actor,
): Promise<GeneratorAssignmentRecord> {
  const v = validateAssignment(draft, actor);
  if (!v.ok) throw new Error(v.errors.join(' '));
  const record: GeneratorAssignmentRecord = {
    ...draft,
    comment: draft.comment.trim(),
    id: crypto.randomUUID(),
    assignment_id: newId('PRZ', draft.scene_time),
    author_id: actor.id,
    author_name: actor.name,
    author_role: actor.role,
    created_at: new Date(),
  };
  return writeOne('GeneratorAssignment', record, memory.assignments);
}

export async function saveVisit(
  draft: WelfareVisitDraft,
  actor: Actor,
  assignedTokens: Set<string>,
): Promise<WelfareVisitRecord> {
  const v = validateVisit(draft, actor, assignedTokens);
  if (!v.ok) throw new Error(v.errors.join(' '));
  const record: WelfareVisitRecord = {
    ...draft,
    notes: draft.notes.trim(),
    offline_sync_id: draft.offline_sync_id || crypto.randomUUID(),
    id: crypto.randomUUID(),
    visit_result_id: newId('WIZ', draft.scene_time),
    author_id: actor.id,
    author_name: actor.name,
    author_role: actor.role,
    created_at: new Date(),
  };
  return writeOne('WelfareVisitResult', record, memory.visits);
}

export async function saveHeatingReport(
  draft: HeatingReportDraft,
  actor: Actor,
): Promise<HeatingReportRecord> {
  const v = validateHeatingReport(draft, actor);
  if (!v.ok) throw new Error(v.errors.join(' '));
  const record: HeatingReportRecord = {
    ...draft,
    comment: draft.comment.trim(),
    offline_sync_id: draft.offline_sync_id || crypto.randomUUID(),
    id: crypto.randomUUID(),
    report_id: newId('RAP', draft.scene_time),
    author_id: actor.id,
    author_name: actor.name,
    author_role: actor.role,
    created_at: new Date(),
  };
  return writeOne('HeatingPointReport', record, memory.reports);
}

export async function saveCampaign(
  draft: AlertCampaignDraft,
  actor: Actor,
): Promise<AlertCampaignRecord> {
  const v = validateCampaign(draft, actor);
  if (!v.ok) throw new Error(v.errors.join(' '));
  const record: AlertCampaignRecord = {
    ...draft,
    message_text: draft.message_text.trim(),
    id: crypto.randomUUID(),
    campaign_id: newId('KAM', draft.scene_time),
    author_id: actor.id,
    author_name: actor.name,
    author_role: actor.role,
    created_at: new Date(),
  };
  return writeOne('AlertCampaign', record, memory.campaigns);
}
