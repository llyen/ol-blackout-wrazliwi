import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  AUTONOMY_URGENT_H,
  COVERAGE_BLACKOUT,
  IZZ_LEVELS,
  MINUTES_PER_FRAME,
  indexScene,
  izzColor,
  liveFrameIndex,
  msToNextFrame,
  shortGminaName,
  type Scene,
} from '@/data/model';
import {
  canActOn,
  canSeePersonList,
  dedupeVisits,
  missingMessageParts,
  uselessChannels,
  validateCampaign,
  validateHeatingReport,
  validateVisit,
  type Actor,
} from '@/services/workflow';

const scene = JSON.parse(
  readFileSync(resolve(__dirname, '../../public/data/scene.json'), 'utf-8'),
) as Scene;

const index = indexScene(scene);

/* ------------------------------------------------------------------ */
/* Scena                                                               */
/* ------------------------------------------------------------------ */

describe('scena', () => {
  it('ma komplet klatek zapowiedziany w metadanych', () => {
    expect(scene.frames).toHaveLength(scene.meta.frames);
    expect(scene.frames.length).toBeGreaterThan(90);
  });

  /**
   * Kotwica regresyjna.
   *
   * Aplikacja przelicza IZZ samodzielnie dla kazdej godziny, bo zbior
   * `dynamic_risk_latest.csv` jest tylko jednym zdjeciem stanu. Zeby ten
   * rachunek nie rozjechal sie z notatnikiem `03_dynamic_risk.py`, klatka
   * odpowiadajaca chwili notatnika musi dawac dokladnie te sama wartosc
   * szczytowa. Jesli ten test padnie, formula w `tools/build_scene.py`
   * przestala odpowiadac formule w notatniku.
   */
  it('klatka notatnika daje ten sam szczyt IZZ co zbior zrodlowy', () => {
    const i = scene.frames.findIndex((f) => f.t === scene.meta.notebookSnapshot);
    expect(i).toBeGreaterThanOrEqual(0);
    const peak = Math.max(...scene.frames[i].risk.map((r) => r[1]));
    expect(peak).toBeCloseTo(82.82, 2);
  });

  it('wagi skladowych IZZ sumuja sie do jednosci', () => {
    const w = scene.meta.weights;
    const sum = w.iwl + w.outage + w.temp + w.telecom + w.rescue;
    expect(sum).toBeCloseTo(1, 6);
  });

  it('kazdy wiersz ryzyka wskazuje gmine znana scenie', () => {
    const unknown = new Set<string>();
    for (const f of scene.frames) {
      for (const r of f.risk) {
        if (!index.gminaByCode.has(r[0])) unknown.add(r[0]);
      }
    }
    expect([...unknown]).toEqual([]);
  });

  it('statystyki sa policzone dla kazdej klatki', () => {
    expect(index.stats).toHaveLength(scene.frames.length);
    expect(Math.max(...index.stats.map((s) => s.maxIzz))).toBeGreaterThan(75);
  });
});

/* ------------------------------------------------------------------ */
/* Skala powagi                                                        */
/* ------------------------------------------------------------------ */

describe('skala IZZ', () => {
  /**
   * Kazdy poziom musi miec wlasna barwe. Przy przechodzeniu na jasna palete
   * odwzorowanie barw skleilo dwa sasiednie poziomy w jeden kolor — mapa
   * przestala rozrozniac stan spokojny od podwyzszonego, a nic tego nie
   * zglosilo. Ten test zamyka te droge.
   */
  it('kazdy poziom ma wlasna barwe', () => {
    const colors = IZZ_LEVELS.map((l) => l.color);
    expect(new Set(colors).size).toBe(IZZ_LEVELS.length);
  });

  it('barwa rosnie wraz z powaga sytuacji', () => {
    expect(izzColor(10)).toBe(IZZ_LEVELS[0].color);
    expect(izzColor(50)).toBe(IZZ_LEVELS[1].color);
    expect(izzColor(70)).toBe(IZZ_LEVELS[2].color);
    expect(izzColor(90)).toBe(IZZ_LEVELS[3].color);
  });

  it('progi sa rozlaczne i uporzadkowane', () => {
    const maxes = IZZ_LEVELS.map((l) => l.max);
    expect([...maxes]).toEqual([...maxes].sort((a, b) => a - b));
  });
});

/* ------------------------------------------------------------------ */
/* Zegar sceny                                                         */
/* ------------------------------------------------------------------ */

