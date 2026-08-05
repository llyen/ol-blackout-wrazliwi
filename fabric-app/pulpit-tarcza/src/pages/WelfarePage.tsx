import { useMemo, useState } from 'react';

import {
  AUTONOMY_URGENT_H,
  CATEGORY_LABELS,
  COVERAGE_BLACKOUT,
  formatNumber,
  formatTime,
  IZZ_LEGEND,
  izzColor,
  riskMap,
  shortGminaName,
  VISIT_RESULTS,
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
  type MapPath,
  type MapPoint,
} from '@/components/ui';
import { useScenario } from '@/hooks/ScenarioContext';
import {
  canSeeContact,
  canSeePersonList,
  dedupeVisits,
  saveVisit,
  validateVisit,
  VISIT_ROLES,
  type WelfareVisitDraft,
} from '@/services/workflow';

export function WelfarePage() {
  const { index, frame, frameTime, actor, visits, refresh, offline } = useScenario();
  const [selected, setSelected] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [draft, setDraft] = useState<WelfareVisitDraft | null>(null);
  const [onlyUrgent, setOnlyUrgent] = useState(false);

  const view = useMemo(() => {
    if (!index) return null;
    const f = index.scene.frames[frame];
    if (!f) return null;
    const risk = riskMap(f);

    // Wizyty odnotowane w scenie do bieżącej klatki plus zapisy użytkownika.
    const doneTokens = new Set<string>();
    for (let i = 0; i <= frame; i += 1) {
      for (const v of index.scene.frames[i].visits) doneTokens.add(v[1]);
    }
    const ownVisits = dedupeVisits(visits);
    for (const v of ownVisits) doneTokens.add(v.person_token);

    // Zakres roli: OSP i gmina widzą wyłącznie własny przydział.
    const teamStops = actor.teamId
      ? (index.scene.routes.find((r) => r.team === actor.teamId)?.stops ?? [])
      : [];
    const assignedTokens = new Set(teamStops.map((s) => s.token));

    let queue = index.scene.queue.filter((q) => {
      if (assignedTokens.size > 0) return assignedTokens.has(q.token);
      if (actor.gminaCode) return q.g === actor.gminaCode;
      if (actor.role === 'wojewoda / WCZK' && actor.voivodeshipCode)
        return index.gminaByCode.get(q.g)?.v === actor.voivodeshipCode;
      return true;
    });
    if (onlyUrgent) queue = queue.filter((q) => q.auto > 0 && q.auto < AUTONOMY_URGENT_H);

    const pending = queue.filter((q) => !doneTokens.has(q.token));

    const points: MapPoint[] = pending.slice(0, 200).map((q) => {
      const g = index.gminaByCode.get(q.g);
      const r = risk.get(q.g);
      return {
        id: q.token,
        lat: Number(g?.lat ?? 0),
        lon: Number(g?.lon ?? 0),
        value: r?.[1] ?? 0,
        label: `${q.token} · ${CATEGORY_LABELS[q.cat] ?? q.cat}`,
        detail: `${shortGminaName(g?.n ?? q.g)} · autonomia ${formatNumber(q.auto)} h · pokrycie ${formatNumber(q.cov * 100)}%`,
        alarm: q.auto > 0 && q.auto < AUTONOMY_URGENT_H,
      };
    });

    // Trasa zespołu jako łamana przez kolejne przystanki.
    const paths: MapPath[] = [];
    if (teamStops.length > 1) {
      const pts = teamStops
        .map((s) => index.gminaByCode.get(s.g))
        .filter((g): g is NonNullable<typeof g> => Boolean(g))
        .map((g) => [Number(g.lat), Number(g.lon)]);
      if (pts.length > 1) paths.push({ id: actor.teamId, points: pts, color: '#0052a5' });
    }

    const urgent = queue.filter((q) => q.auto > 0 && q.auto < AUTONOMY_URGENT_H).length;
    const noCoverage = queue.filter((q) => q.cov < COVERAGE_BLACKOUT).length;

    return {
      queue,
      pending,
      points,
      paths,
      teamStops,
      assignedTokens,
      doneTokens,
      ownVisits,
      urgent,
      noCoverage,
      risk,
    };
  }, [index, frame, actor, visits, onlyUrgent]);

  if (!index || !view) return <EmptyState text="Wczytywanie sceny…" />;

  const canSee = canSeePersonList(actor.role);
  const canWrite = VISIT_ROLES.includes(actor.role);

  if (!canSee) {
    return (
      <Panel title="Lista osób jest niedostępna dla tej roli" tone="accent">
        <p className="text-sm leading-relaxed text-slate-500">
          Rola <span className="font-semibold text-slate-900">{actor.role}</span> pracuje na
          agregatach. Kolejkę wizyt kontrolnych z listą osób widzą gmina, zespół OSP i koordynator
          medyczny — każdy w swoim zakresie. To jeden z testów akceptacyjnych: widok krajowy nie
          zawiera danych o osobach.
        </p>
        <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KpiCard
            label="Osób w kolejce"
            value={index.scene.queue.length}
            hint="Agregat — bez dostępu do listy."
          />
          <KpiCard
            label="Autonomia poniżej 2 h"
            value={
              index.scene.queue.filter((q) => q.auto > 0 && q.auto < AUTONOMY_URGENT_H).length
            }
            hint="Osoby z urządzeniem medycznym wymagające pilnej wizyty."
            emphasis
          />
          <KpiCard
            label="Zespoły w terenie"
            value={index.scene.routes.length}
            higherIsWorse={false}
          />
          <KpiCard
            label="Przystanków zaplanowanych"
            value={index.scene.routes.reduce((s, r) => s + r.stops.length, 0)}
            higherIsWorse={false}
          />
        </div>
      </Panel>
    );
  }

  const openForm = (token: string) => {
    const q = index.personByToken.get(token);
    if (!q) return;
    const g = index.gminaByCode.get(q.g);
    const r = view.risk.get(q.g);
    // Autonomia pozostała: deklarowana minus czas trwania awarii w tej gminie.
    const left = Math.max(0, Math.round((q.auto - (r?.[2] ?? 0)) * 10) / 10);
    setDraft({
      scene_time: frameTime,
      person_token: q.token,
      category: q.cat,
      gmina_code: q.g,
      gmina_name: shortGminaName(g?.n ?? q.g),
      team_id: actor.teamId || index.scene.routes[0]?.team || 'OSP-TEAM-01',
      result: 'contact_confirmed',
      destination: '',
      autonomy_hours_left: left,
      notes: '',
      offline_sync_id: '',
      capture_mode: offline ? 'offline' : 'online',
    });
    setErrors([]);
    setFormOpen(true);
  };

  const submit = async () => {
    if (!draft) return;
    const v = validateVisit(draft, actor, view.assignedTokens);
    if (!v.ok) {
      setErrors(v.errors);
      return;
    }
    try {
      const saved = await saveVisit(draft, actor, view.assignedTokens);
      await refresh();
      setFormOpen(false);
      setToast(
        offline
          ? `Zapisano wynik ${saved.visit_result_id} w kolejce synchronizacji.`
          : `Zapisano wynik ${saved.visit_result_id}.`,
      );
    } catch (e) {
      setErrors([e instanceof Error ? e.message : String(e)]);
    }
  };

  const exportPackage = () => {
    const head = 'kolejnosc;token;kategoria;gmina;autonomia_h;pokrycie;eta_min;dzialanie\n';
    const stops = view.teamStops.length > 0 ? view.teamStops : [];
    const body =
      stops.length > 0
        ? stops
            .map((s) => {
              const q = index.personByToken.get(s.token);
              const g = index.gminaByCode.get(s.g);
              return [
                s.seq,
                s.token,
                q ? (CATEGORY_LABELS[q.cat] ?? q.cat) : '',
                shortGminaName(g?.n ?? s.g),
                q ? formatNumber(q.auto) : '',
                q ? formatNumber(q.cov * 100) : '',
                formatNumber(s.eta),
                s.action,
              ].join(';');
            })
            .join('\n')
        : view.pending
            .slice(0, 100)
            .map((q, i) =>
              [
                i + 1,
                q.token,
                CATEGORY_LABELS[q.cat] ?? q.cat,
                shortGminaName(index.gminaByCode.get(q.g)?.n ?? q.g),
                formatNumber(q.auto),
                formatNumber(q.cov * 100),
                '',
                '',
              ].join(';'),
            )
            .join('\n');
    downloadCsv(`paczka-wizyt-${actor.teamId || 'gmina'}.csv`, head + body);
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          label="Osoby do odwiedzenia"
          value={view.pending.length}
          hint="Kolejka priorytetowa pomniejszona o odnotowane wizyty."
          emphasis={view.pending.length > 0}
        />
        <KpiCard
          label="Autonomia poniżej 2 h"
          value={view.urgent}
          hint="Urządzenie medyczne przestanie działać przed upływem dwóch godzin."
        />
        <KpiCard
          label="Bez zasięgu"
          value={view.noCoverage}
          hint="Poniżej 20% pokrycia telefon nie zadziała — wymagana wizyta, nie telefon."
        />
        <KpiCard
          label="Wyniki zapisane"
          value={view.ownVisits.length}
          higherIsWorse={false}
          hint="Zapisy tej sesji po odsianiu duplikatów z trybu terenowego."
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <Panel
          title={view.teamStops.length > 0 ? `Trasa zespołu ${actor.teamId}` : 'Rozmieszczenie osób'}
          subtitle={
            view.teamStops.length > 0
              ? `${view.teamStops.length} przystanków w kolejności`
              : 'Kolor oznacza IZŻ gminy, obwódka — pilność'
          }
        >
          <CountryMap
            points={view.points}
            colorFor={izzColor}
            legend={IZZ_LEGEND}
            onSelect={setSelected}
            selectedId={selected}
            paths={view.paths}
            height={400}
          />
        </Panel>

        <Panel
          title="Kolejka wizyt"
          subtitle="Kolejność z modelu priorytetyzacji: kategoria medyczna, autonomia, zasięg, czas dojazdu"
          right={
            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1.5 text-[11px] text-slate-500">
                <input
                  type="checkbox"
                  checked={onlyUrgent}
                  onChange={(e) => setOnlyUrgent(e.target.checked)}
                  className="accent-gov"
                />
                tylko pilne
              </label>
              <Button variant="default" onClick={exportPackage}>
                Paczka offline
              </Button>
            </div>
          }
        >
          {view.pending.length === 0 ? (
            <EmptyState text="Kolejka pusta — wszystkie osoby z przydziału mają odnotowany wynik." />
          ) : (
            <div className="max-h-[420px] overflow-y-auto">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-white text-[10px] uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="py-2 pr-2">#</th>
                    <th className="py-2 pr-2">Osoba</th>
                    <th className="py-2 pr-2">Gmina</th>
                    <th className="py-2 pr-2">Autonomia</th>
                    <th className="py-2 pr-2">Zasięg</th>
                    <th className="py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {view.pending.slice(0, 120).map((q) => {
                    const g = index.gminaByCode.get(q.g);
                    const urgent = q.auto > 0 && q.auto < AUTONOMY_URGENT_H;
                    return (
                      <tr
                        key={q.token}
                        className={`align-top transition-colors ${
                          selected === q.token ? 'bg-gov/10' : 'hover:bg-slate-50'
                        }`}
                        onMouseEnter={() => setSelected(q.token)}
                      >
                        <td className="py-2 pr-2 tabular-nums text-slate-500">{q.rank}</td>
                        <td className="py-2 pr-2">
                          <div className="font-medium text-slate-900">{q.token}</div>
                          <div className="text-[11px] text-slate-500">
                            {CATEGORY_LABELS[q.cat] ?? q.cat}
                            {q.alone ? ' · mieszka sam' : ''}
                          </div>
                          {canSeeContact(actor.role) && q.contact && (
                            <div className="text-[11px] text-slate-500">{q.contact}</div>
                          )}
                        </td>
                        <td className="py-2 pr-2 text-slate-700">
                          {shortGminaName(g?.n ?? q.g)}
                          <div className="text-[11px] text-slate-500">{q.age}</div>
                        </td>
                        <td
                          className={`py-2 pr-2 tabular-nums ${urgent ? 'font-semibold text-red-700' : 'text-slate-700'}`}
                        >
                          {q.auto > 0 ? `${formatNumber(q.auto)} h` : '—'}
                        </td>
                        <td className="py-2 pr-2 tabular-nums text-slate-700">
                          {formatNumber(q.cov * 100)}%
                          {q.cov < COVERAGE_BLACKOUT && (
                            <div className="text-[11px] text-amber-700">brak łączności</div>
                          )}
                        </td>
                        <td className="py-2">
                          <Button
                            variant="primary"
                            disabled={!canWrite}
                            onClick={() => openForm(q.token)}
                            className="!px-2 !py-1 !text-[11px]"
                          >
                            Wynik
                          </Button>
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
        title="Odnotowane wyniki"
        subtitle="Zapisy z trybu terenowego są odsiewane po identyfikatorze synchronizacji"
      >
        {view.ownVisits.length === 0 ? (
          <EmptyState text="Brak zapisanych wyników wizyt." />
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="py-1.5 pr-2">Nr</th>
                <th className="py-1.5 pr-2">Osoba</th>
                <th className="py-1.5 pr-2">Gmina</th>
                <th className="py-1.5 pr-2">Zespół</th>
                <th className="py-1.5 pr-2">Wynik</th>
                <th className="py-1.5 pr-2">Tryb</th>
                <th className="py-1.5">Notatka</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {view.ownVisits.slice(0, 20).map((v) => (
                <tr key={v.id}>
                  <td className="py-1.5 pr-2 tabular-nums text-slate-500">{v.visit_result_id}</td>
                  <td className="py-1.5 pr-2 text-slate-900">{v.person_token}</td>
                  <td className="py-1.5 pr-2 text-slate-700">{v.gmina_name}</td>
                  <td className="py-1.5 pr-2 tabular-nums text-slate-700">{v.team_id}</td>
                  <td className="py-1.5 pr-2">
                    <Badge
                      className={
                        v.result === 'contact_confirmed'
                          ? 'bg-emerald-50 text-emerald-700 ring-emerald-600/30'
                          : v.result === 'no_contact'
                            ? 'bg-red-50 text-red-700 ring-red-600/30'
                            : 'bg-amber-50 text-amber-700 ring-amber-600/30'
                      }
                    >
                      {VISIT_RESULTS.find((r) => r.key === v.result)?.label ?? v.result}
                    </Badge>
                    {v.destination && (
                      <div className="mt-0.5 text-[11px] text-slate-500">→ {v.destination}</div>
                    )}
                  </td>
                  <td className="py-1.5 pr-2 text-slate-500">{v.capture_mode}</td>
                  <td className="py-1.5 text-slate-500">{v.notes || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Modal open={formOpen} title="Wynik wizyty kontrolnej" onClose={() => setFormOpen(false)}>
        {draft && (
          <div className="space-y-4">
            <div className="rounded-lg bg-slate-50 p-3 text-xs leading-relaxed text-slate-500 ring-1 ring-slate-200">
              Osoba <span className="font-semibold text-slate-900">{draft.person_token}</span> ·{' '}
              {CATEGORY_LABELS[draft.category] ?? draft.category} · {draft.gmina_name}. Szacowana
              pozostała autonomia urządzenia: {formatNumber(draft.autonomy_hours_left)} h. Stan na{' '}
              {formatTime(frameTime)}.
              {offline && ' Zapis powstaje w trybie terenowym i trafi do kolejki synchronizacji.'}
            </div>

            <Field label="Wynik">
              <select
                value={draft.result}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    result: e.target.value,
                    destination: e.target.value === 'evacuation' ? draft.destination : '',
                  })
                }
                className={inputClass}
              >
                {VISIT_RESULTS.map((r) => (
                  <option key={r.key} value={r.key}>
                    {r.label}
                  </option>
                ))}
              </select>
            </Field>

            {draft.result === 'evacuation' && (
              <Field label="Miejsce docelowe" hint="Wymagane przy ewakuacji">
                <select
                  value={draft.destination}
                  onChange={(e) => setDraft({ ...draft, destination: e.target.value })}
                  className={inputClass}
                >
                  <option value="">— wskaż punkt —</option>
                  {(index.heatingByGmina.get(draft.gmina_code) ?? [])
                    .concat(
                      index.scene.heatingPoints
                        .filter((h) => h.sel && h.g !== draft.gmina_code)
                        .slice(0, 30),
                    )
                    .map((h) => (
                      <option key={h.id} value={`${h.type} ${h.id}`}>
                        {h.type} {h.id} · {h.cap} miejsc
                        {h.g !== draft.gmina_code ? ' · gmina sąsiednia' : ''}
                      </option>
                    ))}
                  <option value="szpital powiatowy">Szpital powiatowy</option>
                </select>
              </Field>
            )}

            <Field label="Zespół">
              <select
                value={draft.team_id}
                onChange={(e) => setDraft({ ...draft, team_id: e.target.value })}
                className={inputClass}
              >
                {index.scene.routes.map((r) => (
                  <option key={r.team} value={r.team}>
                    {r.team}
                  </option>
                ))}
              </select>
            </Field>

            <Field
              label="Notatka"
              hint={`${draft.notes.length} / 500 znaków. Opis sytuacji technicznej — bez danych o stanie zdrowia.`}
            >
              <textarea
                value={draft.notes}
                onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
                rows={3}
                className={inputClass}
                placeholder="Co zastał zespół i co zostało przekazane."
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
                {offline ? 'Zapisz w kolejce' : 'Zapisz wynik'}
              </Button>
            </div>
          </div>
        )}
      </Modal>

      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}
