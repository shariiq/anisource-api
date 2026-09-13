# AniSource Web

This directory is an independent SolidJS/Vite single-page application. In production it is deployed from `web/` to Vercel; the FastAPI service remains deployed independently on Render.

## Vercel deployment

Configure the Vercel project with:

- **Root Directory:** `web`
- **Framework Preset:** Vite
- **Build Command:** `npm run build`
- **Output Directory:** `dist`

`vercel.json` provides SPA rewrites so deep links such as `/anime/:id`, `/browse`, `/search`, `/schedule`, `/list`, and `/watch/:id` serve `index.html`. It gives content-hashed files under `/assets/` immutable one-year browser caching and requires browsers to revalidate `index.html` on each deployment.

## Environment variables

The application makes direct browser requests:

| Variable | Production default | Purpose |
| --- | --- | --- |
| `VITE_ANILIST_ENDPOINT` | `https://graphql.anilist.co` | AniList GraphQL catalog and discovery endpoint. |
| `VITE_ANISOURCE_API_URL` | `https://anisource-api.onrender.com` | AniSource Render API origin used only after a Watch or Resume action. |

Set `VITE_ANISOURCE_API_URL` to a local API origin (for example `http://127.0.0.1:8000`) during local frontend/API development. The Vite development proxy remains available for `/api` requests used by other local tools, but this application uses the configured absolute API origin so it behaves the same locally and in production.

Catalog, search, schedule, details, and My List use AniList only. AniSource source discovery, title matching, episodes, servers, and streams are initiated exclusively within the lazy Watch/Resume workflow.

## CORS on Render

Set `ANIME_API_CORS_ORIGINS` in the Render service to a comma-separated allowlist of the exact Vercel production origin and any custom frontend origin **after that origin is assigned**. Do not commit or configure a guessed Vercel URL. For example, once the deployment URL is confirmed:

```text
ANIME_API_CORS_ORIGINS=<confirmed-vercel-origin>,<confirmed-custom-origin>
```

After deployment, verify the Render API returns the expected CORS header by substituting the confirmed origin:

```bash
curl -i -X OPTIONS https://anisource-api.onrender.com/api/v1/sources \
  -H "Origin: <confirmed-vercel-origin>" \
  -H "Access-Control-Request-Method: GET"
```

The response must include `Access-Control-Allow-Origin: <confirmed-vercel-origin>` and allow `GET`. Live-origin verification remains pending until Vercel supplies the actual production origin.

## Optional self-hosted deployment

For a single-process local/self-hosted installation only, the backend can serve a packaged copy of the SPA through `anime_extensions_api.app.UIStaticFiles`:

```bash
npm run package
```

This explicit command builds `dist/` and copies it into `anime_extensions_api/static/app/`. It is **not** the Vercel production workflow; Vercel runs only `npm run build` and serves `dist/` directly.
