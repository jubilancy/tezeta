# Tezeta

A knowledge graph of terms. Terms are nodes colored by `vibe`; words shared by several
terms become small hub nodes that tie related terms together. Built to stay fast and
readable from a few dozen terms to ten thousand.

## Edit the data

Edit `data/terms.csv` (`term,definition,vibe`) and push to `main`:

- `import-terms.yml` upserts the rows into the Firestore `terms` collection
  (doc id = slug of the term; the CSV row replaces the document).
- `firebase-hosting-merge.yml` rebuilds the site and deploys it.

## Run locally (uv)

```bash
uv run scripts/import_terms.py --dry-run   # validate the CSV
uv run scripts/build_graph.py              # writes dist/ (open dist/index.html)
```

Importing needs `FIREBASE_SERVICE_ACCOUNT` (the service account JSON) in the
environment, and that account needs the **Cloud Datastore User** role.
`--prune` deletes Firestore terms that are not in the CSV.

## How it scales

Nothing in the browser simulates physics, and nothing is drawn that you cannot see.

| Stage | What happens | Where |
|---|---|---|
| Layout | Louvain finds communities of terms that share vocabulary; each is laid out on its own and the communities become islands; strays are tucked into the gaps. Computed once, shipped as coordinates. | `scripts/layout.py` (igraph) |
| Edges | Each term keeps its 6 most specific shared words, and words common to more than 1% of terms are dropped, so a big library stays a web of specific links. | `pick_hubs` in `build_graph.py` |
| Drawing | Sigma.js renders nodes and edges with WebGL. Glow, nebulae and stars are cached sprites on 2D canvases behind it, culled to the viewport and drawn at reduced strength when the view is crowded. | `scripts/graph_fx.js` |
| Level of detail | Zoomed out: clusters and their names. Zoom in: shared words, then links, then labels. Long links between clusters appear only for what you hover or select. | `scripts/graph_fx.js` |
| Preview cards | One JPEG per term, drawn on every CPU core, and only for new or changed terms. CI caches them between deploys. | `scripts/term_pages.py` |

Measured on 4 cores with real WordNet nouns and definitions:

| Terms | Cold build | Cached build | Files | Site size |
|---|---|---|---|---|
| 1,000 | 14 s | 1 s | 2,005 | 80 MB |
| 3,000 | 42 s | 3 s | 6,005 | 240 MB |
| 10,000 | 139 s | 10 s | 20,005 | 801 MB |

The graph page itself is 0.5 MB at 1,000 terms, 0.9 MB at 3,000 and 2.3 MB at 10,000 (before gzip).

### Tuning knobs

- `STOPWORDS` in `build_graph.py`: words ignored when finding shared vocabulary. It includes
  definition boilerplate ("used", "especially", "involving"); add your own domain's glue words.
- `MAX_HUBS_PER_TERM` and the `0.01` ceiling in `pick_hubs`: fewer links, cleaner clusters.
- `CARD_VERSION` in `term_pages.py`: bump it after changing how preview cards look.
- `SPLIT`, `MIN_COMMUNITY`, `ISLAND_GAP` in `layout.py`: how aggressively clusters are separated.

## Repeated words

A repeated word never fails the import or the build (`scripts/terms_csv.py` decides, for both):

- the same word with the same definition is skipped, with a warning in the run log;
- the same word with a *different* definition is a different entry and is kept. The first keeps the
  plain address (`/t/love/`); the others get the word plus their vibe (`/t/love-quote-topics/`), or a
  number (`love-2`) if that is taken. Addresses follow row order, so deleting the first copy of a word
  moves the next one onto the plain address.

## Pages and links

- `/#index` opens the graph straight to a term (the slug is the term lowercased with dashes).
- `/t/<slug>/` is a standalone page per term with Open Graph and Twitter tags, so shared links unfurl
  with a preview card from `/og/<slug>.jpg`. Cards are drawn at build time with Pillow, using the
  Cormorant Garamond font in `scripts/fonts/` (SIL Open Font License).
- `/sitemap.xml` and `/robots.txt` are generated too. Set `SITE_URL` to build for a different domain.
- Press `/` on the graph to search; Esc clears.
- Definitions may contain web addresses. `http(s)` ones become links in the panel and on term pages (long ones
  wrap at `/ ? & = #`); link previews and cards show just the site name; the address is ignored when
  finding shared words. `javascript:`, `ftp:` and any markup stay plain text.

## Vendored libraries

`scripts/vendor/` holds [Sigma.js](https://www.sigmajs.org/) 3.0.3 and
[graphology](https://graphology.github.io/) 0.25.4 (both MIT), inlined into the page at build
time so the site has no runtime CDN dependency.
