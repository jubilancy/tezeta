import { useEffect, useMemo, useState } from "react";
import { fetchTerms } from "./fetchTerms";
import { clusterTerms } from "./cluster";
import "./styles.css";

function Card({ term }) {
  return (
    <article className="card">
      <header>
        <h3>{term.term}</h3>
        {term.vibe && <span className="vibe">{term.vibe}</span>}
      </header>
      <p>{term.definition}</p>
    </article>
  );
}

function Branch({ label, count, children }) {
  return (
    <section className="branch">
      <h2>
        {label} <span className="count">{count}</span>
      </h2>
      <div className="cards">{children}</div>
    </section>
  );
}

export default function App() {
  const [terms, setTerms] = useState(null);
  const [error, setError] = useState(null);
  const [vibe, setVibe] = useState("all");

  useEffect(() => {
    fetchTerms().then(setTerms).catch(setError);
  }, []);

  const vibes = useMemo(
    () => [...new Set((terms || []).map((t) => t.vibe).filter(Boolean))].sort(),
    [terms]
  );

  const { clusters, loose } = useMemo(() => {
    const visible = (terms || []).filter((t) => vibe === "all" || t.vibe === vibe);
    return clusterTerms(visible);
  }, [terms, vibe]);

  if (error) return <pre className="status">{error.message}</pre>;
  if (!terms) return <p className="status">Opening the catalog…</p>;

  return (
    <main>
      <header className="masthead">
        <h1>Tezeta</h1>
        <p>A card catalog of terms, grouped by the words they share.</p>
        <nav className="filters" aria-label="Filter by vibe">
          {["all", ...vibes].map((v) => (
            <button key={v} className={v === vibe ? "on" : ""} onClick={() => setVibe(v)}>
              {v}
            </button>
          ))}
        </nav>
      </header>

      <div className="tree">
        {clusters.map((c) => (
          <Branch key={c.label} label={c.label} count={c.terms.length}>
            {c.terms.map((t) => (
              <Card key={t.id} term={t} />
            ))}
          </Branch>
        ))}
        {loose.length > 0 && (
          <Branch label="Unfiled" count={loose.length}>
            {loose.map((t) => (
              <Card key={t.id} term={t} />
            ))}
          </Branch>
        )}
      </div>
    </main>
  );
}
