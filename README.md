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
