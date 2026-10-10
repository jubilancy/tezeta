# Ideas for Tezeta

## Make the graph even more alive
- [ ] **Flowing light**: tiny particles drifting along edges from term to shared word, speed tied to how many terms share it.
- [ ] **Constellation mode**: draw soft lines and a name label around each vibe cluster, like a star chart.
- [ ] **Time-lapse**: add a `added` date column and replay the graph growing term by term.
- [ ] **Sound**: a soft chime per node on hover, pitched by vibe. Off by default.
- [ ] **Poster export**: one button that renders a high-resolution PNG or SVG for printing.
- [ ] **Themes**: night sky, parchment, risograph, blueprint. Swap the palette with one setting.
- [ ] **3D mode**: a rotating WebGL version with `3d-force-graph`.

## Smarter connections
- [ ] **Semantic edges**: link terms by meaning with embeddings, not only shared words.
- [ ] **Hand-made links**: an optional `related` column in the CSV for connections you curate yourself.
- [ ] **Term types**: `broader`, `narrower`, `see also` columns, so it is a true taxonomy tree.
- [ ] **Auto-vibe**: suggest a vibe for new terms from their definitions.
- [ ] **Duplicate finder**: flag near-identical terms when you import.

## Browse and explore
- [x] **Search**: type to fly the camera to a term. ([commit](https://github.com/jubilancy/tezeta/commit/00524a97d2d44810e179cf90c04db9806bd97fcb))
- [ ] **Random walk**: a "surprise me" button that hops along connections.
- [x] **Deep links**: `tezeta.web.app/#index` opens straight to a term. ([commit](https://github.com/jubilancy/tezeta/commit/3a2a862465482b214823fa7ce0a9b423fe5da79b))
- [ ] **Library-card view**: an alternate flip-through view of printed catalog cards.
- [ ] **Term of the day**: a daily featured node with its neighbors.

## Data and workflow
- [ ] **Edit in a sheet**: sync a Google Sheet to `data/terms.csv`, so editing never needs git.
- [ ] **Add-term form**: a small authenticated page that writes straight to Firestore.
- [ ] **Import report**: the workflow comment lists terms added, changed and removed.
- [ ] **Live mode**: read from Firestore in the browser so edits appear without a deploy.
- [x] **Per-term pages**: shareable URLs with social preview images. ([commit](https://github.com/jubilancy/tezeta/commit/d6643fed3171acc96495ac0d754405e09d984611))