describe('odwzorowanie czasu na zegar scienny', () => {
  const count = scene.frames.length;
  const cycleMs = count * MINUTES_PER_FRAME * 60_000;

  /**
   * Klatka wynika z czasu bezwzglednego, a nie z momentu uruchomienia
   * aplikacji. Dzieki temu odswiezenie strony nie cofa przebiegu, a dwie
   * osoby patrzace na aplikacje w tej samej chwili widza to samo.
   */
  it('ta sama chwila daje ta sama klatke niezaleznie od pory uruchomienia', () => {
    const t = Date.UTC(2026, 4, 17, 9, 13, 44);
    expect(liveFrameIndex(count, t)).toBe(liveFrameIndex(count, t));
    expect(liveFrameIndex(count, t)).toBe(liveFrameIndex(count, t + cycleMs));
  });

  it('przebieg wraca do poczatku dopiero po pelnym cyklu', () => {
    const t0 = Date.UTC(2026, 0, 1, 0, 0, 0);
    const seen = new Set<number>();
    for (let k = 0; k < count; k += 1) {
      seen.add(liveFrameIndex(count, t0 + k * MINUTES_PER_FRAME * 60_000));
    }
    expect(seen.size).toBe(count);
  });

  it('klatka zawsze miesci sie w zakresie sceny', () => {
    for (const t of [0, 1, 999, Date.now(), Date.now() + 12_345_678]) {
      const i = liveFrameIndex(count, t);
      expect(i).toBeGreaterThanOrEqual(0);
      expect(i).toBeLessThan(count);
    }
  });

  it('odstep do nastepnej klatki jest dodatni i nie przekracza dlugosci klatki', () => {
    const frameMs = MINUTES_PER_FRAME * 60_000;
    for (const t of [Date.now(), Date.now() + 7_777]) {
      const ms = msToNextFrame(count, t);
      expect(ms).toBeGreaterThan(0);
      expect(ms).toBeLessThanOrEqual(frameMs);
    }
  });
});

/* ------------------------------------------------------------------ */
/* Zakres widocznosci                                                  */
/* ------------------------------------------------------------------ */

const rcb: Actor = {
  id: 'u1', name: 'RCB', role: 'RCB',
  voivodeshipCode: '', gminaCode: '', teamId: '',
};
const wojewoda: Actor = {
  id: 'u2', name: 'WCZK', role: 'wojewoda / WCZK',
  voivodeshipCode: '06', gminaCode: '', teamId: '',
};
const osp: Actor = {
  id: 'u3', name: 'OSP', role: 'OSP',
  voivodeshipCode: '06', gminaCode: '0601001', teamId: 'OSP-TEAM-01',
};

describe('zakres widocznosci', () => {
  /** Widok krajowy pracuje na agregatach — to wymog scenariusza. */
  it('RCB nie widzi listy osob', () => {
    expect(canSeePersonList('RCB')).toBe(false);
    expect(canSeePersonList('gmina')).toBe(true);
    expect(canSeePersonList('OSP')).toBe(true);
    expect(canSeePersonList('koordynator medyczny')).toBe(true);
  });

  it('wojewoda dziala tylko we wlasnym wojewodztwie', () => {
    expect(canActOn(wojewoda, '0601001', '06')).toBe(true);
    expect(canActOn(wojewoda, '0201001', '02')).toBe(false);
  });

  it('zespol OSP dziala tylko we wlasnej gminie', () => {
    expect(canActOn(osp, '0601001', '06')).toBe(true);
    expect(canActOn(osp, '0601002', '06')).toBe(false);
  });

  it('RCB ma zasieg krajowy', () => {
    expect(canActOn(rcb, '0201001', '02')).toBe(true);
  });
});

/* ------------------------------------------------------------------ */
/* Walidacje formularzy                                                */
/* ------------------------------------------------------------------ */

const visitBase = {
  scene_time: scene.frames[0].t,
  person_token: 'PRIO-00001',
  category: 'home_oxygen',
  gmina_code: '0601001',
  gmina_name: 'test',
  team_id: 'OSP-TEAM-01',
  result: 'contact_confirmed',
  destination: '',
  autonomy_hours_left: 3,
  notes: '',
  offline_sync_id: '',
  capture_mode: 'online',
};

