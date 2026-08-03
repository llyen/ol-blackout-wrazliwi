"""Odtwarzanie scenariusza logistyki zasobow w czasie rzeczywistym.

Zasilanie idzie bezposrednio przez streaming ingestion Eventhouse (REST), dzieki czemu
kazde zdarzenie jest widoczne w dashboardzie w czasie ponizej sekundy od wyslania.

Uzycie:
    python scenario/replay.py --reset --speed 3600
    python scenario/replay.py --speed 600 --from 2026-09-14T00:00:00Z
"""
from __future__ import annotations

import argparse
import json
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "datasets"
CONFIG = ROOT / "scenario" / "scenario.json"

# Tabele Eventhouse maja nazwy PascalCase, a pliki zrodlowe prefiks fact_.
# Mapowanie przychodzi z scenario.json i jest ustawiane przy starcie.
FILES: dict = {}


def stream_file(stream: str) -> str:
    return FILES.get(stream, stream)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# --- uwierzytelnianie -------------------------------------------------------

class TokenCache:
    """Token Kusto z az CLI, odswiezany zanim wygasnie."""

    def __init__(self, resource: str = "https://kusto.kusto.windows.net"):
        self.resource = resource
        self._token = None
        self._expires = datetime.now(timezone.utc)
        self._lock = threading.Lock()

    def invalidate(self):
        """Wymusza pobranie nowego tokenu przy najblizszym get()."""
        with self._lock:
            self._token = None

    @staticmethod
    def _expiry_from(data: dict) -> datetime:
        """Rzeczywisty czas waznosci tokenu zwrocony przez az CLI.

        Sztywne zalozenie 45 minut bylo bledne: az potrafi oddac token z wlasnego
        cache, ktoremu zostalo kilkanascie minut. Odtwarzanie dostawalo wtedy 401
        w polowie przebiegu i caly tryb ciagly sie zatrzymywal.
        """
        epoch = data.get("expires_on")
        if epoch is not None:
            return datetime.fromtimestamp(int(epoch), timezone.utc)
        raw = data.get("expiresOn")
        if raw:
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                parsed = parsed.astimezone()
            return parsed.astimezone(timezone.utc)
        return datetime.now(timezone.utc) + timedelta(minutes=45)

    def get(self) -> str:
        with self._lock:
            if self._token and datetime.now(timezone.utc) < self._expires:
                return self._token
            cmd = ["az", "account", "get-access-token", "--resource", self.resource, "-o", "json"]
            out = subprocess.run(cmd, capture_output=True, text=True, shell=(sys.platform == "win32"))
            if out.returncode != 0:
                raise SystemExit(f"az account get-access-token nie powiodlo sie: {out.stderr.strip()}")
            data = json.loads(out.stdout)
            self._token = data["accessToken"]
            # Margines 5 minut, zeby token nie wygasl w trakcie dluzszej partii.
            self._expires = self._expiry_from(data) - timedelta(minutes=5)
            return self._token


# --- klient Kusto -----------------------------------------------------------

