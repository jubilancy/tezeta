const STOPWORDS = new Set(
  "a an and are as at be by for from has have in into is it its of on or that the their this to was were with which who whose about than then them these those not but can may more most other some such only own same so too very".split(
    " "
  )
);

export function tokenize(text = "") {
  return (text.toLowerCase().match(/[a-z]+/g) || [])
    .filter((w) => w.length > 2 && !STOPWORDS.has(w))
    .map(stem);
}

function stem(word) {
  return word
    .replace(/(ing|ed|es|s)$/, (m, _s, offset) => (offset >= 3 ? "" : m));
}

export function termWords(term) {
  return new Set([...tokenize(term.term), ...tokenize(term.definition)]);
}

// Groups terms that share at least `minShared` significant words
// (transitively, via union-find). Singletons land in `loose`.
export function clusterTerms(terms, { minShared = 1 } = {}) {
  const words = terms.map(termWords);
  const parent = terms.map((_, i) => i);
  const find = (i) => (parent[i] === i ? i : (parent[i] = find(parent[i])));

  for (let i = 0; i < terms.length; i++) {
    for (let j = i + 1; j < terms.length; j++) {
      let shared = 0;
      for (const w of words[i]) if (words[j].has(w)) shared++;
      if (shared >= minShared) parent[find(i)] = find(j);
    }
  }

  const groups = new Map();
  terms.forEach((t, i) => {
    const root = find(i);
    if (!groups.has(root)) groups.set(root, []);
    groups.get(root).push(i);
  });

  const clusters = [];
  const loose = [];
  for (const idxs of groups.values()) {
    if (idxs.length === 1) {
      loose.push(terms[idxs[0]]);
      continue;
    }
    const counts = new Map();
    for (const i of idxs) for (const w of words[i]) counts.set(w, (counts.get(w) || 0) + 1);
    const label =
      [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] ?? "related";
    clusters.push({ label, terms: idxs.map((i) => terms[i]) });
  }

  clusters.sort((a, b) => b.terms.length - a.terms.length || a.label.localeCompare(b.label));
  return { clusters, loose };
}
