# Tezeta

A knowledge graph of terms. Terms are nodes colored by `vibe`; words shared by
two or more terms become small hub nodes that pull related terms together.

## Edit the data

Edit `data/terms.csv` (`term,definition,vibe`) and push to `main`:

- `import-terms.yml` upserts the rows into the Firestore `terms` collection
  (doc id = slug of the term; the CSV row replaces the document).
- `firebase-hosting-merge.yml` rebuilds the graph and deploys it.

## Run locally (uv)

```bash
uv run scripts/import_terms.py --dry-run   # validate the CSV
uv run scripts/build_graph.py              # writes dist/index.html
```

Importing needs `FIREBASE_SERVICE_ACCOUNT` (the service account JSON) in the
environment, and that account needs the **Cloud Datastore User** role.
`--prune` deletes Firestore terms that are not in the CSV.

## Pages and links

- `/#index` opens the graph straight to a term (the slug is the term lowercased with dashes).
- `/t/<slug>/` is a standalone page per term with Open Graph and Twitter tags, so shared links unfurl
  with a preview card from `/og/<slug>.png`. Cards are drawn at build time with Pillow, using the
  Cormorant Garamond font in `scripts/fonts/` (SIL Open Font License).
- `/sitemap.xml` and `/robots.txt` are generated too. Set `SITE_URL` to build for a different domain.
- Press `/` on the graph to search.