class KustoClient:
    def __init__(self, cluster: str, database: str, tokens: TokenCache):
        self.cluster = cluster.rstrip("/")
        self.database = database
        self.tokens = tokens

    def _post(self, url: str, body: bytes) -> bytes:
        last = None
        for attempt in range(5):
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Authorization", f"Bearer {self.tokens.get()}")
            req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return resp.read()
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:400]
                last = f"HTTP {exc.code}: {detail}"
                if exc.code == 401:
                    # Token wygasl w trakcie przebiegu. Unieważniamy cache, zeby
                    # kolejna proba poszla z nowym tokenem, zamiast konczyc odtwarzanie.
                    self.tokens.invalidate()
                # 429 i wszystkie 5xx sa przejsciowe (Eventhouse potrafi zwrocic 520),
                # pozostalych nie ma sensu ponawiac
                elif exc.code != 429 and exc.code < 500:
                    raise SystemExit(f"{url}\n{last}")
            except urllib.error.URLError as exc:
                last = str(exc)
            except TimeoutError as exc:
                # Timeout odczytu nie jest opakowany w URLError, bo polaczenie zostalo
                # juz nawiazane. Bez tej galezi ciezkie operacje (.clear na kilkuset
                # tysiacach wierszy) przerywaly caly przebieg zamiast zostac ponowione.
                last = f"timeout odczytu: {exc}"
            time.sleep(min(2 ** attempt, 15))
        raise SystemExit(f"Nie udalo sie wykonac zadania po 5 probach: {last}")

    def mgmt(self, csl: str):
        body = json.dumps({"db": self.database, "csl": csl}).encode("utf-8")
        return json.loads(self._post(f"{self.cluster}/v1/rest/mgmt", body))

    def query(self, csl: str):
        body = json.dumps({"db": self.database, "csl": csl}).encode("utf-8")
        return json.loads(self._post(f"{self.cluster}/v1/rest/query", body))

    def scalar(self, csl: str):
        rows = self.query(csl)["Tables"][0]["Rows"]
        return rows[0][0] if rows else None

    def table_columns(self, table: str):
        raw = self.mgmt(f".show table {table} schema as json")["Tables"][0]["Rows"][0][1]
        return [c["Name"] for c in json.loads(raw)["OrderedColumns"]]

    def ensure_mapping(self, table: str, columns, mapping_name: str = "scenario_map"):
        mapping = [{"column": c, "Properties": {"Path": f"$.{c}"}} for c in columns]
        literal = json.dumps(mapping, ensure_ascii=False).replace("\\", "\\\\").replace("'", "\\'")
        self.mgmt(f".create-or-alter table {table} ingestion json mapping '{mapping_name}' '{literal}'")

    def ingest(self, table: str, ndjson: str, mapping_name: str = "scenario_map"):
        url = (f"{self.cluster}/v1/rest/ingest/{self.database}/{table}"
               f"?streamFormat=json&mappingName={mapping_name}")
        self._post(url, ndjson.encode("utf-8"))

    def ingest_from_onelake(self, table: str, url: str, mapping_name: str = "scenario_map") -> str:
        """Ingestia wsadowa z OneLake. Dane trafiaja do ekstentow, wiec zapytania sa szybkie."""
        csl = (f".ingest async into table {table} (h'{url};impersonate') "
               f"with (format='json', ingestionMappingReference='{mapping_name}')")
        return self.mgmt(csl)["Tables"][0]["Rows"][0][0]

    def wait_for_operation(self, operation_id: str, timeout_s: int = 900) -> str:
        """Czeka na zakonczenie operacji. Kolumne State szukamy po nazwie,
        bo kolejnosc kolumn w .show operations nie jest gwarantowana."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            table = self.mgmt(f".show operations {operation_id}")["Tables"][0]
            names = [c["ColumnName"] for c in table["Columns"]]
            if "State" not in names:
                raise SystemExit(f".show operations nie zwrocilo kolumny State: {names}")
            idx = names.index("State")
            rows = table["Rows"]
            if rows:
                state = rows[-1][idx]
                if state not in ("InProgress", "Scheduled"):
                    return state
            time.sleep(3)
        return "Timeout"

    def delete_from(self, table: str, cutoff_iso: str):
        csl = f".delete table {table} records <| {table} | where timestamp >= datetime({cutoff_iso})"
        self.mgmt(csl)

    def rewrite_timeline(self, table: str, live_start_iso: str, anchor_iso: str, speed: float) -> str:
        """Obcina tlo do startu fazy live i przenosi je na skompresowana os czasu zegarowego.

        Jedno polecenie robi obie rzeczy naraz i po stronie serwera, wiec dane od razu
        laduja w nowych ekstentach. Dzieki temu tlo konczy sie dokladnie w chwili 'anchor',
        a faza live plynnie kontynuuje os czasu az do biezacego 'teraz'.
        """
        csl = (f".set-or-replace async {table} <| {table} "
               f"| where timestamp < datetime({live_start_iso}) "
               f"| extend timestamp = datetime({anchor_iso}) "
               f"+ (timestamp - datetime({live_start_iso})) / {speed}")
        return self.mgmt(csl)["Tables"][0]["Rows"][0][0]


# --- rownolegla wysylka -----------------------------------------------------

class IngestPool:
    """Pula watkow wysylajacych partie do Eventhouse.

    Pojedyncze zadanie HTTP kosztuje ok. 100 ms, wiec przy szeregowej wysylce
    przepustowosc spada do ~250 zdarzen/s. Scenariusz w tempie 3600x wymaga
    ok. 1850 zdarzen/s, dlatego partie ida rownolegle.
    """

    def __init__(self, client: "KustoClient", workers: int = 8, max_queue: int = 64):
        self.client = client
        self.queue: "queue.Queue" = queue.Queue(maxsize=max_queue)
        self.sent = 0
        self.error = None
        self._lock = threading.Lock()
        self._threads = [threading.Thread(target=self._worker, daemon=True) for _ in range(workers)]
        for t in self._threads:
            t.start()

    def _worker(self):
        while True:
            item = self.queue.get()
            try:
                if item is None:
                    return
                table, rows = item
                try:
                    self.client.ingest(table, "\n".join(rows))
                    with self._lock:
                        self.sent += len(rows)
                except BaseException as exc:  # noqa: BLE001 - blad watku musi dotrzec do glownego
                    with self._lock:
                        self.error = self.error or str(exc)
            finally:
                self.queue.task_done()

    def submit(self, table: str, rows):
        if self.error:
            raise SystemExit(f"Blad wysylki: {self.error}")
        self.queue.put((table, rows))

    def drain(self):
        self.queue.join()
        if self.error:
            raise SystemExit(f"Blad wysylki: {self.error}")

    def reset_error(self):
        """Kasuje blad, zeby tryb ciagly mogl wznowic kolejnym cyklem."""
        with self._lock:
            self.error = None

    def close(self):
        for _ in self._threads:
            self.queue.put(None)
        for t in self._threads:
            t.join(timeout=30)


# --- odtwarzanie ------------------------------------------------------------

def parse_ts(value: str) -> datetime:
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts


def load_config(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Brak {path}. Uruchom scenario\\run_scenario.ps1, ktory go tworzy.")
    return json.loads(path.read_text(encoding="utf-8"))


def load_events(streams, start, end):
    """Wczytuje i scala strumienie, sortujac po czasie zdarzenia."""
    events = []
    for stream in streams:
        path = DATASETS / f"{stream_file(stream)}.jsonl"
        if not path.exists():
            print(f"  [pomijam] brak {path.name}")
            continue
        count = 0
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                ev = json.loads(line)
                ts = parse_ts(ev["timestamp"])
                if start and ts < start:
                    continue
                if end and ts > end:
                    continue
                events.append((ts, stream, ev))
                count += 1
        print(f"  {stream}: {count} zdarzen")
    events.sort(key=lambda item: item[0])
    return events


def reset_tables(client: KustoClient, streams):
    print("=== Reset: czyszczenie tabel strumieniowych")
    # Czyszczenie potrafi sie nie udac, gdy trwa jeszcze poprzednia ingestia.
    # Bez ponowienia tlo doladowaloby sie na istniejace dane i liczby bylyby podwojone.
    for stream in streams:
        cleared = False
        for attempt in range(6):
            try:
                client.mgmt(f".clear table {stream} data")
                if client.scalar(f"{stream} | count") == 0:
                    cleared = True
                    break
            except SystemExit:
                pass
            time.sleep(10 * (attempt + 1))
            print(f"  [ponawiam] {stream}")
        if not cleared:
            raise SystemExit(f"Nie udalo sie wyczyscic tabeli {stream}. Poczekaj i uruchom ponownie.")
        print(f"  [OK] wyczyszczono {stream}")


def bulk_load(client: KustoClient, streams, base_url: str, cutoff: datetime):
    """Wczytuje tlo scenariusza ingestia wsadowa.

    Ingestia wsadowa buduje ekstenty, dzieki czemu zapytania kafelkow sa szybkie.
    Streaming ingestion trzyma dane w buforze i przy setkach tysiecy wierszy
    zapytania zauwazalnie zwalniaja - dlatego strumieniowo idzie wylacznie okno live.
    """
    print("=== Tlo scenariusza: ingestia wsadowa")
    # Ingestie ida sekwencyjnie: dziewiec rownoleglych zadan przekracza limit
    # wspolbieznosci pojemnosci F8 i konczy sie stanem Throttled.
    for stream in streams:
        url = f"{base_url.rstrip('/')}/{stream_file(stream)}.jsonl"
        loaded = 0
        state = "NieUruchomiono"
        for attempt in range(5):
            operation = client.ingest_from_onelake(stream, url)
            state = client.wait_for_operation(operation)
            loaded = client.scalar(f"{stream} | count")
            if state == "Completed" and loaded:
                break
            wait_s = 15 * (attempt + 1)
            print(f"  [ponawiam za {wait_s}s] {stream}: stan={state}")
            time.sleep(wait_s)
        if state != "Completed" or not loaded:
            raise SystemExit(f"Ingestia wsadowa {stream} nie powiodla sie: stan={state}, wierszy={loaded}")
        print(f"  [OK] {stream}: {loaded} wierszy")


def trim_background(client: KustoClient, streams, cutoff: datetime):
    """Obcina tlo do momentu startu fazy live, zachowujac oryginalne znaczniki czasu."""
    cutoff_iso = cutoff.isoformat()
    print(f"=== Obcinanie tla do {cutoff_iso}")
    for stream in streams:
        client.delete_from(stream, cutoff_iso)
        rows = client.scalar(f"{stream} | count")
        print(f"  [OK] {stream}: {rows} wierszy tla")


def shift_background(client: KustoClient, streams, live_start: datetime, anchor: datetime, speed: float):
    """Obcina tlo i przenosi je na skompresowana os czasu konczaca sie w chwili 'anchor'."""
    live_iso, anchor_iso = live_start.isoformat(), anchor.isoformat()
    print(f"=== Przenoszenie tla na os czasu zegarowego (kotwica {anchor_iso}, tempo {speed}x)")
    for stream in streams:
        # Pojemnosc F8 przy wlaczonych widokach materializowanych potrafi zdlawic
        # set-or-replace (stan Throttled). Ponawiamy, bo zdlawiona operacja nic nie
        # zapisala - powtorzenie nie przesunie tla drugi raz.
        state = "NieUruchomiono"
        for attempt in range(4):
            operation = client.rewrite_timeline(stream, live_iso, anchor_iso, speed)
            state = client.wait_for_operation(operation, timeout_s=300)
            if state == "Completed":
                break
            wait_s = 20 * (attempt + 1)
            print(f"  [ponawiam za {wait_s}s] {stream}: stan={state}")
            time.sleep(wait_s)
        if state != "Completed":
            raise SystemExit(f"Przesuniecie osi czasu {stream} nie powiodlo sie: stan={state}")
        rows = client.scalar(f"{stream} | count")
        oldest = client.scalar(f"{stream} | summarize min(timestamp)")
        print(f"  [OK] {stream}: {rows} wierszy tla, najstarszy {oldest}")
    print("  Tlo konczy sie dokladnie w chwili startu fazy live.")


def prune(client: KustoClient, streams, keep_hours: float):
    """Usuwa dane starsze niz okno prezentacji, zeby tryb ciagly nie rozdymal tabel."""
    print(f"  [porzadki] usuwam dane starsze niz {keep_hours} h")
    for stream in streams:
        try:
            client.mgmt(f".delete table {stream} records <| {stream} "
                        f"| where timestamp < ago({keep_hours}h)")
        except BaseException as exc:  # noqa: BLE001 - porzadki nie moga przerwac demo
            print(f"    [uwaga] {stream}: {exc}")


def run(args):
    cfg = load_config(CONFIG)
    global FILES
    FILES = cfg.get("files", {})
    streams = args.streams.split(",") if args.streams else cfg["streams"]
    client = KustoClient(cfg["cluster"], cfg["database"], TokenCache())

    if args.reset:
        reset_tables(client, streams)
        if args.reset_only:
            print("Gotowe: tabele puste, scenariusz mozna uruchomic od zera.")
            return

    print("=== Przygotowanie mapowan ingestii")
    columns = {}
    for stream in streams:
        cols = client.table_columns(stream)
        client.ensure_mapping(stream, cols)
        columns[stream] = set(cols)
        print(f"  [OK] {stream} ({len(cols)} kolumn)")

    live_start = parse_ts(args.from_ts or cfg["liveStart"])
    live_end = parse_ts(args.to_ts) if args.to_ts else live_start + timedelta(hours=args.live_hours)

    if args.bulk:
        bulk_load(client, streams, cfg["onelake"], live_start)

    print("=== Wczytywanie okna live")
    events = load_events(streams, live_start, live_end)
    if not events:
        raise SystemExit("Brak zdarzen do odtworzenia.")

    t0, t1 = events[0][0], events[-1][0]
    span = (t1 - t0).total_seconds()

    # Os czasu demo. W trybie 'wall' cala scena jest skompresowana mnoznikiem --speed
    # i przypieta do biezacego zegara: tlo konczy sie teraz, a kolejne zdarzenia
    # dostaja znacznik rowny chwili wyslania. Dopiero to daje wrazenie czasu
    # rzeczywistego na dashboardzie z dynamicznym oknem typu "ostatnia godzina".
    anchor = datetime.now(timezone.utc) + timedelta(seconds=5)
    if args.time_mode == "wall":
        if args.bulk:
            shift_background(client, streams, live_start, anchor, args.speed)
    else:
        if args.bulk:
            trim_background(client, streams, live_start)
        anchor = None

    offset = datetime.now(timezone.utc) - t0 if args.time_mode == "now" else None

    def stamp(ts: datetime, cycle_anchor: datetime) -> str:
        """Znacznik czasu zdarzenia na osi demo."""
        if args.time_mode == "wall":
            mapped = cycle_anchor + (ts - live_start) / args.speed
        else:
            mapped = ts + offset
        return mapped.isoformat().replace("+00:00", "Z")

    rewrite = args.time_mode in ("wall", "now")
    tryb = {"wall": "zegar sceny przypiety do teraz", "now": "przesuniete na teraz"}.get(args.time_mode, "oryginalne")

    print(f"  zdarzen: {len(events)}")
    print(f"  okno live: {t0.isoformat()} .. {t1.isoformat()} ({span / 3600:.1f} h)")
    print(f"  mnoznik czasu: {args.speed}x  ->  odtwarzanie potrwa ok. {span / args.speed / 60:.1f} min")
    print(f"  znaczniki czasu: {tryb}")
    if args.dry_run:
        print("DRY-RUN: nic nie wysylam.")
        return

    print("=== Odtwarzanie (Ctrl+C przerywa)")
    pool = IngestPool(client, workers=args.workers)
    buffers = defaultdict(list)
    buffered = 0

    def flush():
        nonlocal buffers, buffered
        for table, rows in buffers.items():
            if rows:
                pool.submit(table, rows)
        buffers = defaultdict(list)
        buffered = 0

    def play(cycle_anchor: datetime, cycle_no: int) -> bool:
        """Odtwarza jeden przebieg okna live. Zwraca False, gdy przerwano z klawiatury."""
        nonlocal buffered
        wall_start = time.monotonic()
        last_log = wall_start
        for ts, stream, ev in events:
            # tempo: czas sceny podzielony przez mnoznik to czas zegarowy
            due = (ts - t0).total_seconds() / args.speed
            behind = due - (time.monotonic() - wall_start)
            if behind > 0:
                flush()
                time.sleep(min(behind, args.tick))
            if rewrite:
                ev = dict(ev)
                ev["timestamp"] = stamp(ts, cycle_anchor)
            payload = {k: v for k, v in ev.items() if k in columns[stream]}
            buffers[stream].append(json.dumps(payload, ensure_ascii=False))
            buffered += 1
            if buffered >= args.batch:
                flush()
            now = time.monotonic()
            if now - last_log >= args.log_every:
                elapsed = now - wall_start
                scene = t0 + timedelta(seconds=elapsed * args.speed)
                etykieta = f"cykl {cycle_no} " if args.loop else ""
                print(f"  [{etykieta}{elapsed / 60:6.1f} min] czas sceny {scene:%Y-%m-%d %H:%M} | "
                      f"wyslano {pool.sent} zdarzen", flush=True)
                last_log = now
        flush()
        pool.drain()
        return True

    started = time.monotonic()
    cycle = 1
    try:
        while True:
            try:
                play(anchor, cycle)
            except SystemExit as exc:
                # Demo w trybie ciaglym ma stac wlaczone godzinami. Pojedyncza awaria
                # (wygasly token, chwilowa niedostepnosc pojemnosci) nie moze konczyc
                # calego przebiegu - wznawiamy nastepnym cyklem od biezacej chwili.
                if not args.loop:
                    raise
                print(f"  [cykl {cycle} przerwany] {exc}; wznawiam za 30 s", flush=True)
                pool.reset_error()
                buffers.clear()
                buffered = 0
                time.sleep(30)
                cycle += 1
                anchor = datetime.now(timezone.utc)
                continue
            if not args.loop:
                break
            # Tryb ciagly: kolejny przebieg startuje od biezacej chwili, wiec dashboard
            # pokazuje aktualne dane niezaleznie od tego, o ktorej ktos go otworzy.
            print(f"  [cykl {cycle} zakonczony] start kolejnego przebiegu", flush=True)
            if args.prune_hours:
                prune(client, streams, args.prune_hours)
            cycle += 1
            anchor = datetime.now(timezone.utc)
    except KeyboardInterrupt:
        print(f"\nPrzerwano. Wyslano {pool.sent} zdarzen.")
        return
    finally:
        pool.close()

    elapsed = time.monotonic() - started
    print(f"=== Zakonczono: {pool.sent} zdarzen w {elapsed / 60:.1f} min")
    for stream in streams:
        print(f"  {stream}: {client.scalar(f'{stream} | count')} wierszy w Eventhouse")


def main():
    p = argparse.ArgumentParser(description="Odtwarzanie scenariusza logistyki zasobow do Eventhouse")
    p.add_argument("--speed", type=float, default=60.0,
                   help="ile sekund scenariusza przypada na sekunde zegara (60 = minuta na sekunde). "
                        "Okno dashboardu musi byc krotsze niz czas jednego cyklu, inaczej w kadrze "
                        "lezy cala scena naraz i przyrost nie jest widoczny")
    p.add_argument("--reset", action="store_true", help="wyczysc tabele przed startem")
    p.add_argument("--reset-only", action="store_true", help="tylko wyczysc i zakoncz")
    p.add_argument("--bulk", action="store_true",
                   help="zaladuj tlo scenariusza ingestia wsadowa z OneLake przed faza live")
    p.add_argument("--live-hours", type=float, default=24.0,
                   help="dlugosc okna odtwarzanego strumieniowo, w godzinach scenariusza")
    p.add_argument("--streams", help="lista strumieni po przecinku; domyslnie wszystkie z scenario.json")
    p.add_argument("--from", dest="from_ts", help="poczatek okna live; domyslnie liveStart z scenario.json")
    p.add_argument("--to", dest="to_ts", help="koniec okna live; domyslnie poczatek + live-hours")
    p.add_argument("--time-mode", choices=("source", "now", "wall"), default="wall",
                   help="wall = cala scena skompresowana i przypieta do biezacego zegara (demo real-time), "
                        "source = oryginalne znaczniki scenariusza, now = staly offset od pierwszego zdarzenia")
    p.add_argument("--loop", action="store_true",
                   help="tryb ciagly: po zakonczeniu okna live scenariusz startuje od nowa, "
                        "wiec dashboard jest na zywo niezaleznie od pory otwarcia")
    p.add_argument("--prune-hours", type=float, default=3.0,
                   help="w trybie ciaglym usuwa dane starsze niz podana liczba godzin (0 = nie usuwaj)")
    p.add_argument("--batch", type=int, default=4000, help="maks. liczba zdarzen w jednej partii")
    p.add_argument("--workers", type=int, default=8, help="liczba rownoleglych watkow wysylajacych")
    p.add_argument("--tick", type=float, default=0.5, help="maks. dlugosc pojedynczego uspienia w sekundach")
    p.add_argument("--log-every", type=float, default=10.0, help="co ile sekund raportowac postep")
    p.add_argument("--dry-run", action="store_true", help="policz i pokaz plan bez wysylania")
    run(p.parse_args())


if __name__ == "__main__":
    main()
