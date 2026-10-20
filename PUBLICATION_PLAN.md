# Proposed public repository staging plan

This is the reviewed staging plan for the first baseline commit, not a Git
command log. Stage by explicit path after reviewing each file. No commit or
GitHub remote is created by this plan.

## Initial baseline allowlist

- Root: `.gitignore`, `AGENTS.md`, `README.md`, `PUBLICATION_PLAN.md`.
- Firmware: all files under `firmware/project-source/` **except generated
  `__pycache__/`**, including the exact dependency manifest, inventory,
  reconstruction/export scripts, two active patch files, application/Kconfig
  overlay, and historical patch documentation. The manifest applies the
  historical ICM20608 and RW007 patches once; the historical SNTP patch is
  retained as a reference and is not applied twice.
- Backend source: `backend/app.py`, `backend/activity_recognition.py`,
  `backend/inference_service.py`, `backend/publish_simulated.py`,
  `backend/requirements.txt`, `backend/requirements-training.txt`,
  `backend/.gitignore`, `backend/broker.example.yaml`,
  `backend/README.md`, `backend/ACTIVITY_RECOGNITION.md`,
  `backend/ml/*.py`, `backend/ml/*.md`, `backend/tests/*.py`,
  `backend/models/*.json`, `backend/models/README.md`, and
  `backend/models/activity_model_corrected.joblib`. The project owner
  explicitly authorized redistribution of this existing corrected artifact.
  This authorization does not establish rights to the original dataset.
- Web: `web/src/`, `web/package.json`, `web/package-lock.json`,
  `web/next.config.ts`, `web/tsconfig.json`, `web/postcss.config.mjs`,
  `web/eslint.config.mjs`, `web/.gitignore`, `web/.env.example`,
  `web/README.md`, and `web/AGENTS.md` after review.

Review each staged path before committing. Do not use `git add .` as a
substitute for this allowlist.

## Exclusions

- `firmware/rt-thread/` known-working large checkout and its nested `.git`;
  `firmware/reconstruction-work/` temporary clean build; `rw007-download/`
  separate clone and `.git`; object files, ELF/BIN/HEX, and other build output.
- `backend/data/` runtime database and Run-or-Walk CSV; older/other `.joblib`
  models; `backend/broker.yaml` and
  environment files; `backend/file` empty local artifact; Python environments
  and caches.
- `web/node_modules/`, `.next/`, caches, and real `.env*` files other than
  reviewed examples.
- Course PDF, third-party datasheets, old Android archive, Env archive,
  personal downloads, credentials, logs, and large backups.

The corrected model is included under the project owner's authorization, so
the public baseline can run the existing inference pipeline after installing
the documented dependencies. The dataset CSV, lab PDF, and vendor datasheets
remain excluded; their redistribution rights are separate and unresolved.

## Honest commit sequence

1. `chore: import existing Lab 3 source baseline` — the reviewed allowlist
   above. Verify the firmware manifest/inventory and inspect staged paths.
   This is a baseline of completed work, not a recreated history.
2. `docs: improve third-party license notices` — only after additional
   file-level rights are verified; record actual license evidence while
   keeping the restricted dataset and course materials excluded.
3. `test: add reproducible firmware reconstruction check` — only if an actual
   new CI or clean-machine verification is added. Run the new check on the
   pinned source. Do not create this commit without that change.
4. `test: strengthen frontend or backend regressions` — only for real new
   tests or fixes; run the relevant test suite.
5. `docs: describe frontend-only deployment constraints` — only if new
   verified Vercel setup work is completed; run frontend lint, typecheck,
   tests, and production build.

Never backdate commits or split already completed features into invented
historical milestones.
