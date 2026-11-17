# Local development

From the repository root:

```bash
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt
cp -n config.example.yaml config.yaml
venv/bin/python sample_board.py
venv/bin/python dev.py
```

The launcher starts the dashboard and the separate marketing site on loopback, without a database.
The dashboard uses `DINKYDASH_PORT` (default 5000) and the site uses `DINKYDASH_WEBSITE_PORT`
(default one higher). Conductor supplies `CONDUCTOR_PORT` for the dashboard; the site uses the
next port. Both stop together. Restart the command after Python or content changes.

The launcher disables feedback email so a copied SendGrid key cannot send from a preview. To test
parent sign-in, set both `DINKYDASH_PARENT_PASSWORD` and a private `DINKYDASH_SECRET_KEY` in the
environment or `.env`. Keep local data and secrets out of commits.
