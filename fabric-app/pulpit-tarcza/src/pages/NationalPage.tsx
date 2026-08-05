import { useMemo, useState } from 'react';

import {
  CALL_TYPE_LABELS,
  formatNumber,
  formatTime,
  IZZ_CRITICAL,
  IZZ_LEGEND,
  izzColor,
  izzLevel,
  recommendations,
  riskMap,
  shortGminaName,
} from '@/data/model';
import {
  BarList,
  Button,
  CountryMap,
  EmptyState,
  Field,
  KpiCard,
  Modal,
  Panel,
  Sparkline,
  TimelineBars,
  Toast,
  inputClass,
  type MapPoint,
} from '@/components/ui';
import { useScenario } from '@/hooks/ScenarioContext';
import {
  DECISION_TYPES,
  saveNationalDecision,
  validateNationalDecision,
  type NationalDecisionDraft,
} from '@/services/workflow';

/** Ile ostatnich klatek pokazuje iskierka przy wskaźniku. */
const SPARK_WINDOW = 24;

export function NationalPage() {
  const { index, frame, frameTime, setFrame, actor, decisions, refresh } = useScenario();
  const [selected, setSelected] = useState<string | null>(null);
  const [decisionOpen, setDecisionOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [draft, setDraft] = useState<NationalDecisionDraft>({
    scene_time: '',
    decision_type: 'zwolanie_RZZK',
    scope: 'kraj',
    critical_gminas: 0,
    vulnerable_without_power: 0,
    justification: '',
    supersedes: '',
  });

  const voivFilter = actor.role === 'RCB' ? '' : actor.voivodeshipCode;

  const view = useMemo(() => {
    if (!index) return null;
    const f = index.scene.frames[frame];
    if (!f) return null;
    const risk = riskMap(f);
    const inScope = (code: string) =>
      !voivFilter || index.gminaByCode.get(code)?.v === voivFilter;

    const rows = f.risk.filter((r) => inScope(r[0]));
    const points: MapPoint[] = rows.map((r) => {
      const g = index.gminaByCode.get(r[0]);
      return {
        id: r[0],
        lat: Number(g?.lat ?? 0),
        lon: Number(g?.lon ?? 0),
        value: r[1],
        label: shortGminaName(g?.n ?? r[0]),
        detail: `IZŻ ${formatNumber(r[1])} · ${formatNumber(r[2])} h bez zasilania · ${formatNumber(r[4])} osób wrażliwych`,
        alarm: r[1] >= IZZ_CRITICAL,
      };
    });

    const byVoiv = new Map<string, { critical: number; vuln: number; name: string }>();
    for (const r of rows) {
      const g = index.gminaByCode.get(r[0]);
      if (!g) continue;
      const cur = byVoiv.get(g.v) ?? {
        critical: 0,
        vuln: 0,
        name: index.voivByCode.get(g.v)?.n ?? g.v,
      };
      if (r[1] >= IZZ_CRITICAL) cur.critical += 1;
      cur.vuln += r[4];
      byVoiv.set(g.v, cur);
    }

    const callRows = Object.entries(f.calls)
      .filter(([k]) => !k.startsWith('_'))
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([k, v]) => ({ label: CALL_TYPE_LABELS[k] ?? k, value: v }));

    const stats = index.stats[frame];
    const prev = index.stats[Math.max(0, frame - 1)];
    const from = Math.max(0, frame - SPARK_WINDOW + 1);
    const spark = index.stats.slice(from, frame + 1);

    return {
      frame: f,
      risk,
      rows,
      points,
      byVoiv: [...byVoiv.entries()].sort((a, b) => b[1].critical - a[1].critical),
      callRows,
      stats,
      prev,
      spark,
      recs: recommendations(index, frame, voivFilter),
    };
  }, [index, frame, voivFilter]);

  if (!index || !view) return <EmptyState text="Wczytywanie sceny…" />;

  const { stats, prev, spark } = view;
  const selectedRow = selected ? view.risk.get(selected) : undefined;
  const selectedGmina = selected ? index.gminaByCode.get(selected) : undefined;

  const openDecision = () => {
    setDraft({
      scene_time: frameTime,
      decision_type: 'zwolanie_RZZK',
      scope: actor.role === 'RCB' ? 'kraj' : actor.voivodeshipCode || 'kraj',
      critical_gminas: stats.critical,
      vulnerable_without_power: stats.vulnerableWithoutPower,
      justification: '',
      supersedes: '',
    });
    setErrors([]);
    setDecisionOpen(true);
  };

  const submitDecision = async () => {
    const v = validateNationalDecision(draft, actor);
    if (!v.ok) {
      setErrors(v.errors);
      return;
    }
    try {
      const saved = await saveNationalDecision(draft, actor);
      await refresh();
      setDecisionOpen(false);
      setToast(`Zapisano decyzję ${saved.decision_id}.`);
    } catch (e) {
      setErrors([e instanceof Error ? e.message : String(e)]);
    }
  };

  /** Uzasadnienie podpowiadane z bieżących przesłanek — decydent je poprawia, nie pisze od zera. */
  const suggestJustification = () => {
    const worst = view.rows[0];
    const g = worst ? index.gminaByCode.get(worst[0]) : undefined;
    setDraft((d) => ({
      ...d,
      justification:
        `Stan na ${formatTime(frameTime)}. Gmin w stanie krytycznym (IZŻ ≥ ${IZZ_CRITICAL}): ${stats.critical}. ` +
        `Osoby wrażliwe bez zasilania: ${formatNumber(stats.vulnerableWithoutPower)}. ` +
        (worst
          ? `Najwyższy IZŻ ${formatNumber(worst[1])} w gminie ${shortGminaName(g?.n ?? worst[0])}, ${formatNumber(worst[2])} h bez zasilania przy ${formatNumber(worst[6])} °C odczuwalnych. `
          : '') +
        `Temperatura odczuwalna w obszarze zdarzenia: ${formatNumber(stats.minFeelsLike)} °C. ` +
        `Zgłoszenia 112 w ostatniej godzinie: ${stats.calls}.`,
    }));
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <KpiCard
          label="Gminy krytyczne"
          value={stats.critical}
          prev={prev.critical}
          hint={`IZŻ ≥ ${IZZ_CRITICAL}. Podstawa zwołania RZZK.`}
          spark={spark.map((s) => s.critical)}
          emphasis={stats.critical > 0}
        />
        <KpiCard
          label="Wrażliwi bez zasilania"
          value={stats.vulnerableWithoutPower}
          prev={prev.vulnerableWithoutPower}
          hint="Szacunek z Indeksu Wrażliwości Ludności przeskalowany udziałem odbiorców bez prądu."
          spark={spark.map((s) => s.vulnerableWithoutPower)}
        />
        <KpiCard
          label="Odbiorcy bez prądu"
          value={stats.customersWithoutPower}
          prev={prev.customersWithoutPower}
          hint="Suma zgłoszeń operatora sieci dla gmin z czynną awarią."
          spark={spark.map((s) => s.customersWithoutPower)}
        />
        <KpiCard
          label="Odczuwalna w strefie"
          value={stats.minFeelsLike}
          prev={prev.minFeelsLike}
          unit=" °C"
          higherIsWorse={false}
          hint="Najniższa temperatura odczuwalna wśród gmin objętych awarią."
          spark={spark.map((s) => s.minFeelsLike)}
        />
        <KpiCard
          label="Skuteczność SPO-3"
          value={stats.deliveryRate === null ? 0 : Math.round(stats.deliveryRate * 1000) / 10}
          prev={prev.deliveryRate === null ? null : Math.round(prev.deliveryRate * 1000) / 10}
          unit="%"
          higherIsWorse={false}
          hint="Dostarczone / wysłane w tej godzinie. Poniżej 60% kampanię trzeba wznowić."
          spark={spark.map((s) => (s.deliveryRate ?? 0) * 100)}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <Panel
          title="Mapa zagrożenia życia"
          subtitle={`Indeks Zagrożenia Życia · ${view.rows.length} gmin powyżej progu monitorowania`}
          right={
            <span className="text-[11px] text-slate-500">
              kółko myszy · przeciągnięcie · dwuklik
            </span>
          }
        >
          <CountryMap
            points={view.points}
            colorFor={izzColor}
            legend={IZZ_LEGEND}
            onSelect={setSelected}
            selectedId={selected}
            height={430}
            highlightRegions={
              voivFilter ? [index.voivByCode.get(voivFilter)?.n ?? ''] : undefined
            }
          />
        </Panel>

        <div className="space-y-4">
          <Panel
            title="Przesłanki eskalacji"
            tone={view.recs.some((r) => r.severity === 'critical') ? 'alert' : 'default'}
            right={
              <Button variant="primary" onClick={openDecision}>
                Podejmij decyzję
              </Button>
            }
          >
            {view.recs.length === 0 ? (
              <EmptyState text="Brak przesłanek do eskalacji w tej chwili scenariusza." />
            ) : (
              <ul className="space-y-2.5">
                {view.recs.map((r) => (
                  <li
                    key={r.id}
                    className={`rounded-lg p-3 ring-1 ${
                      r.severity === 'critical'
                        ? 'bg-red-50 ring-red-600/30'
                        : r.severity === 'high'
                          ? 'bg-amber-50 ring-amber-600/30'
                          : 'bg-slate-50 ring-slate-200'
                    }`}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-sm font-semibold text-slate-900">{r.title}</span>
                      <span className="shrink-0 text-[10px] uppercase tracking-wider text-slate-500">
                        {r.spo}
                      </span>
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-slate-500">{r.detail}</p>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Zgłoszenia 112 w tej godzinie" subtitle={`Razem ${stats.calls}`}>
            {view.callRows.length === 0 ? (
              <EmptyState text="Brak zgłoszeń w tej godzinie." />
            ) : (
              <BarList rows={view.callRows} color="#c2410c" />
            )}
          </Panel>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Przebieg zdarzenia" subtitle="Gminy krytyczne w kolejnych godzinach">
          <TimelineBars
            values={index.stats.map((s) => s.critical)}
            labels={index.scene.frames.map((f) => formatTime(f.t))}
            activeIndex={frame}
            onSelect={setFrame}
            height={70}
            colorFor={(v) => (v > 0 ? '#d5233f' : '#00417f')}
          />
          <div className="mt-3 space-y-2">
            <p className="text-[11px] text-slate-500">
              Osoby wrażliwe bez zasilania w całym przebiegu
            </p>
            <Sparkline
              values={index.stats.map((s) => s.vulnerableWithoutPower)}
              marker={frame}
              height={44}
              color="#0052a5"
            />
          </div>
        </Panel>

        <Panel title="Rozkład wojewódzki" subtitle="Gminy krytyczne i osoby wrażliwe bez prądu">
          {view.byVoiv.length === 0 ? (
            <EmptyState text="Brak gmin powyżej progu." />
          ) : (
            <BarList
              rows={view.byVoiv.slice(0, 8).map(([, v]) => ({
                label: v.name,
                value: v.critical,
                hint: `${formatNumber(v.vuln)} osób wrażliwych bez zasilania`,
              }))}
              color="#d5233f"
            />
          )}
        </Panel>

        <Panel
          title="Rejestr decyzji"
          subtitle={`${decisions.length} ${decisions.length === 1 ? 'wpis' : 'wpisów'}`}
        >
          {decisions.length === 0 ? (
            <EmptyState text="Brak decyzji. Każda zapisana decyzja niesie migawkę przesłanek." />
          ) : (
            <ul className="max-h-[240px] space-y-2 overflow-y-auto pr-1">
              {decisions.slice(0, 12).map((d) => (
                <li key={d.id} className="rounded-lg bg-slate-50 p-2.5 ring-1 ring-slate-200">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-xs font-semibold text-slate-900">
                      {DECISION_TYPES.find((t) => t.key === d.decision_type)?.label ??
                        d.decision_type}
                    </span>
                    <span className="shrink-0 text-[10px] tabular-nums text-slate-500">
                      {d.decision_id}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[11px] text-slate-500">
                    {d.author_role} · {d.scope} · {d.critical_gminas} gmin krytycznych
                  </p>
                  <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-slate-500">
                    {d.justification}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      {selectedGmina && selectedRow && (
        <Panel
          title={shortGminaName(selectedGmina.n)}
          subtitle={`${index.voivByCode.get(selectedGmina.v)?.n ?? ''} · ${formatNumber(selectedGmina.pop)} mieszkańców`}
          tone={selectedRow[1] >= IZZ_CRITICAL ? 'alert' : 'accent'}
          right={
            <Button variant="ghost" onClick={() => setSelected(null)}>
              Zamknij
            </Button>
          }
        >
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {[
              { l: 'IZŻ', v: formatNumber(selectedRow[1]), s: izzLevel(selectedRow[1]).label },
              { l: 'IWL', v: formatNumber(selectedGmina.iwl), s: 'indeks wrażliwości' },
              { l: 'Bez zasilania', v: `${formatNumber(selectedRow[2])} h`, s: `${formatNumber(selectedRow[3])} odbiorców` },
              { l: 'Wrażliwi bez prądu', v: formatNumber(selectedRow[4]), s: `z ${formatNumber(selectedGmina.vuln)} ogółem` },
              { l: 'Pokrycie sieci', v: `${formatNumber(selectedRow[5] * 100)}%`, s: selectedRow[5] < 0.2 ? 'RSO i SMS nie dotrą' : 'ostrzeganie działa' },
              { l: 'Dojazd ratunkowy', v: `${formatNumber(selectedGmina.rescue)} min`, s: `${formatNumber(selectedRow[6])} °C odczuwalne` },
            ].map((c) => (
              <div key={c.l} className="rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200">
                <div className="text-[10px] uppercase tracking-wider text-slate-500">{c.l}</div>
                <div className="mt-0.5 text-lg font-semibold tabular-nums text-slate-900">
                  {c.v}
                </div>
                <div className="text-[11px] text-slate-500">{c.s}</div>
              </div>
            ))}
          </div>
          {actor.role === 'RCB' && (
            <p className="mt-3 text-[11px] text-slate-500">
              Widok krajowy pracuje na agregatach. Lista osób z kolejki wizyt jest dostępna dla
              gminy, OSP i koordynatora medycznego.
            </p>
          )}
        </Panel>
      )}

      <Modal
        open={decisionOpen}
        title="Decyzja szczebla krajowego"
        onClose={() => setDecisionOpen(false)}
      >
        <div className="space-y-4">
          <p className="rounded-lg bg-slate-50 p-3 text-xs leading-relaxed text-slate-500 ring-1 ring-slate-200">
            Decyzja zostanie zapisana wraz z migawką przesłanek na chwilę{' '}
            <span className="font-semibold text-slate-900">{formatTime(frameTime)}</span>:{' '}
            {stats.critical} gmin krytycznych, {formatNumber(stats.vulnerableWithoutPower)} osób
            wrażliwych bez zasilania. Wpisu nie da się później zmienić — odwołanie decyzji to nowy
            wpis wskazujący poprzedni.
          </p>

          <Field label="Rodzaj decyzji">
            <select
              value={draft.decision_type}
              onChange={(e) => setDraft({ ...draft, decision_type: e.target.value, supersedes: '' })}
              className={inputClass}
            >
              {DECISION_TYPES.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.label}
                </option>
              ))}
            </select>
          </Field>

          {draft.decision_type === 'odwolanie' && (
            <Field label="Decyzja odwoływana">
              <select
                value={draft.supersedes}
                onChange={(e) => setDraft({ ...draft, supersedes: e.target.value })}
                className={inputClass}
              >
                <option value="">— wskaż wpis —</option>
                {decisions.map((d) => (
                  <option key={d.id} value={d.decision_id}>
                    {d.decision_id} ·{' '}
                    {DECISION_TYPES.find((t) => t.key === d.decision_type)?.label ??
                      d.decision_type}
                  </option>
                ))}
              </select>
            </Field>
          )}

          <Field label="Zasięg">
            <select
              value={draft.scope}
              onChange={(e) => setDraft({ ...draft, scope: e.target.value })}
              className={inputClass}
              disabled={actor.role !== 'RCB'}
            >
              <option value="kraj">Cały kraj</option>
              {index.scene.voivodeships.map((v) => (
                <option key={v.c} value={v.c}>
                  {v.n}
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="Uzasadnienie"
            hint={`${draft.justification.trim().length} / 1500 znaków, wymagane minimum 20`}
          >
            <textarea
              value={draft.justification}
              onChange={(e) => setDraft({ ...draft, justification: e.target.value })}
              rows={6}
              className={inputClass}
              placeholder="Na jakiej podstawie zapada decyzja i co ma zostać uruchomione."
            />
          </Field>

          <Button variant="default" onClick={suggestJustification}>
            Wstaw przesłanki z bieżącej chwili
          </Button>

          {errors.length > 0 && (
            <ul className="space-y-1 rounded-lg bg-red-50 p-3 text-xs text-red-700 ring-1 ring-red-600/30">
              {errors.map((e) => (
                <li key={e}>• {e}</li>
              ))}
            </ul>
          )}

          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDecisionOpen(false)}>
              Anuluj
            </Button>
            <Button variant="primary" onClick={() => void submitDecision()}>
              Zapisz decyzję
            </Button>
          </div>
        </div>
      </Modal>

      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}
