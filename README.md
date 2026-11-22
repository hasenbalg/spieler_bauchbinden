# spieler_bauchbinden

Broadcast name-bugs ("Bauchbinden") for handball live streams. Keeps a player
roster in PostgreSQL, renders transparent PNG name banners at the exact
resolution of your broadcast stream, and exports them all in one click —
built to sit on top of a live picture via chroma keying, the same way
[handball_scorebug](https://github.com/hasenbalg/handball_scorebug) does on
handballsociety.com.

## Features

- Player roster stored in Postgres — photos (PNG with alpha) and the club logo
  are saved **inside the database** as bytea blobs, no file storage needed
- Club logo upload, editable broadcast resolution (720p → 4K presets + free
  input), accent and bar colors
- Banner renderer (Pillow): logo, jersey number chip, player name, optional
  transparent player photo; output is a full-resolution transparent PNG,
  drop-in for OBS / vMix / ATEM
- Live preview page with chroma-green backdrop to check the keying
- Bulk export: every player's banner as one ZIP
- Flask + gunicorn + PostgreSQL + Caddy, deployed with docker compose

## Run (Docker — recommended)

```bash
docker compose up --build -d
```

Open http://localhost/ — control panel on `/`, preview on `/preview`,
bulk export on `/export.zip`.

## Run locally without Docker

```bash
python3 -m venv env
env/bin/pip install -r requirements.txt -r requirements-dev.txt

# start a PostgreSQL 17 on localhost:5432 with user/password/db = bauch
export DATABASE_URL=postgresql+psycopg://bauch:***@localhost:5432/bauchbinden
env/bin/python app/app.py
```

## Tests

Against a throwaway Postgres:

```bash
docker run -d --name bbtest -p 55432:5432 \
  -e POSTGRES_USER=bauch -e POSTGRES_PASSWORD=*** -e POSTGRES_DB=bauchbinden_test \
  postgres:17-alpine
DATABASE_URL=postgresql+psycopg://bauch:***@localhost:55432/bauchbinden_test \
  env/bin/pytest -q
```

## CI/CD

`.github/workflows/ci-cd.yml` (derived from the handballsociety.com deploy
pattern — Flask container behind Caddy, compose on the server):

1. **test** — pytest against a `postgres:17-alpine` service container
2. **docker** — image build on every PR
3. **deploy** (push to `main` only) — publish image to GHCR and restart the
   compose stack on the server over SSH

For the deploy step to actually reach a server, set the repository secrets
`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` and keep a checkout of this
repo (with `compose.yaml`) in `~/bauchbinden` on the server, where the
`ghcr.io/hasenbalg/spieler_bauchbinden` image is pulled. Without those
secrets the deploy step publishes the image and skips the server hop.

## License

MIT
