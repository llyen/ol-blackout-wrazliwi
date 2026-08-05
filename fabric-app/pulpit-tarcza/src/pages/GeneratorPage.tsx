import { useMemo, useState } from 'react';

import {
  AUTONOMY_URGENT_H,
  formatNumber,
  formatTime,
  IZZ_CRITICAL,
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
  Toast,
  downloadCsv,
  inputClass,
  type MapPoint,
} from '@/components/ui';
import { useScenario } from '@/hooks/ScenarioContext';
import {
  ASSIGNING_ROLES,
  powerShortfall,
  saveAssignment,
  validateAssignment,
  type GeneratorAssignmentDraft,
} from '@/services/workflow';

/** Przybliżenie odległości w kilometrach — wystarczające w skali województwa. */
function km(lat1: number, lon1: number, lat2: number, lon2: number): number {
  return Math.hypot((lon2 - lon1) * 68.5, (lat2 - lat1) * 111.2);
}

/**
 * Średnia prędkość przejazdu zimą po drogach lokalnych. Świadomie niska —
 * scenariusz zakłada zawieje i drogi nieprzejezdne.
 */
const AVG_SPEED_KMH = 38;

interface Candidate {
  targetType: 'heating_point' | 'care_facility';
  targetId: string;
  targetName: string;
  gminaCode: string;
  gminaName: string;
  voivCode: string;
  lat: number;
  lon: number;
  needKw: number;
  /** Osoby wrażliwe, których dotyczy przydział. */
  covered: number;
  /** Uzasadnienie pilności — pokazywane w tabeli. */
  reason: string;
  izz: number;
  urgency: number;
}

