type SymbolItem = { symbol: string; exchange: string; is_active: boolean };
type Company = { id: string; name: string; symbols: SymbolItem[] };
type DataSource = { id: string; name: string; source_type: string; enabled: boolean };
type CollectionRun = {
  id: string;
  collector_name: string;
  status: string;
  records_stored: number;
};
type EventItem = {
  id: string;
  title: string;
  event_type: string;
  published_at: string | null;
};
type Page<T> = { items: T[] };

const fixture = {
  companies: [
    { id: "fixture-aapl", name: "Apple Inc.", symbols: [{ symbol: "AAPL", exchange: "NASDAQ", is_active: true }] },
    { id: "fixture-msft", name: "Microsoft Corp.", symbols: [{ symbol: "MSFT", exchange: "NASDAQ", is_active: true }] },
  ],
  sources: [
    { id: "fixture-market", name: "Market data fixture", source_type: "fixture", enabled: true },
    { id: "fixture-news", name: "Financial news fixture", source_type: "fixture", enabled: true },
    { id: "fixture-sec", name: "SEC filing fixture", source_type: "fixture", enabled: true },
  ],
  runs: [
    { id: "fixture-run", collector_name: "fixture_collector", status: "succeeded", records_stored: 2 },
  ],
  events: [
    { id: "fixture-event", title: "Example quarterly results", event_type: "earnings", published_at: "2026-01-30T21:05:00Z" },
  ],
};

async function api<T>(path: string): Promise<T> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
  const response = await fetch(`${baseUrl}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`API request failed: ${response.status}`);
  return response.json() as Promise<T>;
}

async function loadDashboard() {
  try {
    const [companies, sources, runs, events] = await Promise.all([
      api<Company[]>("/companies"),
      api<DataSource[]>("/data-sources"),
      api<CollectionRun[]>("/collection-runs?limit=5"),
      api<Page<EventItem>>("/events?page_size=5"),
    ]);
    return { companies, sources, runs, events: events.items, health: "Operational", fixture: false };
  } catch {
    return { ...fixture, health: "Fixture mode", fixture: true };
  }
}

export const dynamic = "force-dynamic";

export default async function Dashboard() {
  const data = await loadDashboard();
  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">MARKET INTELLIGENCE</p>
          <h1>MarketMind</h1>
          <p className="lede">Evidence-first financial research infrastructure.</p>
        </div>
        <span className={data.fixture ? "status fixture" : "status"}>
          <i /> {data.health}
        </span>
      </header>

      <section className="metrics">
        <Metric label="Tracked symbols" value={data.companies.flatMap((item) => item.symbols).length} />
        <Metric label="Data sources" value={data.sources.length} />
        <Metric label="Recent runs" value={data.runs.length} />
        <Metric label="Stored events" value={data.events.length} />
      </section>

      {data.fixture && <aside>Offline fixture data — connect the API and seed PostgreSQL for live storage.</aside>}

      <div className="grid">
        <Panel title="Tracked symbols">
          {data.companies.map((company) => (
            <div className="row" key={company.id}>
              <div><strong>{company.symbols[0]?.symbol}</strong><span>{company.name}</span></div>
              <small>{company.symbols[0]?.exchange}</small>
            </div>
          ))}
        </Panel>
        <Panel title="Available data sources">
          {data.sources.map((source) => (
            <div className="row" key={source.id}>
              <div><strong>{source.name}</strong><span>{source.source_type.replaceAll("_", " ")}</span></div>
              <small className="enabled">{source.enabled ? "Ready" : "Disabled"}</small>
            </div>
          ))}
        </Panel>
        <Panel title="Recent collection runs">
          {data.runs.map((run) => (
            <div className="row" key={run.id}>
              <div><strong>{run.collector_name}</strong><span>{run.records_stored} records stored</span></div>
              <small className="enabled">{run.status}</small>
            </div>
          ))}
        </Panel>
        <Panel title="Stored events">
          {data.events.map((event) => (
            <div className="row" key={event.id}>
              <div><strong>{event.title}</strong><span>{event.event_type.replaceAll("_", " ")}</span></div>
              <small>{event.published_at ? new Date(event.published_at).toLocaleDateString("en-US") : "—"}</small>
            </div>
          ))}
        </Panel>
      </div>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <article><span>{label}</span><strong>{value}</strong></article>;
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="panel"><h2>{title}</h2>{children}</section>;
}

