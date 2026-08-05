/**
 * Model sceny scenariusza „Tarcza Zimowa”.
 *
 * Scena jest statyczna i deterministyczna (97 klatek godzinowych, 14–18.01.2026),
 * ale prezentowana **jak strumień na żywo**: chwila scenariusza jest wyliczana
 * z zegara ściennego, więc demonstracja wygląda tak samo o 9 rano i o 23.
 * Szczegóły odwzorowania czasu opisuje `liveFrameIndex`.
 */

/* ------------------------------------------------------------------ */
/* Typy sceny                                                          */
/* ------------------------------------------------------------------ */

export interface SceneMeta {
  generated: string;
  tStart: string;
  tEnd: string;
  stepHours: number;
  frames: number;
  notebookSnapshot: string;
  weights: { iwl: number; outage: number; temp: number; telecom: number; rescue: number };
}

export interface SceneVoivodeship {
  c: string;
  n: string;
  lat: string;
  lon: string;
  axis: string;
}

export interface ScenePowiat {
  c: string;
  v: string;
  n: string;
}

export interface SceneGmina {
  c: string;
  n: string;
  v: string;
  p: string;
  lat: string;
  lon: string;
  pop: number;
  iwl: number;
  vuln: number;
  rescue: number;
  type: string;
}

export interface SceneHeatingPoint {
  id: string;
  g: string;
  type: string;
  cap: number;
  lat: string;
  lon: string;
  gen: boolean;
  stove: boolean;
  kw: number;
  avail: string;
  sel: boolean;
  score: number | null;
  covered: number;
}

export interface SceneGenerator {
  id: string;
  wh: string;
  v: string;
  kw: number;
  fuel: string;
  mob: string;
  status: string;
  lat: string;
  lon: string;
}

export interface SceneFacility {
  id: string;
  g: string;
  type: string;
  cap: number;
  occ: number;
  gen: boolean;
  auto: number;
  kw: number;
  lat: string;
  lon: string;
}

export interface SceneQueueItem {
  rank: number;
  token: string;
  cat: string;
  g: string;
  prio: number;
  auto: number;
  age: string;
  alone: boolean;
  cov: number;
  hours: number;
  contact: string;
}

export interface SceneRouteStop {
  seq: number;
  token: string;
  g: string;
  eta: number;
  action: string;
}

export interface SceneRoute {
  team: string;
  stops: SceneRouteStop[];
}

export interface SceneCrossing {
  g: string;
  n: string;
  t: string;
  izz: number;
  drivers: string;
}

export interface SceneWhatIf {
  g: string;
  n: string;
  izz: number;
  whatif: number;
  delta: number;
}

/**
 * Wiersz ryzyka w klatce. Tablica, nie obiekt — 97 klatek × do 260 gmin,
 * a nazwy pól powtórzone 25 tys. razy to jedna trzecia objętości pliku.
 * Kolejność: kod gminy, IZŻ, godziny bez zasilania, odbiorcy bez zasilania,
 * osoby wrażliwe bez zasilania, pokrycie telekomunikacyjne, temperatura odczuwalna.
 */
export type RiskRow = [string, number, number, number, number, number, number];

/** Stan punktu grzewczego: id, gmina, status, obłożenie, pojemność, 3 flagi potrzeb. */
export type HpRow = [string, string, string, number, number, number, number, number];

/** Dysponowanie agregatu: id, agregat, typ celu, gmina, status, moc. */
export type DispatchRow = [string, string, string, string, string, number];

/** Wizyta: id, token osoby, gmina, zespół, wynik. */
export type VisitRow = [string, string, string, string, string];

export interface SceneFrame {
  t: string;
  risk: RiskRow[];
  hp: HpRow[];
  disp: DispatchRow[];
  visits: VisitRow[];
  calls: Record<string, number>;
  callsG: Record<string, number>;
  alerts: { sent?: number; delivered?: number; opened?: number; ch?: Record<string, number> };
}

export interface Scene {
  meta: SceneMeta;
  voivodeships: SceneVoivodeship[];
  powiats: ScenePowiat[];
  gminas: SceneGmina[];
  heatingPoints: SceneHeatingPoint[];
  generators: SceneGenerator[];
  facilities: SceneFacility[];
  queue: SceneQueueItem[];
  routes: SceneRoute[];
  crossing: SceneCrossing[];
  whatif: SceneWhatIf[];
  alertsByGmina: Record<string, [number, number]>;
  summaries: Record<string, Record<string, unknown>>;
  frames: SceneFrame[];
}

