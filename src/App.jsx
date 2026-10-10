import { useEffect, useState } from "react";
import { fetchTerms } from "./fetchTerms";

export default function App() {
  const [terms, setTerms] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchTerms().then(setTerms).catch(setError);
  }, []);

  if (error) return <pre>{error.message}</pre>;
  if (!terms) return <p>Loading…</p>;

  return (
    <main>
      <h1>Tezeta</h1>
      <p>{terms.length} terms loaded</p>
      <ul>
        {terms.map((t) => (
          <li key={t.id}>
            <code>{JSON.stringify(t)}</code>
          </li>
        ))}
      </ul>
    </main>
  );
}