describe('wynik wizyty kontrolnej', () => {
  it('ewakuacja wymaga miejsca docelowego', () => {
    const bad = validateVisit({ ...visitBase, result: 'evacuation' }, osp, new Set());
    expect(bad.ok).toBe(false);
    const good = validateVisit(
      { ...visitBase, result: 'evacuation', destination: 'HP-0001' },
      osp,
      new Set(),
    );
    expect(good.ok).toBe(true);
  });

  it('miejsce docelowe bez ewakuacji jest bledem', () => {
    const r = validateVisit({ ...visitBase, destination: 'HP-0001' }, osp, new Set());
    expect(r.ok).toBe(false);
  });

  it('RCB nie zapisze wyniku wizyty', () => {
    expect(validateVisit(visitBase, rcb, new Set()).ok).toBe(false);
  });

  it('zespol nie zapisze wyniku dla osoby spoza przydzialu', () => {
    const r = validateVisit(visitBase, osp, new Set(['PRIO-99999']));
    expect(r.ok).toBe(false);
  });

  /**
   * Urzadzenie terenowe nadaje identyfikator przed wysylka. Ta sama paczka
   * wyslana dwa razy po odzyskaniu lacznosci nie moze utworzyc drugiej wizyty.
   */
  it('powtorzona paczka z trybu terenowego nie tworzy drugiej wizyty', () => {
    const a = { offline_sync_id: 'sync-1', created_at: new Date('2026-01-16T10:00:00Z') };
    const b = { offline_sync_id: 'sync-1', created_at: new Date('2026-01-16T10:05:00Z') };
    const c = { offline_sync_id: 'sync-2', created_at: new Date('2026-01-16T10:06:00Z') };
    const out = dedupeVisits([a, b, c]);
    expect(out).toHaveLength(2);
    expect(out).toContain(b);
    expect(out).not.toContain(a);
  });

  it('zapisy bez identyfikatora synchronizacji nie sa scalane', () => {
    const a = { offline_sync_id: '', created_at: new Date('2026-01-16T10:00:00Z') };
    const b = { offline_sync_id: '', created_at: new Date('2026-01-16T10:01:00Z') };
    expect(dedupeVisits([a, b])).toHaveLength(2);
  });
});

const reportBase = {
  scene_time: scene.frames[0].t,
  heating_point_id: 'HP-0001',
  gmina_code: '0601001',
  gmina_name: 'test',
  voivodeship_code: '06',
  status: 'open',
  occupancy: 10,
  capacity: 100,
  needs_food: false,
  needs_medical_support: false,
  needs_generator: false,
  fuel_hours_remaining: 8,
  comment: '',
  checklist_gaps: '',
  offline_sync_id: '',
  capture_mode: 'online',
};

describe('raport z punktu grzewczego', () => {
  it('poprawny raport przechodzi', () => {
    expect(validateHeatingReport(reportBase, osp).ok).toBe(true);
  });

  it('oblozenie ponad pojemnosc wymaga komentarza', () => {
    const bad = { ...reportBase, occupancy: 140 };
    expect(validateHeatingReport(bad, osp).ok).toBe(false);
    const good = { ...bad, comment: 'Przyjeto mieszkancow z sasiedniej gminy po zamknieciu punktu.' };
    expect(validateHeatingReport(good, osp).ok).toBe(true);
  });

  it('oblozenie ujemne jest bledem', () => {
    expect(validateHeatingReport({ ...reportBase, occupancy: -1 }, osp).ok).toBe(false);
  });

  it('otwarcie punktu wymaga odhaczonej checklisty', () => {
    const bad = { ...reportBase, checklist_gaps: 'heat,power,co,water' };
    expect(validateHeatingReport(bad, osp).ok).toBe(false);
  });
});

describe('kampania ostrzegawcza SPO-3', () => {
  const full =
    'UWAGA. Brak zasilania. Uruchomiono punkty grzewcze w budynku szkoly. ' +
    'Zabierz leki i dokumenty. Nie ogrzewaj mieszkania grillem — grozi zatruciem czadem. ' +
    'Sprawdz sasiadow, zwlaszcza osoby starsze. W razie zagrozenia zycia dzwon 112. ' +
    'Aktualizacja o 18:00.';

  it('pelny komunikat zawiera wszystkie wymagane elementy', () => {
    expect(missingMessageParts(full)).toEqual([]);
  });

  it('brak numeru alarmowego jest wykrywany', () => {
    expect(missingMessageParts(full.replace('112', 'sluzby'))).toContain('numer alarmowy');
  });

  it('zbyt krotki komunikat nie przechodzi', () => {
    const r = validateCampaign(
      {
        scene_time: scene.frames[0].t,
        message_text: 'Krotko.',
        channels: 'RSO',
        target_gminas: '0601001',
        target_gmina_count: 1,
        target_population: 100,
        low_coverage_gminas: 0,
        approval_status: 'zatwierdzona',
        language: 'pl',
        scope: 'krajowy',
      },
      rcb,
    );
    expect(r.ok).toBe(false);
  });

  it('kanaly sieciowe sa oznaczane jako nieskuteczne bez zasiegu', () => {
    expect(uselessChannels(['RSO', 'SMS', 'local_radio'], 5)).toEqual(['RSO', 'SMS']);
    expect(uselessChannels(['RSO', 'SMS', 'local_radio'], 0)).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* Drobiazgi                                                           */
/* ------------------------------------------------------------------ */

describe('formatowanie i progi', () => {
  it('skraca wygenerowane nazwy gmin', () => {
    expect(shortGminaName('gmina dolnośląskie-południowy-01-01')).toBe(
      'dolnośląskie południowy 01 01',
    );
  });

  it('progi pilnosci i lacznosci sa takie jak w scenariuszu', () => {
    expect(AUTONOMY_URGENT_H).toBe(2);
    expect(COVERAGE_BLACKOUT).toBeCloseTo(0.2, 6);
  });
});