/* ------------------------------------------------------------------ */
/* Rzut kartograficzny                                                 */
/* ------------------------------------------------------------------ */

/**
 * Musi być identyczne z BOUNDS w `components/CountryMap.tsx` oraz w generatorze
 * `tools/build_poland_geo.py`. Rozjazd tych trzech miejsc przesunie punkty
 * względem granic województw.
 */
export const BOUNDS = { minLat: 49.0, maxLat: 54.9, minLon: 14.1, maxLon: 24.2 };

export function project(lat: number, lon: number, w = 100, h = 100): { x: number; y: number } {
  return {
    x: ((lon - BOUNDS.minLon) / (BOUNDS.maxLon - BOUNDS.minLon)) * w,
    y: h - ((lat - BOUNDS.minLat) / (BOUNDS.maxLat - BOUNDS.minLat)) * h,
  };
}

/* ------------------------------------------------------------------ */
/* Skale i progi                                                       */
/* ------------------------------------------------------------------ */

/** Progi IZŻ są takie same jak w notatniku `03_dynamic_risk.py` i w Activatorze. */
export const IZZ_LEVELS = [
  { max: 40, key: 'monitoring', label: 'Monitorowanie', color: '#15803d' },
  { max: 60, key: 'elevated', label: 'Podwyższony', color: '#a16207' },
  { max: 75, key: 'high', label: 'Wysoki', color: '#c2410c' },
  { max: 1e9, key: 'critical', label: 'Krytyczny', color: '#d5233f' },
] as const;

export const IZZ_CRITICAL = 75;
export const IZZ_HIGH = 60;

export function izzLevel(score: number): (typeof IZZ_LEVELS)[number] {
  return IZZ_LEVELS.find((l) => score <= l.max) ?? IZZ_LEVELS[IZZ_LEVELS.length - 1];
}

export function izzColor(score: number): string {
  return izzLevel(score).color;
}

export const IZZ_LEGEND = IZZ_LEVELS.map((l) => ({
  label: l.label,
  value: l.max === 1e9 ? 85 : l.max - 5,
}));

/** Pokrycie telekomunikacyjne poniżej tej wartości oznacza, że RSO i SMS nie dotrą. */
export const COVERAGE_BLACKOUT = 0.2;

/** Poniżej dwóch godzin autonomii urządzenia medycznego wizyta jest pilna. */
export const AUTONOMY_URGENT_H = 2;

export const CALL_TYPE_LABELS: Record<string, string> = {
  no_heating: 'Brak ogrzewania',
  medical_device: 'Urządzenie medyczne',
  elderly_alone: 'Osoba starsza sama',
  carbon_monoxide: 'Podejrzenie czadu',
  fire: 'Pożar',
  power_outage: 'Brak zasilania',
  road_blocked: 'Droga nieprzejezdna',
  water_supply: 'Brak wody',
};

export const CATEGORY_LABELS: Record<string, string> = {
  home_oxygen: 'Tlenoterapia domowa',
  dialysis: 'Dializy',
  respirator: 'Respirator',
  insulin_dependent: 'Insulinozależność',
  mobility_impaired: 'Ograniczona mobilność',
  senior_alone: 'Senior samotny',
};

export const VISIT_RESULTS = [
  { key: 'contact_confirmed', label: 'Kontakt potwierdzony' },
  { key: 'no_contact', label: 'Brak kontaktu' },
  { key: 'evacuation', label: 'Ewakuacja' },
  { key: 'generator_needed', label: 'Potrzebny agregat' },
] as const;

export const CHANNELS = [
  { key: 'RSO', label: 'RSO', needsNetwork: true },
  { key: 'SMS', label: 'SMS', needsNetwork: true },
  { key: 'local_radio', label: 'Radio lokalne', needsNetwork: false },
  { key: 'WWW', label: 'Strona WWW', needsNetwork: true },
  { key: 'social', label: 'Media społecznościowe', needsNetwork: true },
] as const;

/* ------------------------------------------------------------------ */
/* Formatowanie                                                        */
/* ------------------------------------------------------------------ */

const NUM = new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 1 });

export function formatNumber(value: number): string {
  return NUM.format(value);
}

export function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString('pl-PL', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatHour(iso: string): string {
  return new Date(iso).toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });
}

