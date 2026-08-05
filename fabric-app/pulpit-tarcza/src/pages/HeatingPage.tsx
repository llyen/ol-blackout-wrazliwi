import { useMemo, useState } from 'react';

import {
  formatNumber,
  formatTime,
  IZZ_LEGEND,
  izzColor,
  riskMap,
  shortGminaName,
} from '@/data/model';
import {
  Badge,
  Button,
  CountryMap,
  EmptyState,
  Field,
  KpiCard,
  Modal,
  Panel,
  Sparkline,
  Toast,
  inputClass,
  type MapPoint,
} from '@/components/ui';
import { useScenario } from '@/hooks/ScenarioContext';
import {
  HEATING_ROLES,
  OPENING_CHECKLIST,
  saveHeatingReport,
  validateHeatingReport,
  type HeatingReportDraft,
} from '@/services/workflow';

const STATUS_LABELS: Record<string, string> = {
  planned: 'Planowany',
  open: 'Otwarty',
  full: 'Zapełniony',
  closed: 'Zamknięty',
};

/** Poniżej tego zapasu paliwa punkt wymaga dowozu. */
const FUEL_ALERT_H = 6;

export function HeatingPage() {
  const { index, frame, frameTime, actor, reports, refresh, offline } = useScenario();
  const [selected, setSelected] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [draft, setDraft] = useState<HeatingReportDraft | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());

  const scope = actor.role === 'RCB' ? '' : actor.voivodeshipCode;

  const view = useMemo(() => {
    if (!index) return null;
    const f = index.scene.frames[frame];
    if (!f) return null;
    const risk = riskMap(f);
    const state = index.hpStateAt(frame);

    // Raport użytkownika ma pierwszeństwo przed stanem ze sceny.
    const latestOwn = new Map<string, (typeof reports)[number]>();
    for (const r of reports) {
      const prev = latestOwn.get(r.heating_point_id);
      if (!prev || new Date(r.created_at) > new Date(prev.created_at))
        latestOwn.set(r.heating_point_id, r);
    }

    const rows = index.scene.heatingPoints
      .filter((hp) => {
        const g = index.gminaByCode.get(hp.g);
        if (!g) return false;
        if (actor.gminaCode) return hp.g === actor.gminaCode;
        if (scope) return g.v === scope;
        return true;
      })
      .map((hp) => {
        const g = index.gminaByCode.get(hp.g);
        const s = state.get(hp.id);
        const own = latestOwn.get(hp.id);
        const status = own?.status ?? s?.[2] ?? (hp.sel ? 'planned' : 'closed');
        const occupancy = own?.occupancy ?? s?.[3] ?? 0;
        const capacity = own?.capacity ?? s?.[4] ?? hp.cap;
        return {
          hp,
          gminaName: shortGminaName(g?.n ?? hp.g),
          voivCode: g?.v ?? '',
          izz: risk.get(hp.g)?.[1] ?? 0,
          status,
          occupancy,
          capacity,
          fill: capacity > 0 ? occupancy / capacity : 0,
          needsFood: own ? own.needs_food : s?.[5] === 1,
          needsMedical: own ? own.needs_medical_support : s?.[6] === 1,
          needsGenerator: own ? own.needs_generator : s?.[7] === 1,
          fuel: own?.fuel_hours_remaining ?? null,
          reported: Boolean(own ?? s),
        };
      })
      .sort((a, b) => {
        const rank = (r: typeof a) =>
          (r.status === 'full' ? 300 : r.status === 'open' ? 200 : r.hp.sel ? 100 : 0) + r.fill * 50;
        return rank(b) - rank(a);
      });

    const active = rows.filter((r) => r.status === 'open' || r.status === 'full');
    const points: MapPoint[] = rows.slice(0, 300).map((r) => ({
      id: r.hp.id,
      lat: Number(r.hp.lat),
      lon: Number(r.hp.lon),
      value: r.izz,
      label: `${r.hp.type} ${r.hp.id}`,
      detail: `${r.gminaName} · ${STATUS_LABELS[r.status] ?? r.status} · ${r.occupancy}/${r.capacity} miejsc`,
      alarm: r.fill >= 0.95,
    }));

    return {
      rows,
      active,
      points,
      occupancy: active.reduce((s, r) => s + r.occupancy, 0),
      capacity: active.reduce((s, r) => s + r.capacity, 0),
      full: rows.filter((r) => r.fill >= 0.95).length,
      needGen: rows.filter((r) => r.needsGenerator).length,
      latestOwn,
    };
  }, [index, frame, scope, actor.gminaCode, reports]);

  if (!index || !view) return <EmptyState text="Wczytywanie sceny…" />;

  const canWrite = HEATING_ROLES.includes(actor.role);

  const openForm = (row: (typeof view.rows)[number]) => {
    setChecked(new Set(OPENING_CHECKLIST.map((c) => c.key)));
    setDraft({
      scene_time: frameTime,
      heating_point_id: row.hp.id,
      gmina_code: row.hp.g,
      gmina_name: row.gminaName,
      voivodeship_code: row.voivCode,
      status: row.status === 'closed' || row.status === 'planned' ? 'open' : row.status,
      occupancy: row.occupancy,
      capacity: row.capacity,
      needs_food: row.needsFood,
      needs_medical_support: row.needsMedical,
      needs_generator: row.needsGenerator,
      fuel_hours_remaining: row.fuel ?? (row.hp.gen ? 12 : 0),
      comment: '',
      checklist_gaps: '',
      offline_sync_id: '',
      capture_mode: offline ? 'offline' : 'online',
    });
    setErrors([]);
    setFormOpen(true);
  };

  const toggleCheck = (key: string) => {
    const next = new Set(checked);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setChecked(next);
    if (draft) {
      const gaps = OPENING_CHECKLIST.filter((c) => !next.has(c.key)).map((c) => c.key);
      setDraft({ ...draft, checklist_gaps: gaps.join(',') });
    }
  };

  const submit = async () => {
    if (!draft) return;
    const gaps = OPENING_CHECKLIST.filter((c) => !checked.has(c.key)).map((c) => c.key);
    const payload = { ...draft, checklist_gaps: gaps.join(',') };
    const v = validateHeatingReport(payload, actor);
    if (!v.ok) {
      setErrors(v.errors);
      return;
    }
    try {
      const saved = await saveHeatingReport(payload, actor);
      await refresh();
      setFormOpen(false);
      setToast(`Zapisano raport ${saved.report_id}.`);
    } catch (e) {
      setErrors([e instanceof Error ? e.message : String(e)]);
    }
  };

  const over = draft ? draft.occupancy > draft.capacity : false;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <KpiCard
          label="Punkty czynne"
          value={view.active.length}
          higherIsWorse={false}
          hint="Status „otwarty” albo „zapełniony”."
          spark={index.stats.slice(Math.max(0, frame - 23), frame + 1).map((s) => s.openHeatingPoints)}
        />
        <KpiCard
          label="Osoby w punktach"
          value={view.occupancy}
          higherIsWorse={false}
          hint="Suma obłożenia punktów czynnych."
          spark={index.stats.slice(Math.max(0, frame - 23), frame + 1).map((s) => s.occupancy)}
        />
        <KpiCard
          label="Wolne miejsca"
          value={Math.max(0, view.capacity - view.occupancy)}
          higherIsWorse={false}
          hint="Rezerwa w punktach czynnych."
        />
        <KpiCard
          label="Zapełnione"
          value={view.full}
          hint="Powyżej 95% pojemności — otwórz rezerwowy punkt."
          emphasis={view.full > 0}
        />
        <KpiCard
          label="Zgłoszona potrzeba agregatu"
          value={view.needGen}
          hint="Trafia na ekran „Plan agregatów” do decyzji wojewody."
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <Panel
          title="Rozmieszczenie punktów"
          subtitle={`${view.rows.length} punktów w zakresie roli · stan na ${formatTime(frameTime)}`}
        >
          <CountryMap
            points={view.points}
            colorFor={izzColor}
            legend={IZZ_LEGEND}
            onSelect={setSelected}
            selectedId={selected}
            height={400}
            highlightRegions={scope ? [index.voivByCode.get(scope)?.n ?? ''] : undefined}
          />
        </Panel>

        <Panel
          title="Stan punktów"
          subtitle="Kolejność: zapełnione, czynne, wskazane przez model"
        >
          <div className="max-h-[420px] overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-white text-[10px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="py-2 pr-2">Punkt</th>
                  <th className="py-2 pr-2">Status</th>
                  <th className="py-2 pr-2">Obłożenie</th>
                  <th className="py-2 pr-2">Potrzeby</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {view.rows.slice(0, 120).map((row) => (
                  <tr
                    key={row.hp.id}
                    className={`align-top transition-colors ${
                      selected === row.hp.id ? 'bg-gov/10' : 'hover:bg-slate-50'
                    }`}
                    onMouseEnter={() => setSelected(row.hp.id)}
                  >
                    <td className="py-2 pr-2">
                      <div className="font-medium text-slate-900">
                        {row.hp.type} {row.hp.id}
                      </div>
                      <div className="text-[11px] text-slate-500">
                        {row.gminaName}
                        {row.hp.sel && ' · wskazany przez model'}
                      </div>
                    </td>
                    <td className="py-2 pr-2">
                      <Badge
                        className={
                          row.status === 'full'
                            ? 'bg-red-50 text-red-700 ring-red-600/30'
                            : row.status === 'open'
                              ? 'bg-emerald-50 text-emerald-700 ring-emerald-600/30'
                              : 'bg-slate-200 text-slate-500 ring-slate-300'
                        }
                      >
                        {STATUS_LABELS[row.status] ?? row.status}
                      </Badge>
                    </td>
                    <td className="py-2 pr-2">
                      <div className="tabular-nums text-slate-700">
                        {row.occupancy} / {row.capacity}
                      </div>
                      <div className="mt-1 h-1.5 w-20 overflow-hidden rounded-full bg-slate-50">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${Math.min(100, row.fill * 100)}%`,
                            background: row.fill >= 0.95 ? '#d5233f' : '#0052a5',
                          }}
                        />
                      </div>
                    </td>
                    <td className="py-2 pr-2">
                      <div className="flex flex-wrap gap-1">
                        {row.needsFood && (
                          <Badge className="bg-amber-50 text-amber-700 ring-amber-600/30">
                            żywność
                          </Badge>
                        )}
                        {row.needsMedical && (
                          <Badge className="bg-red-50 text-red-700 ring-red-600/30">
                            medyczne
                          </Badge>
                        )}
                        {row.needsGenerator && (
                          <Badge className="bg-gov/10 text-gov ring-gov/30">
                            agregat
                          </Badge>
                        )}
                        {row.fuel !== null && row.fuel < FUEL_ALERT_H && (
                          <Badge className="bg-red-50 text-red-700 ring-red-600/30">
                            paliwo {formatNumber(row.fuel)} h
                          </Badge>
                        )}
                        {!row.needsFood && !row.needsMedical && !row.needsGenerator && (
                          <span className="text-slate-400">—</span>
                        )}
                      </div>
                    </td>
                    <td className="py-2">
                      <Button
                        variant="primary"
                        disabled={!canWrite}
                        onClick={() => openForm(row)}
                        className="!px-2 !py-1 !text-[11px]"
                      >
                        Raport
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Obłożenie w czasie" subtitle="Suma osób w punktach czynnych">
          <Sparkline
            values={index.stats.map((s) => s.occupancy)}
            marker={frame}
            height={70}
            color="#0052a5"
          />
        </Panel>
        <Panel
          title="Złożone raporty"
          subtitle={`${reports.length} ${reports.length === 1 ? 'wpis' : 'wpisów'}`}
          className="lg:col-span-2"
        >
          {reports.length === 0 ? (
            <EmptyState text="Brak raportów. Raport zapisuje historię obłożenia i potrzeb." />
          ) : (
            <table className="w-full text-left text-xs">
              <thead className="text-[10px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="py-1.5 pr-2">Nr</th>
                  <th className="py-1.5 pr-2">Punkt</th>
                  <th className="py-1.5 pr-2">Status</th>
                  <th className="py-1.5 pr-2">Obłożenie</th>
                  <th className="py-1.5 pr-2">Paliwo</th>
                  <th className="py-1.5">Braki checklisty</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {reports.slice(0, 12).map((r) => (
                  <tr key={r.id}>
                    <td className="py-1.5 pr-2 tabular-nums text-slate-500">{r.report_id}</td>
                    <td className="py-1.5 pr-2 text-slate-900">
                      {r.heating_point_id}
                      <div className="text-[11px] text-slate-500">{r.gmina_name}</div>
                    </td>
                    <td className="py-1.5 pr-2 text-slate-700">
                      {STATUS_LABELS[r.status] ?? r.status}
                    </td>
                    <td className="py-1.5 pr-2 tabular-nums text-slate-700">
                      {r.occupancy} / {r.capacity}
                    </td>
                    <td className="py-1.5 pr-2 tabular-nums text-slate-700">
                      {formatNumber(r.fuel_hours_remaining)} h
                    </td>
                    <td className="py-1.5 text-slate-500">
                      {r.checklist_gaps
                        ? r.checklist_gaps
                            .split(',')
                            .map((k) => OPENING_CHECKLIST.find((c) => c.key === k)?.label ?? k)
                            .join(', ')
                        : 'brak'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      <Modal open={formOpen} title="Raport z punktu grzewczego" onClose={() => setFormOpen(false)} wide>
        {draft && (
          <div className="space-y-4">
            <div className="rounded-lg bg-slate-50 p-3 text-xs leading-relaxed text-slate-500 ring-1 ring-slate-200">
              Punkt <span className="font-semibold text-slate-900">{draft.heating_point_id}</span> w
              gminie {draft.gmina_name}. Raport na chwilę {formatTime(frameTime)}.
              {offline && ' Zapis powstaje w trybie terenowym.'}
            </div>

            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
                Checklista otwarcia
              </p>
              <div className="grid gap-1.5 sm:grid-cols-2">
                {OPENING_CHECKLIST.map((c) => (
                  <label
                    key={c.key}
                    className="flex items-center gap-2 rounded-lg bg-slate-50 px-2.5 py-1.5 text-xs text-slate-700 ring-1 ring-slate-200"
                  >
                    <input
                      type="checkbox"
                      checked={checked.has(c.key)}
                      onChange={() => toggleCheck(c.key)}
                      className="accent-gov"
                    />
                    {c.label}
                  </label>
                ))}
              </div>
              <p className="mt-1.5 text-[11px] text-slate-500">
                Odhaczone: {checked.size} z {OPENING_CHECKLIST.length}. Punkt można otworzyć po
                odhaczeniu co najmniej pięciu pozycji.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Status">
                <select
                  value={draft.status}
                  onChange={(e) => setDraft({ ...draft, status: e.target.value })}
                  className={inputClass}
                >
                  {Object.entries(STATUS_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Zapas paliwa" hint="godziny pracy agregatu">
                <input
                  type="number"
                  value={draft.fuel_hours_remaining}
                  onChange={(e) =>
                    setDraft({ ...draft, fuel_hours_remaining: Number(e.target.value) })
                  }
                  className={inputClass}
                />
              </Field>
              <Field label="Obłożenie" hint={`Pojemność: ${draft.capacity}`}>
                <input
                  type="number"
                  value={draft.occupancy}
                  onChange={(e) => setDraft({ ...draft, occupancy: Number(e.target.value) })}
                  className={inputClass}
                />
              </Field>
              <Field label="Pojemność">
                <input
                  type="number"
                  value={draft.capacity}
                  onChange={(e) => setDraft({ ...draft, capacity: Number(e.target.value) })}
                  className={inputClass}
                />
              </Field>
            </div>

            {over && (
              <p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-700 ring-1 ring-amber-600/30">
                Obłożenie przekracza pojemność. To dopuszczalne w sytuacji nadzwyczajnej, ale
                wymaga komentarza — inaczej nie da się później wytłumaczyć decyzji.
              </p>
            )}

            <div className="flex flex-wrap gap-4">
              {[
                { k: 'needs_food' as const, l: 'Potrzebna żywność' },
                { k: 'needs_medical_support' as const, l: 'Potrzebne wsparcie medyczne' },
                { k: 'needs_generator' as const, l: 'Potrzebny agregat' },
              ].map((f) => (
                <label key={f.k} className="flex items-center gap-2 text-xs text-slate-700">
                  <input
                    type="checkbox"
                    checked={draft[f.k]}
                    onChange={(e) => setDraft({ ...draft, [f.k]: e.target.checked })}
                    className="accent-gov"
                  />
                  {f.l}
                </label>
              ))}
            </div>

            <Field label="Komentarz" hint={`${draft.comment.length} / 600 znaków`}>
              <textarea
                value={draft.comment}
                onChange={(e) => setDraft({ ...draft, comment: e.target.value })}
                rows={3}
                className={inputClass}
                placeholder="Sytuacja w punkcie, przyczyna przekroczenia pojemności, braki."
              />
            </Field>

            {errors.length > 0 && (
              <ul className="space-y-1 rounded-lg bg-red-50 p-3 text-xs text-red-700 ring-1 ring-red-600/30">
                {errors.map((e) => (
                  <li key={e}>• {e}</li>
                ))}
              </ul>
            )}

            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setFormOpen(false)}>
                Anuluj
              </Button>
              <Button variant="primary" onClick={() => void submit()}>
                Zapisz raport
              </Button>
            </div>
          </div>
        )}
      </Modal>

      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}