export function GeneratorPage() {
  const { index, frame, frameTime, actor, assignments, refresh } = useScenario();
  const [selected, setSelected] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [draft, setDraft] = useState<GeneratorAssignmentDraft | null>(null);

  const scope = actor.role === 'RCB' ? '' : actor.voivodeshipCode;

  const view = useMemo(() => {
    if (!index) return null;
    const f = index.scene.frames[frame];
    if (!f) return null;
    const risk = riskMap(f);
    const hpState = index.hpStateAt(frame);
    const assigned = new Set(assignments.map((a) => a.target_id));

    const inScope = (gminaCode: string) => {
      const g = index.gminaByCode.get(gminaCode);
      return !scope || g?.v === scope;
    };

    const candidates: Candidate[] = [];

    // Punkty grzewcze zgłaszające potrzebę agregatu albo wskazane przez model
    // i pozbawione własnego źródła zasilania.
    for (const hp of index.scene.heatingPoints) {
      if (!inScope(hp.g)) continue;
      const g = index.gminaByCode.get(hp.g);
      if (!g) continue;
      const state = hpState.get(hp.id);
      const reported = state?.[7] === 1;
      if (!reported && !(hp.sel && !hp.gen)) continue;
      const r = risk.get(hp.g);
      const izz = r?.[1] ?? 0;
      candidates.push({
        targetType: 'heating_point',
        targetId: hp.id,
        targetName: `${hp.type} ${hp.id}`,
        gminaCode: hp.g,
        gminaName: shortGminaName(g.n),
        voivCode: g.v,
        lat: Number(hp.lat),
        lon: Number(hp.lon),
        needKw: hp.kw,
        covered: hp.covered || Math.round(hp.cap * 0.6),
        reason: reported
          ? 'Punkt zgłosił potrzebę agregatu'
          : 'Wskazany przez model, bez własnego zasilania',
        izz,
        urgency: (reported ? 200 : 0) + izz + (hp.covered ?? 0) / 100,
      });
    }

    // Placówki opieki, którym kończy się autonomia agregatu.
    for (const fac of index.scene.facilities) {
      if (!inScope(fac.g)) continue;
      const g = index.gminaByCode.get(fac.g);
      if (!g) continue;
      const r = risk.get(fac.g);
      if (!r || r[3] <= 0) continue;
      const left = fac.gen ? fac.auto - r[2] : 0;
      if (fac.gen && left > AUTONOMY_URGENT_H) continue;
      candidates.push({
        targetType: 'care_facility',
        targetId: fac.id,
        targetName: `${fac.type} ${fac.id}`,
        gminaCode: fac.g,
        gminaName: shortGminaName(g.n),
        voivCode: g.v,
        lat: Number(fac.lat),
        lon: Number(fac.lon),
        needKw: fac.kw,
        covered: fac.occ,
        reason: fac.gen
          ? `Autonomia agregatu wyczerpana (${formatNumber(Math.max(0, left))} h)`
          : 'Placówka bez agregatu w gminie z awarią',
        izz: r[1],
        urgency: 300 + r[1] + fac.occ / 10,
      });
    }

    candidates.sort((a, b) => b.urgency - a.urgency);

    const pool = index.scene.generators.filter(
      (gen) => (!scope || gen.v === scope) && gen.status === 'available',
    );

    /** Agregat rekomendowany: wystarczająca moc, najkrótszy dojazd. */
    const recommend = (c: Candidate) => {
      const fits = pool.filter((gen) => gen.kw >= c.needKw);
      const from = fits.length > 0 ? fits : pool;
      let best = null as (typeof pool)[number] | null;
      let bestD = Number.POSITIVE_INFINITY;
      for (const gen of from) {
        const d = km(c.lat, c.lon, Number(gen.lat), Number(gen.lon));
        if (d < bestD) {
          bestD = d;
          best = gen;
        }
      }
      return best
        ? { gen: best, distanceKm: bestD, etaMin: Math.round((bestD / AVG_SPEED_KMH) * 60) }
        : null;
    };

    const rows = candidates.slice(0, 40).map((c) => ({
      c,
      rec: recommend(c),
      done: assigned.has(c.targetId),
    }));

    const points: MapPoint[] = rows.map(({ c }) => ({
      id: c.targetId,
      lat: c.lat,
      lon: c.lon,
      value: c.izz,
      label: c.targetName,
      detail: `${c.gminaName} · ${formatNumber(c.needKw)} kW · ${c.reason}`,
      alarm: c.izz >= IZZ_CRITICAL,
    }));

    return {
      rows,
      points,
      pool,
      recommend,
      openPool: pool.length,
      totalKw: pool.reduce((s, g) => s + g.kw, 0),
      covered: rows.filter((r) => r.done).reduce((s, r) => s + r.c.covered, 0),
      pending: rows.filter((r) => !r.done).length,
    };
  }, [index, frame, scope, assignments]);

  if (!index || !view) return <EmptyState text="Wczytywanie sceny…" />;

  const canAssign = ASSIGNING_ROLES.includes(actor.role);

  const openForm = (row: (typeof view.rows)[number], status: GeneratorAssignmentDraft['status']) => {
    const { c, rec } = row;
    setDraft({
      scene_time: frameTime,
      generator_id: rec?.gen.id ?? '',
      target_type: c.targetType,
      target_id: c.targetId,
      target_name: c.targetName,
      gmina_code: c.gminaCode,
      gmina_name: c.gminaName,
      voivodeship_code: c.voivCode,
      power_kw: rec?.gen.kw ?? 0,
      power_need_kw: c.needKw,
      eta_minutes: rec?.etaMin ?? 0,
      covered_vulnerable: c.covered,
      status,
      comment: '',
      recommended_generator_id: rec?.gen.id ?? '',
    });
    setErrors([]);
    setFormOpen(true);
  };

  const submit = async () => {
    if (!draft) return;
    const v = validateAssignment(draft, actor);
    if (!v.ok) {
      setErrors(v.errors);
      return;
    }
    try {
      const saved = await saveAssignment(draft, actor);
      await refresh();
      setFormOpen(false);
      setToast(`Zapisano przydział ${saved.assignment_id}.`);
    } catch (e) {
      setErrors([e instanceof Error ? e.message : String(e)]);
    }
  };

  const exportPlan = () => {
    const head =
      'cel;rodzaj;gmina;zapotrzebowanie_kW;agregat;moc_kW;dojazd_min;osoby;uzasadnienie\n';
    const body = view.rows
      .map(({ c, rec }) =>
        [
          c.targetId,
          c.targetType,
          c.gminaName,
          c.needKw,
          rec?.gen.id ?? '',
          rec?.gen.kw ?? '',
          rec?.etaMin ?? '',
          c.covered,
          c.reason,
        ].join(';'),
      )
      .join('\n');
    downloadCsv(`plan-agregatow-${frameTime.slice(0, 13)}.csv`, head + body);
  };

  const shortfall = draft ? powerShortfall(draft) : 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          label="Cele oczekujące"
          value={view.pending}
          hint="Punkty grzewcze i placówki bez zatwierdzonego przydziału."
          emphasis={view.pending > 0}
        />
        <KpiCard
          label="Agregaty dostępne"
          value={view.openPool}
          higherIsWorse={false}
          hint="Stan magazynowy w zakresie roli."
        />
        <KpiCard
          label="Moc dostępna"
          value={view.totalKw}
          unit=" kW"
          higherIsWorse={false}
          hint="Suma mocy agregatów w stanie „available”."
        />
        <KpiCard
          label="Osoby objęte przydziałem"
          value={view.covered}
          higherIsWorse={false}
          hint="Obłożenie celów, dla których zapadła decyzja."
        />
      </div>

      {!canAssign && (
        <div className="rounded-lg bg-amber-50 px-4 py-2.5 text-xs text-amber-700 ring-1 ring-amber-600/30">
          Rola <span className="font-semibold">{actor.role}</span> ma wgląd w plan, ale przydział
          agregatu zatwierdza wojewoda albo WCZK. Przełącz rolę w nagłówku, żeby zobaczyć ścieżkę
          decyzyjną.
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
        <Panel
          title="Cele wymagające zasilania"
          subtitle={`Stan na ${formatTime(frameTime)}`}
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
          title="Plan przydziału"
          subtitle="Kolejność wynika z pilności: zgłoszona potrzeba, wyczerpana autonomia, IZŻ gminy"
          right={
            <Button variant="default" onClick={exportPlan}>
              Eksport CSV
            </Button>
          }
        >
          {view.rows.length === 0 ? (
            <EmptyState text="Żaden cel nie zgłasza potrzeby zasilania w tej chwili." />
          ) : (
            <div className="max-h-[420px] overflow-y-auto">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-white text-[10px] uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="py-2 pr-2">Cel</th>
                    <th className="py-2 pr-2">Zapotrz.</th>
                    <th className="py-2 pr-2">Agregat</th>
                    <th className="py-2 pr-2">Dojazd</th>
                    <th className="py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {view.rows.map((row) => {
                    const { c, rec, done } = row;
                    const weak = rec ? rec.gen.kw < c.needKw : false;
                    return (
                      <tr
                        key={c.targetId}
                        className={`align-top transition-colors ${
                          selected === c.targetId ? 'bg-gov/10' : 'hover:bg-slate-50'
                        }`}
                        onMouseEnter={() => setSelected(c.targetId)}
                      >
                        <td className="py-2 pr-2">
                          <div className="font-medium text-slate-900">{c.targetName}</div>
                          <div className="text-[11px] text-slate-500">
                            {c.gminaName} · IZŻ {formatNumber(c.izz)}
                          </div>
                          <div className="mt-0.5 text-[11px] text-slate-500">{c.reason}</div>
                        </td>
                        <td className="py-2 pr-2 tabular-nums text-slate-700">
                          {formatNumber(c.needKw)} kW
                          <div className="text-[11px] text-slate-500">{c.covered} osób</div>
                        </td>
                        <td className="py-2 pr-2">
                          {rec ? (
                            <>
                              <div className="tabular-nums text-slate-900">{rec.gen.id}</div>
                              <div
                                className={`text-[11px] tabular-nums ${weak ? 'text-amber-700' : 'text-slate-500'}`}
                              >
                                {rec.gen.kw} kW {weak ? '· za słaby' : ''}
                              </div>
                            </>
                          ) : (
                            <span className="text-amber-700">brak w puli</span>
                          )}
                        </td>
                        <td className="py-2 pr-2 tabular-nums text-slate-700">
                          {rec ? (
                            <>
                              {rec.etaMin} min
                              <div className="text-[11px] text-slate-500">
                                {formatNumber(Math.round(rec.distanceKm))} km
                              </div>
                            </>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="py-2">
                          {done ? (
                            <Badge className="bg-emerald-50 text-emerald-700 ring-emerald-600/30">
                              zatwierdzony
                            </Badge>
                          ) : (
                            <div className="flex flex-col gap-1">
                              <Button
                                variant="primary"
                                disabled={!canAssign}
                                onClick={() => openForm(row, 'zatwierdzony')}
                                className="!px-2 !py-1 !text-[11px]"
                              >
                                Zatwierdź
                              </Button>
                              <Button
                                variant="default"
                                disabled={!canAssign}
                                onClick={() => openForm(row, 'zmieniony')}
                                className="!px-2 !py-1 !text-[11px]"
                              >
                                Zmień
                              </Button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      <Panel
        title="Zatwierdzone przydziały"
        subtitle={`${assignments.length} ${assignments.length === 1 ? 'wpis' : 'wpisów'}`}
      >
        {assignments.length === 0 ? (
          <EmptyState text="Brak decyzji o przydziale agregatów." />
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="py-1.5 pr-2">Nr</th>
                <th className="py-1.5 pr-2">Cel</th>
                <th className="py-1.5 pr-2">Agregat</th>
                <th className="py-1.5 pr-2">Moc / potrzeba</th>
                <th className="py-1.5 pr-2">Dojazd</th>
                <th className="py-1.5 pr-2">Status</th>
                <th className="py-1.5">Komentarz</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {assignments.slice(0, 20).map((a) => (
                <tr key={a.id}>
                  <td className="py-1.5 pr-2 tabular-nums text-slate-500">{a.assignment_id}</td>
                  <td className="py-1.5 pr-2 text-slate-900">
                    {a.target_name}
                    <div className="text-[11px] text-slate-500">{a.gmina_name}</div>
                  </td>
                  <td className="py-1.5 pr-2 tabular-nums text-slate-700">{a.generator_id}</td>
                  <td className="py-1.5 pr-2 tabular-nums text-slate-700">
                    {a.power_kw} / {formatNumber(a.power_need_kw)} kW
                    {a.power_kw < a.power_need_kw && (
                      <span className="ml-1 text-amber-700">niedobór</span>
                    )}
                  </td>
                  <td className="py-1.5 pr-2 tabular-nums text-slate-700">{a.eta_minutes} min</td>
                  <td className="py-1.5 pr-2">
                    <Badge
                      className={
                        a.status === 'zatwierdzony'
                          ? 'bg-emerald-50 text-emerald-700 ring-emerald-600/30'
                          : a.status === 'odrzucony'
                            ? 'bg-red-50 text-red-700 ring-red-600/30'
                            : 'bg-amber-50 text-amber-700 ring-amber-600/30'
                      }
                    >
                      {a.status}
                    </Badge>
                  </td>
                  <td className="py-1.5 text-slate-500">{a.comment || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Modal open={formOpen} title="Przydział agregatu" onClose={() => setFormOpen(false)} wide>
        {draft && (
          <div className="space-y-4">
            <div className="rounded-lg bg-slate-50 p-3 text-xs leading-relaxed text-slate-500 ring-1 ring-slate-200">
              Cel: <span className="font-semibold text-slate-900">{draft.target_name}</span> w
              gminie {draft.gmina_name}. Zapotrzebowanie{' '}
              {formatNumber(draft.power_need_kw)} kW, przydział obejmuje{' '}
              {draft.covered_vulnerable} osób. Model rekomenduje agregat{' '}
              {draft.recommended_generator_id || '—'}.
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Agregat">
                <select
                  value={draft.generator_id}
                  onChange={(e) => {
                    const gen = index.generatorById.get(e.target.value);
                    setDraft({
                      ...draft,
                      generator_id: e.target.value,
                      power_kw: gen?.kw ?? draft.power_kw,
                    });
                  }}
                  className={inputClass}
                >
                  <option value="">— wskaż agregat —</option>
                  {view.pool.slice(0, 120).map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.id} · {g.kw} kW · {g.fuel} · {g.mob}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="Status decyzji">
                <select
                  value={draft.status}
                  onChange={(e) => setDraft({ ...draft, status: e.target.value })}
                  className={inputClass}
                >
                  <option value="zatwierdzony">Zatwierdzam plan</option>
                  <option value="zmieniony">Zmieniam przydział</option>
                  <option value="odrzucony">Odrzucam</option>
                  <option value="wniosek_o_wiecej">Wnioskuję o dodatkowe siły</option>
                </select>
              </Field>

              <Field label="Moc agregatu" hint="kW">
                <input
                  type="number"
                  value={draft.power_kw}
                  onChange={(e) => setDraft({ ...draft, power_kw: Number(e.target.value) })}
                  className={inputClass}
                />
              </Field>

              <Field label="Czas dojazdu" hint="minuty, zakres 0–1440">
                <input
                  type="number"
                  value={draft.eta_minutes}
                  onChange={(e) => setDraft({ ...draft, eta_minutes: Number(e.target.value) })}
                  className={inputClass}
                />
              </Field>
            </div>

            {shortfall > 0 && (
              <p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-700 ring-1 ring-amber-600/30">
                Moc agregatu jest o {formatNumber(shortfall)} kW niższa od zapotrzebowania. To nie
                blokuje decyzji — słabszy agregat może utrzymać samo ogrzewanie. Warto to zapisać w
                komentarzu, żeby zmiana była czytelna w rozliczeniu.
              </p>
            )}

            <Field
              label="Komentarz"
              hint={
                draft.status === 'zmieniony' || draft.status === 'odrzucony'
                  ? 'Wymagany przy zmianie i odrzuceniu, minimum 10 znaków'
                  : 'Opcjonalny'
              }
            >
              <textarea
                value={draft.comment}
                onChange={(e) => setDraft({ ...draft, comment: e.target.value })}
                rows={3}
                className={inputClass}
                placeholder="Dlaczego decyzja odbiega od rekomendacji modelu."
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
                Zapisz decyzję
              </Button>
            </div>
          </div>
        )}
      </Modal>

      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}
