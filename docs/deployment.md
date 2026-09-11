# Deployment and submission

Deployment files are prepared. No public service or repository was created here.
GitHub, Render and Railway connections were unavailable under the workspace's
administrator policy. Docker and package-registry access were also unavailable.
The required remaining actions are account setup, a container build, real provider
verification and public endpoint verification.

## 1 Create the public source repository

Unzip the project and create a public repository in your GitHub account. Upload
the project contents or use the commands GitHub supplies for that repository.
Run `git status` before committing. `.env`, database files, virtual environments
and runtime outputs are ignored. Never upload your actual API or database tokens.

The ZIP includes sample OCR text from the supplied assessment dataset. Review
dataset redistribution permission before publishing those sample artifacts. Do
not upload unrelated personal documents to the public demo.

## 2 Create persistent database storage

Create a Turso account and database. Copy its database URL and an auth token into
the deployment platform's secret environment fields. This project talks directly
to Turso's documented HTTPS SQL endpoint, so no extra database driver is needed.

Use `DATABASE_BACKEND=turso`. Set `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`.
Schema creation occurs on application startup. The token needs permission to
create the documents table/index and read/write its records. Test account limits
and continued database availability during the evaluation period.

Turso HTTP contract: [SQL over HTTP](https://docs.turso.tech/sdk/http/quickstart).
This integration was tested against mocked protocol responses; a live database
connection and durability across a hosted restart still need verification.

## 3 Configure the model

Obtain your own Gemini API key from Google AI Studio. Set `GEMINI_API_KEY` and
`LLM_MODEL=gemini-2.5-flash`, or another available compatible model after checking
its structured-output support. Confirm the selected model and quota are available
to your account. No free quota or cost entitlement is assumed.

## 4 Deploy the Docker application on Render

1. Connect the public GitHub repository to Render.
2. Create a Blueprint from `render.yaml`, or create a Docker Web Service from the
   repository root with the supplied `Dockerfile`.
3. Select the free service plan if available to your account.
4. Add `GEMINI_API_KEY`, `LLM_MODEL`, `DATABASE_BACKEND=turso`,
   `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, and `MAX_CONCURRENT_DOCUMENTS=1`.
5. Use the Dockerfile's command: `python -m backend.app.main`. Render supplies
   `PORT`; the app binds to `0.0.0.0` and that port.
6. Set the health-check path to `/api/v1/health`.
7. Deploy and wait for successful startup. Resolve dependency/build failures from
   the build logs before sharing the service URL.

The same service hosts the frontend and backend. Leave `ALLOWED_ORIGINS` empty
for this arrangement. If the frontend is deliberately hosted separately, set an
exact allowed origin and update its API URL handling; the supplied frontend uses
same-origin requests.

Free Render storage is ephemeral, and free services can sleep. Use the external
database and open the service before the interview. Do not switch to local SQLite
on the free service. A paid persistent-disk alternative can use
`DATABASE_PATH=/var/data/documents.sqlite3` with a disk actually mounted at that path.
[Render hosting documentation](https://render.com/docs/docker),
[free-service limits](https://render.com/docs/free).

## 5 Verify the live submission

Use the actual HTTPS origin shown in the hosting dashboard. Do not submit a
predicted URL or localhost URL.

1. Open `/` and `/docs`. Confirm the Swagger interface and `/openapi.json` load.
2. Request `/api/v1/health?ready=true`. Confirm database availability, OCR
   availability and configured model readiness.
3. Upload one representative document of each type, including the native 2022
   cash-flow PDF and an invoice image. Health alone does not verify the model key.
4. Compare every key total and a selection of line-item/table values to the source.
   Check both reporting years and bracketed negative amounts. Record omissions and
   errors; improve extraction if the live run is incomplete.
5. Test a corrupt file, a four-page PDF and an unsupported extension.
6. Confirm list/get endpoints and the dashboard agree on stored results.
7. Restart/redeploy the service and retrieve the previous results again.
8. Reprocess the same filename and check that GET returns its latest result.
9. Run the browser smoke workflow; manually test the actual public UI as well.

To generate actual live sample outputs, run the dataset evaluator with `--api`
set to the real service origin. Replace fixture replays in the submitted demo
evidence with these live-provider results once verified.

## 6 Record the verified URLs

Submit the actual public GitHub URL and the host's actual origin as the frontend
and backend base URL. Append `/docs` for Swagger and `/api/v1/health` for health.
Record the date and results of verification in the README. No public URLs are
listed here because none were deployed or verified during this build.