/** Nazwy gmin w zbiorze są generowane („gmina podlaskie-miejski-05-03”) — skracamy. */
export function shortGminaName(name: string): string {
  return name.replace(/^gmina\s+/i, '').replace(/-/g, ' ');
}

/* ------------------------------------------------------------------ */
/* Odwzorowanie czasu na zegar ścienny                                 */
/* ------------------------------------------------------------------ */

/**
 * Ile minut zegara ściennego przypada na jedną godzinę scenariusza.
 * 0,5 min × 97 klatek ≈ 48 minut na pełny przebieg — tyle, żeby demonstracja
 * mogła iść w tle całą prezentację bez zapętlenia w jej trakcie.
 */
export const MINUTES_PER_FRAME = 0.5;

/**
 * Klatka odpowiadająca bieżącej chwili zegara.
 *
 * Scenariusz zapętla się, a punkt zaczepienia liczony jest od epoki, nie od
 * uruchomienia aplikacji. Dzięki temu dwie osoby patrzące na aplikację w tej
 * samej chwili widzą tę samą klatkę, a odświeżenie strony nie cofa przebiegu
 * do początku. To była wcześniejsza uwaga do dashboardu: symulacja ma działać
 * niezależnie od pory uruchomienia.
 */
export function liveFrameIndex(frameCount: number, now: number = Date.now()): number {
  if (frameCount <= 0) return 0;
  const frameMs = MINUTES_PER_FRAME * 60_000;
  const cycleMs = frameCount * frameMs;
  const phase = ((now % cycleMs) + cycleMs) % cycleMs;
  // Dzielimy przez długość klatki, nie przez długość cyklu przemnożoną przez
  // ich liczbę: ta druga postać przy niektórych chwilach schodzi o ułamek
  // poniżej całkowitej i zaokrągla w dół do poprzedniej klatki, przez co część
  // klatek wyświetla się dwa razy, a część wcale.
  return Math.min(frameCount - 1, Math.floor(phase / frameMs));
}

/** Ile milisekund pozostało do przeskoku na następną klatkę. */
export function msToNextFrame(frameCount: number, now: number = Date.now()): number {
  if (frameCount <= 0) return 60_000;
  const frameMs = MINUTES_PER_FRAME * 60_000;
  const cycleMs = frameCount * frameMs;
  const phase = ((now % cycleMs) + cycleMs) % cycleMs;
  return frameMs - (phase % frameMs);
}

/* ------------------------------------------------------------------ */
/* Indeks sceny                                                        */
/* ------------------------------------------------------------------ */

export interface FrameStats {
  /** Gminy z IZŻ ≥ 75. */
  critical: number;
  /** Gminy z IZŻ ≥ 60. */
  high: number;
  vulnerableWithoutPower: number;
  customersWithoutPower: number;
  maxIzz: number;
  /** Najniższa temperatura odczuwalna wśród gmin objętych zdarzeniem. */
  minFeelsLike: number;
  calls: number;
  /** Skuteczność SPO-3 w klatce: dostarczone / wysłane. */
  deliveryRate: number | null;
  openHeatingPoints: number;
  occupancy: number;
  visits: number;
}

export interface SceneIndex {
  scene: Scene;
  gminaByCode: Map<string, SceneGmina>;
  voivByCode: Map<string, SceneVoivodeship>;
  powiatByCode: Map<string, ScenePowiat>;
  heatingById: Map<string, SceneHeatingPoint>;
  generatorById: Map<string, SceneGenerator>;
  facilityById: Map<string, SceneFacility>;
  gminasByVoiv: Map<string, SceneGmina[]>;
  heatingByGmina: Map<string, SceneHeatingPoint[]>;
  facilitiesByGmina: Map<string, SceneFacility[]>;
  queueByGmina: Map<string, SceneQueueItem[]>;
  personByToken: Map<string, SceneQueueItem>;
  /** Statystyki liczone raz przy wczytaniu — używane przez oś czasu i iskierki. */
  stats: FrameStats[];
  /** Stan punktu grzewczego narastająco do danej klatki. */
  hpStateAt: (frame: number) => Map<string, HpRow>;
}

function emptyStats(): FrameStats {
  return {
    critical: 0,
    high: 0,
    vulnerableWithoutPower: 0,
    customersWithoutPower: 0,
    maxIzz: 0,
    minFeelsLike: 0,
    calls: 0,
    deliveryRate: null,
    openHeatingPoints: 0,
    occupancy: 0,
    visits: 0,
  };
}

