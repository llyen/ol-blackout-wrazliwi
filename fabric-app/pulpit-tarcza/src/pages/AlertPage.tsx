import { useMemo, useState } from 'react';

import {
  CHANNELS,
  COVERAGE_BLACKOUT,
  formatHour,
  formatNumber,
  formatTime,
  IZZ_HIGH,
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
  Panel,
  Sparkline,
  Toast,
  inputClass,
  type MapPoint,
} from '@/components/ui';
import { useScenario } from '@/hooks/ScenarioContext';
import {
  MESSAGE_REQUIREMENTS,
  missingMessageParts,
  saveCampaign,
  uselessChannels,
  validateCampaign,
  type AlertCampaignDraft,
} from '@/services/workflow';

/** Domyślny zestaw kanałów. Radio lokalne jest zaznaczone zawsze — działa bez sieci. */
const DEFAULT_CHANNELS = ['RSO', 'SMS', 'local_radio'];

export function AlertPage() {
  const { index, frame, frameTime, actor, campaigns, refresh } = useScenario();
  const [selectedGminas, setSelectedGminas] = useState<Set<string>>(new Set());
  const [channels, setChannels] = useState<string[]>(DEFAULT_CHANNELS);
  const [text, setText] = useState('');
  const [hover, setHover] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const view = useMemo(() => {
    if (!index) return null;
    const f = index.scene.frames[frame];
    if (!f) return null;
    const risk = riskMap(f);

    const scope = actor.role === 'wojewoda / WCZK' ? actor.voivodeshipCode : '';
    const rows = [...risk.values()]
      .map((r) => {
        const g = index.gminaByCode.get(r[0]);
        return {
          code: r[0],
          name: shortGminaName(g?.n ?? r[0]),
          voiv: g?.v ?? '',
          lat: Number(g?.lat ?? 0),
          lon: Number(g?.lon ?? 0),
          pop: g?.pop ?? 0,
          izz: r[1],
          hours: r[2],
          vulnerable: r[4],
          coverage: r[5],
          feelsLike: r[6],
        };
      })
      .filter((r) => {
        if (actor.gminaCode) return r.code === actor.gminaCode;
        if (scope) return r.voiv === scope;
        return true;
      })
      .sort((a, b) => b.izz - a.izz);

    const selected = rows.filter((r) => selectedGminas.has(r.code));
    const lowCoverage = selected.filter((r) => r.coverage < COVERAGE_BLACKOUT);
    const population = selected.reduce((s, r) => s + r.pop, 0);

    const points: MapPoint[] = rows.slice(0, 400).map((r) => ({
      id: r.code,
      lat: r.lat,
      lon: r.lon,
      value: r.izz,
      label: r.name,
      detail: `IZŻ ${formatNumber(r.izz)} · pokrycie ${formatNumber(r.coverage * 100)}% · ${formatNumber(r.pop)} mieszkańców`,
      alarm: selectedGminas.has(r.code),
    }));

    // Skuteczność dostarczenia z przebiegu scenariusza — pokazuje, że przy
    // spadku pokrycia kanał sieciowy przestaje docierać.
    const delivery = index.stats.map((s) => (s.deliveryRate ?? 0) * 100);

    return { rows, selected, lowCoverage, population, points, delivery, risk };
  }, [index, frame, actor, selectedGminas]);

  if (!index || !view) return <EmptyState text="Wczytywanie sceny…" />;

  const toggleGmina = (code: string) => {
    const next = new Set(selectedGminas);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    setSelectedGminas(next);
  };

  const selectHigh = () => {
    setSelectedGminas(new Set(view.rows.filter((r) => r.izz >= IZZ_HIGH).map((r) => r.code)));
  };

  const toggleChannel = (key: string) => {
    setChannels((prev) => (prev.includes(key) ? prev.filter((c) => c !== key) : [...prev, key]));
  };

  /**
   * Podpowiedź treści. Nie jest to generowanie „z niczego” — szablon składa
   * wymagane elementy komunikatu SPO-3 z liczb bieżącej klatki, żeby
   * dyżurny nie musiał ich przepisywać ręcznie pod presją czasu.
   */
  const suggest = () => {
    const sel = view.selected.length > 0 ? view.selected : view.rows.slice(0, 1);
    const names = sel.slice(0, 3).map((r) => r.name);
    const more = sel.length > names.length ? ` i ${sel.length - names.length} innych gmin` : '';
    const points = sel
      .flatMap((r) => index.heatingByGmina.get(r.code) ?? [])
      .filter((h) => h.sel)
      .slice(0, 2);
    const where =
      points.length > 0
        ? points.map((h) => `${h.type} ${h.id}`).join(', ')
        : 'punkty grzewcze wskazane przez gminę';
    setText(
      `UWAGA. Brak zasilania w gminach: ${names.join(', ')}${more}. ` +
        `Temperatura odczuwalna do ${formatNumber(
          Math.min(...sel.map((r) => r.feelsLike)),
        )} st. C. ` +
        `Uruchomiono miejsca ogrzania: ${where}. Zabierz leki i dokumenty. ` +
        `Nie ogrzewaj mieszkania grillem ani kuchenką gazową — grozi zatruciem czadem. ` +
        `Sprawdź sąsiadów, zwłaszcza osoby starsze i samotne. ` +
        `W razie zagrożenia życia dzwoń 112. Aktualizacja o ${formatHour(frameTime)}.`,
    );
    setErrors([]);
  };

  const missing = missingMessageParts(text);
  const useless = uselessChannels(channels, view.lowCoverage.length);

  const draft: AlertCampaignDraft = {
    scene_time: frameTime,
    message_text: text,
    channels: channels.join(','),
    target_gminas: view.selected.map((r) => r.code).join(','),
    target_gmina_count: view.selected.length,
    target_population: view.population,
    low_coverage_gminas: view.lowCoverage.length,
    approval_status: 'zatwierdzona',
    language: 'pl',
    scope: actor.role === 'RCB' ? 'krajowy' : actor.voivodeshipCode || 'gminny',
  };

  const submit = async () => {
    const v = validateCampaign(draft, actor);
    if (!v.ok) {
      setErrors(v.errors);
      return;
    }
    setBusy(true);
    try {
      const saved = await saveCampaign(draft, actor);
      await refresh();
      setErrors([]);
      setToast(
        `Uruchomiono kampanię ${saved.campaign_id} — ${view.selected.length} gmin, ` +
          `${formatNumber(view.population)} mieszkańców.`,
      );
    } catch (e) {
      setErrors([e instanceof Error ? e.message : String(e)]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          label="Gminy wybrane"
          value={view.selected.length}
          higherIsWorse={false}
          hint="Obszar objęty komunikatem."
          emphasis={view.selected.length > 0}
        />
        <KpiCard
          label="Mieszkańcy w zasięgu"
          value={view.population}
          higherIsWorse={false}
          hint="Suma ludności wybranych gmin."
        />
        <KpiCard
          label="Gminy bez łączności"
          value={view.lowCoverage.length}
          hint="Pokrycie poniżej 20% — RSO i SMS tam nie dotrą."
        />
        <KpiCard
          label="Skuteczność dostarczenia"
          value={Math.round((index.stats[frame]?.deliveryRate ?? 0) * 100)}
          unit="%"
          higherIsWorse={false}
          hint="Udział komunikatów dostarczonych w tej klatce."
          spark={view.delivery.slice(Math.max(0, frame - 23), frame + 1)}
        />
      </div>

      {view.lowCoverage.length > 0 && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-4">
          <p className="text-sm font-semibold text-amber-800">
            {view.lowCoverage.length} z wybranych gmin nie ma łączności
          </p>
          <p className="mt-1 text-xs leading-relaxed text-amber-700">
            Przy pokryciu poniżej 20% komunikat wysłany kanałem sieciowym zostanie nadany, ale nie
            dotrze. Tam działa wyłącznie radio lokalne, megafon i obwieszczenie w terenie. Wskaźnik
            „wysłano” bez wskaźnika „dostarczono” to najczęstsze źródło złudzenia, że ludność
            została ostrzeżona.
          </p>
          <p className="mt-2 text-xs text-amber-700">
            Gminy:{' '}
            {view.lowCoverage
              .slice(0, 8)
              .map((r) => r.name)
              .join(', ')}
            {view.lowCoverage.length > 8 ? ` i ${view.lowCoverage.length - 8} innych` : ''}
          </p>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <Panel
          title="Wybór obszaru"
          subtitle={`Kliknij gminę na mapie albo w tabeli · stan na ${formatTime(frameTime)}`}
          right={
            <div className="flex gap-2">
              <Button variant="default" onClick={selectHigh}>
                Zaznacz IZŻ ≥ {IZZ_HIGH}
              </Button>
              <Button variant="ghost" onClick={() => setSelectedGminas(new Set())}>
                Wyczyść
              </Button>
            </div>
          }
        >
          <CountryMap
            points={view.points}
            colorFor={izzColor}
            legend={IZZ_LEGEND}
            onSelect={toggleGmina}
            selectedId={hover}
            height={380}
          />
          <div className="mt-3 max-h-44 overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="py-1.5 pr-2" />
                  <th className="py-1.5 pr-2">Gmina</th>
                  <th className="py-1.5 pr-2">IZŻ</th>
                  <th className="py-1.5 pr-2">Pokrycie</th>
                  <th className="py-1.5">Mieszkańcy</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {view.rows.slice(0, 80).map((r) => (
                  <tr
                    key={r.code}
                    onMouseEnter={() => setHover(r.code)}
                    onClick={() => toggleGmina(r.code)}
                    className={`cursor-pointer transition-colors ${
                      selectedGminas.has(r.code) ? 'bg-gov/10' : 'hover:bg-slate-50'
                    }`}
                  >
                    <td className="py-1.5 pr-2">
                      <input
                        type="checkbox"
                        readOnly
                        checked={selectedGminas.has(r.code)}
                        className="accent-gov"
                      />
                    </td>
                    <td className="py-1.5 pr-2 text-slate-900">{r.name}</td>
                    <td className="py-1.5 pr-2 tabular-nums">
                      <span style={{ color: izzColor(r.izz) }} className="font-semibold">
                        {formatNumber(r.izz)}
                      </span>
                    </td>
                    <td className="py-1.5 pr-2 tabular-nums text-slate-700">
                      {formatNumber(r.coverage * 100)}%
                    </td>
                    <td className="py-1.5 tabular-nums text-slate-700">{formatNumber(r.pop)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <div className="space-y-4">
          <Panel
            title="Treść komunikatu"
            subtitle="Procedura SPO-3 — cztery elementy obowiązkowe"
            right={
              <Button variant="default" onClick={suggest}>
                Podpowiedz treść
              </Button>
            }
          >
            <Field
              label="Komunikat"
              hint={`${text.length} / 600 znaków, wymagane co najmniej 160`}
            >
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={7}
                className={inputClass}
                placeholder="Treść ostrzeżenia dla ludności."
              />
            </Field>

            <div className="mt-3 flex flex-wrap gap-2">
              {MESSAGE_REQUIREMENTS.map((r) => {
                const ok = !missing.includes(r.label);
                return (
                  <Badge
                    key={r.key}
                    className={
                      ok
                        ? 'bg-emerald-100 text-emerald-800 ring-emerald-600/30'
                        : 'bg-slate-50 text-slate-500 ring-slate-300'
                    }
                  >
                    {ok ? '✓' : '○'} {r.label}
                  </Badge>
                );
              })}
            </div>
          </Panel>

          <Panel title="Kanały" subtitle="Radio lokalne działa również przy braku zasięgu">
            <div className="flex flex-wrap gap-2">
              {CHANNELS.map((c) => {
                const on = channels.includes(c.key);
                const dead = on && useless.includes(c.key);
                return (
                  <button
                    key={c.key}
                    onClick={() => toggleChannel(c.key)}
                    className={`rounded-lg px-3 py-1.5 text-xs font-medium ring-1 transition-colors ${
                      on
                        ? dead
                          ? 'bg-amber-50 text-amber-800 ring-amber-600/40'
                          : 'bg-gov/10 text-gov ring-gov/40'
                        : 'bg-white text-slate-500 ring-slate-300 hover:bg-slate-50'
                    }`}
                  >
                    {c.label}
                    {dead && ' · nie dotrze'}
                  </button>
                );
              })}
            </div>
            {useless.length > 0 && (
              <p className="mt-3 text-xs leading-relaxed text-amber-700">
                Kanały sieciowe nie dotrą do {view.lowCoverage.length} gmin bez zasięgu. Zostaw je
                dla pozostałego obszaru, ale dla gmin odciętych uruchom radio lokalne i ogłoszenie
                w terenie.
              </p>
            )}

            {errors.length > 0 && (
              <ul className="mt-3 space-y-1 rounded-lg border border-red-300 bg-red-50 p-3 text-xs text-red-700">
                {errors.map((e) => (
                  <li key={e}>• {e}</li>
                ))}
              </ul>
            )}

            <div className="mt-4 flex items-center justify-between gap-3">
              <p className="text-xs text-slate-500">
                {view.selected.length} gmin · {formatNumber(view.population)} mieszkańców ·{' '}
                {channels.length} {channels.length === 1 ? 'kanał' : 'kanały'}
              </p>
              <Button variant="primary" onClick={() => void submit()} disabled={busy}>
                {busy ? 'Uruchamianie…' : 'Uruchom kampanię'}
              </Button>
            </div>
          </Panel>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Skuteczność w czasie" subtitle="Dostarczone / wysłane w przebiegu scenariusza">
          <Sparkline values={view.delivery} marker={frame} height={70} />
          <p className="mt-2 text-xs leading-relaxed text-slate-500">
            Spadek krzywej pokrywa się z utratą zasilania stacji bazowych. To moment, w którym
            ostrzeganie kanałem cyfrowym przestaje być skuteczne.
          </p>
        </Panel>

        <Panel
          title="Uruchomione kampanie"
          subtitle={`${campaigns.length} ${campaigns.length === 1 ? 'wpis' : 'wpisów'}`}
          className="lg:col-span-2"
        >
          {campaigns.length === 0 ? (
            <EmptyState text="Brak kampanii. Wybierz obszar, ułóż treść i uruchom." />
          ) : (
            <table className="w-full text-left text-xs">
              <thead className="text-[10px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="py-1.5 pr-2">Nr</th>
                  <th className="py-1.5 pr-2">Zasięg</th>
                  <th className="py-1.5 pr-2">Kanały</th>
                  <th className="py-1.5 pr-2">Bez łączności</th>
                  <th className="py-1.5">Treść</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {campaigns.slice(0, 10).map((c) => (
                  <tr key={c.id}>
                    <td className="py-1.5 pr-2 tabular-nums text-slate-500">{c.campaign_id}</td>
                    <td className="py-1.5 pr-2 tabular-nums text-slate-700">
                      {c.target_gmina_count} gmin
                      <div className="text-[11px] text-slate-500">
                        {formatNumber(c.target_population)} osób
                      </div>
                    </td>
                    <td className="py-1.5 pr-2 text-slate-700">
                      {c.channels
                        .split(',')
                        .map((k) => CHANNELS.find((ch) => ch.key === k)?.label ?? k)
                        .join(', ')}
                    </td>
                    <td className="py-1.5 pr-2 tabular-nums">
                      {c.low_coverage_gminas > 0 ? (
                        <span className="font-semibold text-amber-700">
                          {c.low_coverage_gminas}
                        </span>
                      ) : (
                        <span className="text-slate-400">0</span>
                      )}
                    </td>
                    <td className="py-1.5 text-slate-500">
                      {c.message_text.slice(0, 90)}
                      {c.message_text.length > 90 ? '…' : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      <Toast message={toast} onDone={() => setToast(null)} />
    </div>
  );
}
