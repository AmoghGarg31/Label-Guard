# Deployment Guide

LabelGuard is verified for local demonstration. The configuration in this repository prepares a single-instance prototype deployment with a Vercel frontend and a Docker-based Render backend. It does not make the application production-ready: there is no authentication or role authorization.

## Before deployment

1. Push the repository to GitHub without local databases, backups, environments, uploads, reports, or `.env` files. The root `.gitignore` excludes these paths. The included GitHub Actions workflow then validates both applications, dependency audits, and the backend image build.
2. Keep the repository private until you intentionally choose otherwise.
3. Decide whether you accept a paid Render service and persistent disk. The SQLite database and generated media are not safe on an ephemeral filesystem.
4. Do not use the deployment for real regulated records or unrestricted public traffic.

## Backend on Render

The root `render.yaml` defines one Docker web service in Singapore, one instance, `/health` checks, Gemini routing/rate-limit settings, and a 1 GB persistent disk mounted at `/var/data`.

1. In Render, choose **New → Blueprint** and connect the GitHub repository.
2. Render reads `render.yaml` from the repository root.
3. When prompted for `CORS_ORIGINS`, enter the exact frontend production origin, for example `https://labelguard.vercel.app`. Do not include a trailing slash. Multiple exact origins can be comma-separated.
4. Keep `GEMINI_ENABLED=true` and add `GEMINI_API_KEY` as a Render secret. Gemini is the required image reader and there is no OCR fallback. Keep the key backend-only; never create a `NEXT_PUBLIC_GEMINI_*` variable.
5. Confirm that the disk is mounted at `/var/data` and `LABELGUARD_DATA_DIR` has the same value.
6. Deploy and wait for `https://YOUR-SERVICE.onrender.com/system/status` to return database, Gemini model route/rate-limit, and rule-engine readiness without exposing the key.

The persistent disk makes this a single-instance deployment. Do not enable autoscaling while SQLite/local media are in use.

## Frontend on Vercel

1. Import the same GitHub repository into Vercel.
2. Set **Root Directory** to `frontend`.
3. Keep the detected Next.js build command (`npm run build`).
4. Add `NEXT_PUBLIC_API_BASE_URL=https://YOUR-SERVICE.onrender.com` for Production and Preview as appropriate.
5. Deploy the frontend.
6. If the final Vercel URL differs from the origin entered in Render, update `CORS_ORIGINS` in Render and restart the backend.

## Post-deploy smoke test

1. Open `/system`; confirm the database, required Gemini extraction route/rate limit, and seven deterministic rules are ready.
2. Upload the synthetic readable domestic fixture.
3. Verify detail, original/evidence image, correction/rule rerun, review, history, and PDF.
4. Check both browser console and Render logs for errors.
5. Test at mobile width.

## Production blockers

Before a public operational pilot, implement authentication/RBAC, tenant-level data authorization, Postgres/object storage, distributed throttling/job execution, encryption/retention policy, centralized redacted observability, backup/restore drills, and a qualified legal review of the active rule corpus.

Deployment credentials and final public access remain user-controlled. They are never stored in this repository.
