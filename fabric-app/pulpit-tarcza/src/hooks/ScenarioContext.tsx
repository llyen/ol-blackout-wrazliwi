import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import {
  indexScene,
  liveFrameIndex,
  msToNextFrame,
  type Scene,
  type SceneIndex,
} from '@/data/model';
import { useAuth } from '@/hooks/AuthContext';
import {
  listAssignments,
  listCampaigns,
  listDecisions,
  listReports,
  listVisits,
  type Actor,
  type AlertCampaignRecord,
  type GeneratorAssignmentRecord,
  type HeatingReportRecord,
  type NationalDecisionRecord,
  type UserRole,
  type WelfareVisitRecord,
} from '@/services/workflow';

interface ScenarioValue {
  index: SceneIndex | null;
  loading: boolean;
  error: string | null;
  /** Numer klatki, którą pokazują ekrany. */
  frame: number;
  /** Chwila scenariusza odpowiadająca klatce (ISO 8601). */
  frameTime: string;
  setFrame: (i: number) => void;
  /** Czy klatka jest wyliczana z zegara ściennego. */
  live: boolean;
  setLive: (v: boolean) => void;
  actor: Actor;
  setRole: (role: UserRole) => void;
  setVoivodeship: (code: string) => void;
  setGmina: (code: string) => void;
  setTeam: (id: string) => void;
  /** Tryb terenowy — zapisy trafiają do kolejki synchronizacji. */
  offline: boolean;
  setOffline: (v: boolean) => void;
  decisions: NationalDecisionRecord[];
  assignments: GeneratorAssignmentRecord[];
  visits: WelfareVisitRecord[];
  reports: HeatingReportRecord[];
  campaigns: AlertCampaignRecord[];
  refresh: () => Promise<void>;
  writebackError: string | null;
}

const ScenarioContext = createContext<ScenarioValue | undefined>(undefined);

const ROLE_KEY = 'tarcza.role';
const VOIV_KEY = 'tarcza.voivodeship';
const GMINA_KEY = 'tarcza.gmina';
const TEAM_KEY = 'tarcza.team';

export function ScenarioProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [index, setIndex] = useState<SceneIndex | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [frame, setFrameState] = useState(0);
  const [live, setLiveState] = useState(true);
  const [offline, setOffline] = useState(false);
  const [role, setRoleState] = useState<UserRole>(
    () => (localStorage.getItem(ROLE_KEY) as UserRole) || 'RCB',
  );
  const [voivodeship, setVoivodeshipState] = useState(
    () => localStorage.getItem(VOIV_KEY) || '',
  );
  const [gmina, setGminaState] = useState(() => localStorage.getItem(GMINA_KEY) || '');
  const [team, setTeamState] = useState(() => localStorage.getItem(TEAM_KEY) || '');
  const [decisions, setDecisions] = useState<NationalDecisionRecord[]>([]);
  const [assignments, setAssignments] = useState<GeneratorAssignmentRecord[]>([]);
  const [visits, setVisits] = useState<WelfareVisitRecord[]>([]);
  const [reports, setReports] = useState<HeatingReportRecord[]>([]);
  const [campaigns, setCampaigns] = useState<AlertCampaignRecord[]>([]);
  const [writebackError, setWritebackError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${import.meta.env.BASE_URL}data/scene.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`Nie udało się wczytać sceny (HTTP ${r.status}).`);
        return r.json() as Promise<Scene>;
      })
      .then((scene) => {
        if (cancelled) return;
        const idx = indexScene(scene);
        setIndex(idx);
        setFrameState(liveFrameIndex(idx.scene.frames.length));
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * Zegar sceny.
   *
   * Klatka jest **liczona z bieżącego czasu**, a nie zwiększana licznikiem.
   * Dzięki temu przebieg nie rozjeżdża się, gdy przeglądarka uśpi zakładkę,
   * a odświeżenie strony nie cofa demonstracji do początku. Odstęp jest
   * wyliczany do najbliższego przeskoku, więc zmiana następuje równo z zegarem.
   */
  useEffect(() => {
    if (!live || !index) return;
    const count = index.scene.frames.length;
    let stopped = false;

    const tick = () => {
      if (stopped) return;
      setFrameState(liveFrameIndex(count));
      timer.current = window.setTimeout(tick, msToNextFrame(count) + 50);
    };
    setFrameState(liveFrameIndex(count));
    timer.current = window.setTimeout(tick, msToNextFrame(count) + 50);

    return () => {
      stopped = true;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [live, index]);

  const refresh = useCallback(async () => {
    try {
      const [d, a, v, r, c] = await Promise.all([
        listDecisions(),
        listAssignments(),
        listVisits(),
        listReports(),
        listCampaigns(),
      ]);
      setDecisions(d);
      setAssignments(a);
      setVisits(v);
      setReports(r);
      setCampaigns(c);
      setWritebackError(null);
    } catch (e: unknown) {
      setWritebackError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const setFrame = useCallback((i: number) => {
    setLiveState(false);
    setFrameState(i);
  }, []);

  const setLive = useCallback(
    (v: boolean) => {
      setLiveState(v);
      if (v && index) setFrameState(liveFrameIndex(index.scene.frames.length));
    },
    [index],
  );

  const setRole = useCallback((r: UserRole) => {
    setRoleState(r);
    localStorage.setItem(ROLE_KEY, r);
  }, []);

  const setVoivodeship = useCallback((code: string) => {
    setVoivodeshipState(code);
    localStorage.setItem(VOIV_KEY, code);
  }, []);

  const setGmina = useCallback((code: string) => {
    setGminaState(code);
    localStorage.setItem(GMINA_KEY, code);
  }, []);

  const setTeam = useCallback((id: string) => {
    setTeamState(id);
    localStorage.setItem(TEAM_KEY, id);
  }, []);

  const actor: Actor = useMemo(
    () => ({
      id: user?.id ?? 'local-user',
      name: user?.name ?? user?.email ?? 'Użytkownik demonstracyjny',
      role,
      voivodeshipCode: voivodeship,
      gminaCode: gmina,
      teamId: team,
    }),
    [user, role, voivodeship, gmina, team],
  );

  const frameTime = index?.scene.frames[frame]?.t ?? '';

  const value: ScenarioValue = useMemo(
    () => ({
      index,
      loading,
      error,
      frame,
      frameTime,
      setFrame,
      live,
      setLive,
      actor,
      setRole,
      setVoivodeship,
      setGmina,
      setTeam,
      offline,
      setOffline,
      decisions,
      assignments,
      visits,
      reports,
      campaigns,
      refresh,
      writebackError,
    }),
    [
      index,
      loading,
      error,
      frame,
      frameTime,
      setFrame,
      live,
      setLive,
      actor,
      setRole,
      setVoivodeship,
      setGmina,
      setTeam,
      offline,
      decisions,
      assignments,
      visits,
      reports,
      campaigns,
      refresh,
      writebackError,
    ],
  );

  return <ScenarioContext.Provider value={value}>{children}</ScenarioContext.Provider>;
}

export function useScenario(): ScenarioValue {
  const ctx = useContext(ScenarioContext);
  if (!ctx) throw new Error('useScenario musi być użyte wewnątrz ScenarioProvider');
  return ctx;
}