export function indexScene(scene: Scene): SceneIndex {
  const gminaByCode = new Map(scene.gminas.map((g) => [g.c, g]));
  const voivByCode = new Map(scene.voivodeships.map((v) => [v.c, v]));
  const powiatByCode = new Map(scene.powiats.map((p) => [p.c, p]));
  const heatingById = new Map(scene.heatingPoints.map((h) => [h.id, h]));
  const generatorById = new Map(scene.generators.map((g) => [g.id, g]));
  const facilityById = new Map(scene.facilities.map((f) => [f.id, f]));

  const gminasByVoiv = new Map<string, SceneGmina[]>();
  for (const g of scene.gminas) {
    const list = gminasByVoiv.get(g.v) ?? [];
    list.push(g);
    gminasByVoiv.set(g.v, list);
  }
  const heatingByGmina = new Map<string, SceneHeatingPoint[]>();
  for (const h of scene.heatingPoints) {
    const list = heatingByGmina.get(h.g) ?? [];
    list.push(h);
    heatingByGmina.set(h.g, list);
  }
  const facilitiesByGmina = new Map<string, SceneFacility[]>();
  for (const f of scene.facilities) {
    const list = facilitiesByGmina.get(f.g) ?? [];
    list.push(f);
    facilitiesByGmina.set(f.g, list);
  }
  const queueByGmina = new Map<string, SceneQueueItem[]>();
  for (const q of scene.queue) {
    const list = queueByGmina.get(q.g) ?? [];
    list.push(q);
    queueByGmina.set(q.g, list);
  }
  const personByToken = new Map(scene.queue.map((q) => [q.token, q]));

  // Stan punktów grzewczych jest narastający: raport z godziny 8 obowiązuje,
  // dopóki nie przyjdzie następny. Liczymy prefiksy raz, zamiast przy każdym
  // przerysowaniu skanować wszystkie klatki od początku.
  const hpPrefix: Map<string, HpRow>[] = [];
  const running = new Map<string, HpRow>();
  const stats: FrameStats[] = [];

  for (const frame of scene.frames) {
    for (const row of frame.hp) running.set(row[0], row);
    hpPrefix.push(new Map(running));

    const s = emptyStats();
    let feels = Number.POSITIVE_INFINITY;
    for (const r of frame.risk) {
      if (r[1] >= IZZ_CRITICAL) s.critical += 1;
      if (r[1] >= IZZ_HIGH) s.high += 1;
      s.vulnerableWithoutPower += r[4];
      s.customersWithoutPower += r[3];
      if (r[1] > s.maxIzz) s.maxIzz = r[1];
      if (r[3] > 0 && r[6] < feels) feels = r[6];
    }
    s.minFeelsLike = Number.isFinite(feels) ? feels : 0;
    s.calls = Object.entries(frame.calls)
      .filter(([k]) => !k.startsWith('_'))
      .reduce((sum, [, v]) => sum + v, 0);
    const sent = frame.alerts.sent ?? 0;
    s.deliveryRate = sent > 0 ? (frame.alerts.delivered ?? 0) / sent : null;
    for (const row of running.values()) {
      if (row[2] === 'open' || row[2] === 'full') {
        s.openHeatingPoints += 1;
        s.occupancy += row[3];
      }
    }
    s.visits = frame.visits.length;
    stats.push(s);
  }

  return {
    scene,
    gminaByCode,
    voivByCode,
    powiatByCode,
    heatingById,
    generatorById,
    facilityById,
    gminasByVoiv,
    heatingByGmina,
    facilitiesByGmina,
    queueByGmina,
    personByToken,
    stats,
    hpStateAt: (frame: number) => hpPrefix[Math.max(0, Math.min(frame, hpPrefix.length - 1))] ?? new Map(),
  };
}

/** Wiersze ryzyka klatki jako mapa po kodzie gminy. */
export function riskMap(frame: SceneFrame): Map<string, RiskRow> {
  return new Map(frame.risk.map((r) => [r[0], r]));
}

/* ------------------------------------------------------------------ */
/* Rekomendacje                                                        */
/* ------------------------------------------------------------------ */

export interface Recommendation {
  id: string;
  title: string;
  detail: string;
  spo: string;
  severity: 'critical' | 'high' | 'info';
  gminaCode?: string;
}

/**
 * Przesłanki eskalacji liczone z bieżącej klatki.
 *
 * Progi odpowiadają regułom Activatora opisanym w `activator/RULES.md`, żeby
 * aplikacja i alerty w Fabric mówiły to samo. Lista jest krótka celowo —
 * wcześniejsza wersja pokazywała wszystko, co przekroczyło próg, i była
 * nieczytelna na odprawie.
 */
export function recommendations(
  index: SceneIndex,
  frameIndex: number,
  voivFilter: string,
): Recommendation[] {
  const frame = index.scene.frames[frameIndex];
  if (!frame) return [];
  const out: Recommendation[] = [];
  const inScope = (code: string) =>
    !voivFilter || index.gminaByCode.get(code)?.v === voivFilter;

  const rows = frame.risk.filter((r) => inScope(r[0]));
  const critical = rows.filter((r) => r[1] >= IZZ_CRITICAL);
  if (critical.length > 0) {
    const worst = critical[0];
    const g = index.gminaByCode.get(worst[0]);
    out.push({
      id: 'izz-critical',
      title: `${critical.length} ${critical.length === 1 ? 'gmina' : 'gmin'} w stanie krytycznym`,
      detail: `Najwyższy IZŻ ${formatNumber(worst[1])} w gminie ${shortGminaName(g?.n ?? worst[0])}: ${formatNumber(worst[2])} h bez zasilania, ${formatNumber(worst[6])} °C odczuwalne. Podstawa do zwołania RZZK i uruchomienia SPO-12.`,
      spo: 'SPO-12 · SPO-5',
      severity: 'critical',
      gminaCode: worst[0],
    });
  }

  const noContact = rows.filter((r) => r[5] < COVERAGE_BLACKOUT);
  if (noContact.length > 0) {
    out.push({
      id: 'telecom',
      title: `Łączność zerwana w ${noContact.length} gminach`,
      detail:
        'Poniżej 20% pokrycia RSO i SMS nie docierają. Ostrzeganie trzeba przenieść na radio lokalne, tablice ogłoszeń i patrole OSP.',
      spo: 'SPO-3',
      severity: 'high',
    });
  }

  const urgentPersons = index.scene.queue.filter(
    (q) => inScope(q.g) && q.auto > 0 && q.auto < AUTONOMY_URGENT_H,
  );
  if (urgentPersons.length > 0) {
    out.push({
      id: 'autonomy',
      title: `${urgentPersons.length} osób z autonomią urządzenia poniżej ${AUTONOMY_URGENT_H} h`,
      detail:
        'Wizyta kontrolna albo dowóz agregatu przed wyczerpaniem zasilania urządzenia medycznego. Kolejka jest na ekranie „Wizyty kontrolne”.',
      spo: 'SPO-12',
      severity: 'critical',
    });
  }

  const sent = frame.alerts.sent ?? 0;
  const rate = sent > 0 ? (frame.alerts.delivered ?? 0) / sent : null;
  if (rate !== null && rate < 0.6) {
    out.push({
      id: 'delivery',
      title: `Dostarczalność ostrzeżeń ${formatNumber(rate * 100)}%`,
      detail:
        'Poniżej 60% skuteczności kampanię trzeba wznowić innym kanałem. Ekran „Ostrzeganie SPO-3” pozwala wybrać gminy, które nie odebrały komunikatu.',
      spo: 'SPO-3',
      severity: 'high',
    });
  }

  const hpState = index.hpStateAt(frameIndex);
  const full = [...hpState.values()].filter(
    (r) => inScope(r[1]) && r[4] > 0 && r[3] / r[4] >= 0.95,
  );
  if (full.length > 0) {
    out.push({
      id: 'heating-full',
      title: `${full.length} ${full.length === 1 ? 'punkt grzewczy zapełniony' : 'punktów grzewczych zapełnionych'}`,
      detail:
        'Powyżej 95% pojemności trzeba otworzyć rezerwowy punkt albo przekierować transport. Lista jest na ekranie „Punkty grzewcze”.',
      spo: 'SPO-12',
      severity: 'high',
    });
  }

  const needGen = [...hpState.values()].filter((r) => inScope(r[1]) && r[7] === 1);
  if (needGen.length > 0) {
    out.push({
      id: 'need-generator',
      title: `${needGen.length} punktów zgłasza potrzebę agregatu`,
      detail:
        'Przydział zatwierdza wojewoda na ekranie „Plan agregatów”. Model podpowiada agregat o najkrótszym dojeździe i wystarczającej mocy.',
      spo: 'SPO-12',
      severity: 'info',
    });
  }

  return out;
}
