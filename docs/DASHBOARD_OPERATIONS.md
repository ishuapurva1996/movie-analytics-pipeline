# Dashboard operations

The approved movie dashboard is live at [the Movie Observatory](https://ishuapurva1996.github.io/movie-analytics-pipeline/). It is packaged as `index.html` for GitHub Pages; `redesign.html` remains an alias. The artifact includes the light/dark toggle, all nine charts, four KPIs, two movie highlights, and both selectors. The original dashboard remains in the source checkout for comparison but is not the deployed homepage.

The [first snapshot deployment](https://github.com/ishuapurva1996/movie-analytics-pipeline/actions/runs/37695898993) succeeded on October 7, 2026. The public JSON matched the reviewed SHA-256, and browser verification passed for all nine charts, desktop/mobile layout, role and country selectors, themes, and News exclusion.

Automatic publication is now enabled with `DASHBOARD_PUBLICATION_MODE=airflow`. On October 7, 2026, all ten Airflow tasks succeeded, including the validated S3 export and GitHub dispatch. That initial dispatch occurred before the mode switch; after configuration and S3 reader permissions were corrected, a [manual deployment of the exported bundle](https://github.com/ishuapurva1996/movie-analytics-pipeline/actions/runs/37705105560) succeeded. The public checksum matched the private export. All nine charts, role and market selectors, themes, and News exclusion were checked on the live site. The warehouse build completed at `2026-10-07T23:34:32.007880Z`; TMDB capture dates are October 7. Subsequent successful runs dispatch the enabled workflow automatically.

## Reviewed snapshot publication

The alternative [Publish dashboard snapshot workflow](../.github/workflows/deploy-dashboard-snapshot.yml) publishes the approved design with `web_dashboard/snapshot/dashboard.json` when automatic mode is not enabled. This is the existing October 5, 2026 warehouse export, with News titles excluded and its original completion, export, and capture dates retained. It contains only the public analytics contract; credentials and private infrastructure details are absent.

The workflow runs on relevant changes to `main` or manual dispatch. It checks the committed SHA-256, schema and semantics, rejects synthetic data, assembles only allowlisted assets, and verifies the public JSON checksum after deployment. A rerun resolves current `main`; if it changes after artifact upload, publication stops instead of deploying an obsolete artifact. Pages must use GitHub Actions with the `github-pages` environment restricted to `main`. No AWS credentials or Airflow dispatch token are needed for this route.

Data updates are manual in snapshot mode: replace the reviewed export and its checksum together, validate and merge the change, then verify the Pages run. Redeploying the frontend does not refresh warehouse data. For local assembly:

```bash
python scripts/build_dashboard_site.py --snapshot --state /tmp/movie-dashboard-selection.json
```

For a new installation, complete the private configuration below, verify the complete ten-task pipeline and private handoff, then set the repository variable `DASHBOARD_PUBLICATION_MODE` to `airflow`. This disables snapshot publication and enables the existing S3 workflow. Both modes share one Pages concurrency group. This repository has completed those steps.

The dedicated Airflow API reader is configured and its metadata access was checked; Connections and Variables access returned 403. GitHub Pages uses Actions, and the `github-pages` environment allows only `main`. Bucket/prefix Actions secrets, the region variable, the Airflow dispatch token, and the AWS OIDC read role are configured. The owner added a dashboard-only `s3:GetObject` policy to the reader role; AWS authentication and both export reads succeeded in the verified deployment. The local AWS principal cannot inspect IAM or bucket security, so effective bucket controls still require an administrator's review. Recreate Airflow services after changing private environment configuration. The owner confirmed on October 2, 2026 that permission covers this dashboard’s public aggregates and ranked movie/person rows.

## Automatic Airflow publication flow

The schedule remains Monday at 6:00 AM `America/Los_Angeles`. The original eight ingestion, RAW-loading, and dbt tasks retain full-refresh behavior. Two dependent tasks add publication:

1. `dbt_build` emits an attempt-specific completion receipt only after its command exits successfully. `export_dashboard_bundle` requires that receipt to match the current task instance, run, attempt, and DAG version, with both receipt timestamps inside that successful attempt's interval. Airflow records supervisor and worker start times separately, so exact timestamp equality is not required. It then checks the current run's eight successful predecessors and dbt attempt history through Airflow's REST API. Manually marking a failed task successful cannot create the receipt. It rejects changed upstream tasks, overlapping or later warehouse writes, and incomplete metadata. It checks eligibility again after extraction and immediately before advancing the pointer.
2. The exporter reads explicit columns from the analytics tables and bounded capture-date aggregates from `CURATED.FCT_NOW_PLAYING`. It validates the [schema](../web_dashboard/data-contract.schema.json), numeric ranges, ranks, row limits, US/India coverage, and a maximum JSON size of 2 MiB. Unknown values remain `null`. See [metric definitions](DASHBOARD_METRICS.md).
3. It writes the validated bytes to `<DASHBOARD_S3_PREFIX>/bundles/<sha256>.json`, verifies those bytes, then conditionally updates `<DASHBOARD_S3_PREFIX>/latest-success.json`. A conditional S3 write prevents silently overwriting a concurrently changed pointer. An older warehouse completion cannot replace a newer pointer.
4. `dispatch_dashboard_pages` calls the configured GitHub workflow on `main`. HTTP 204 means GitHub accepted the request. It does not mean the site deployed.
5. [Deploy dashboard](../.github/workflows/deploy-dashboard.yml) serializes publication through one concurrency group. It resolves current `main` and the current private pointer, verifies the checksum and contract, and assembles a complete Pages artifact. Before deployment it rechecks both inputs and rebuilds if either changed. Repeated changes fail the run with the existing site preserved.
6. After Pages deploys, the workflow fetches the public `data/dashboard.json` and checks its SHA-256 against the selected bundle. The Actions summary records the selected code commit, bundle ID, and timestamps.

The export task has a ten-minute execution limit. Each Snowflake query has a 120-second timeout; its connection uses 30-second login/socket and 60-second network timeouts. A timeout fails the task for normal Airflow retry without advancing the pointer.

The browser receives only static assets and the bounded public JSON. The S3 pointer, Airflow run ID, credentials, raw files, dbt artifacts, warehouse connection details, and private object locations stay out of the Pages artifact. Synthetic fixtures are rejected in production. There is no first-run sample-data fallback.

## Private Airflow configuration

Keep values in `.env` or your private secret-management system. Do not paste secrets into command arguments, screenshots, issue bodies, or task logs. Compose passes `.env` to the Airflow services and mounts the schema read-only.

| Setting | Value or purpose |
| --- | --- |
| `S3_BUCKET_NAME` | Existing private pipeline bucket; also used for dashboard handoff. |
| `DASHBOARD_S3_PREFIX` | `dashboard/v1`, or another dedicated `dashboard/<name>` prefix without a trailing slash or `..`. |
| `DASHBOARD_GITHUB_REPOSITORY` | `ishuapurva1996/movie-analytics-pipeline`. |
| `DASHBOARD_GITHUB_WORKFLOW` | `deploy-dashboard.yml`. |
| `DASHBOARD_GITHUB_TOKEN` | Expiring fine-grained token for this repository only, with Actions read/write permission. |
| `DASHBOARD_AIRFLOW_API_URL` | `http://airflow-apiserver:8080` inside Compose; use HTTPS for a remote server. No embedded credentials or query string. |
| `DASHBOARD_AIRFLOW_USERNAME` | Dedicated reader account for this DAG's task metadata. |
| `DASHBOARD_AIRFLOW_PASSWORD` | Private password for that reader. |
| `DASHBOARD_SCHEMA_PATH` | Compose sets `/opt/airflow/project/web_dashboard/data-contract.schema.json`; normally leave unchanged. |
| `AIRFLOW_CONN_SNOWFLAKE_CONN` | Existing `snowflake_conn` connection for RAW loading, dbt, and export reads. |
| AWS credentials | Mounted `~/.aws`, or `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`, and `AWS_DEFAULT_REGION`. Prefer temporary credentials. |

The existing TMDB, stage, and file-format settings remain required; see [.env.example](../.env.example) and [Airflow setup](../AIRFLOW_SETUP.md). Recreate the Airflow services after rotating environment values.

### Airflow API reader

Create a separate FAB role with `can_read` on the registered DAG resource for `movie_analytics_pipeline` (normally `DAG:movie_analytics_pipeline`), `DAG Runs`, and `Task Instances`. Assign only that role to the reader. Do not grant global DAG access, mutation permissions, Connections, Variables, XComs, or administrative roles. Resource names must match the running FAB installation. These endpoints require DAG, DAG-run, and task-instance read permissions in the [official FAB access-control reference](https://airflow.apache.org/docs/apache-airflow-providers-fab/stable/auth-manager/access-control.html).

The publisher authenticates with `POST /auth/token`, then sends the returned bearer token to:

- `GET /api/v2/dags/movie_analytics_pipeline/dagRuns/<run-id>/taskInstances`.
- `GET /api/v2/dags/movie_analytics_pipeline/dagRuns/<run-id>/taskInstances/dbt_build/tries?map_index=-1`.
- `GET /api/v2/dags/movie_analytics_pipeline/dagRuns/~/taskInstances`, filtered separately for each warehouse-mutating task.

Verify that the reader can access these routes, including filters and pagination, while mutation and secret-reading routes remain denied. The `~` scan spans runs of this DAG; it is needed to detect warehouse writes from another run. The code uses the supported REST API rather than direct metadata-database access. Tokens are acquired anew when the export task starts; an expired token during a long attempt fails eligibility safely, and a retry obtains a new one.

### GitHub dispatch credential

Create a fine-grained personal access token with access only to this repository and **Actions: read and write**, as required by [Create a workflow dispatch event](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event). Set an expiry and privately record the owner and rotation date. Store it only on the Airflow side. It does not need Contents write, AWS, or Snowflake access.

Rotate before expiry: create a replacement with the same scope, update `DASHBOARD_GITHUB_TOKEN`, recreate the services, verify a dispatch, then revoke the old token. HTTP 401/403 can indicate expiry, revocation, approval restrictions, or insufficient permission; 404 can also indicate inaccessible repository/workflow configuration. Do not widen permissions to diagnose a typo. A timed-out dispatch may already have been accepted; check Actions before retrying. Duplicate requests are safe because deployment selects current inputs.

## AWS and GitHub Pages setup

The Airflow publisher writes private handoff objects. GitHub Actions assumes a separate read-only AWS role through OpenID Connect (OIDC), which exchanges GitHub's identity token for temporary AWS credentials. GitHub needs no stored AWS access keys.

An AWS administrator must verify that the bucket has all S3 Block Public Access settings enabled, no public policy or ACL, and encryption at rest. Keep dashboard objects private even though selected contents later become public through Pages. Use a dedicated prefix, enable versioning for recovery, and keep the existing ingestion prefixes outside the dashboard reader's access.

The following are **placeholder templates**, not records of installed permissions. Replace every angle-bracket placeholder with the intended private value. Review effective permissions, permission boundaries, bucket policies, and any organization controls before testing.

Attach this object policy to the Airflow publishing principal in addition to its existing ingestion permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": [
        "arn:aws:s3:::<BUCKET>/<DASHBOARD_PREFIX>/latest-success.json",
        "arn:aws:s3:::<BUCKET>/<DASHBOARD_PREFIX>/bundles/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::<BUCKET>"
    }
  ]
}
```

Attach this policy to the GitHub OIDC role:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "s3:GetObject",
    "Resource": [
      "arn:aws:s3:::<BUCKET>/<DASHBOARD_PREFIX>/latest-success.json",
      "arn:aws:s3:::<BUCKET>/<DASHBOARD_PREFIX>/bundles/*"
    ]
  }]
}
```

Neither principal needs dashboard object deletion. The builder reads known keys and does not list bundles. The publisher's bucket-level `s3:ListBucket` allows a missing first pointer to return 404 instead of 403; it also permits listing object names in that bucket, so review it alongside this principal's existing ingestion access. The Pages reader has no listing permission and may receive 403 for an absent pointer; an administrator should distinguish a missing first bundle from a permission failure. Never seed the pointer with a synthetic or unvalidated bundle. If the bucket uses a customer-managed KMS key, also scope the required decrypt/encrypt permissions to that key and these roles.

Configure the role trust for the exact repository's `github-pages` environment:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::<AWS_ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub": "<EXACT_REPOSITORY_GITHUB_PAGES_ENVIRONMENT_SUBJECT>"
      }
    }
  }]
}
```

The legacy subject form is `repo:<OWNER>/<REPOSITORY>:environment:github-pages`. Repositories using immutable subject claims include owner/repository IDs; confirm the exact format before applying the policy. Match it exactly, without a repository-wide wildcard. Because an environment subject does not itself name `main`, restrict the GitHub environment to `main` as well. See [GitHub's AWS OIDC guide](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).

In GitHub repository settings:

1. Select **GitHub Actions** as the Pages build/deployment source.
2. Configure the `github-pages` environment with a deployment branch rule allowing **only `main`**, not tags or feature branches. Retain any required reviewers appropriate to the repository.
3. Add these repository Actions settings. Store private infrastructure identifiers as secrets so GitHub masks them in runner logs:

| Repository setting | Storage | Meaning |
| --- | --- | --- |
| `DASHBOARD_AWS_ROLE_ARN` | Actions secret | ARN of the provisioned read-only OIDC role. |
| `DASHBOARD_AWS_REGION` | Actions variable | Region containing the private bucket. |
| `DASHBOARD_S3_BUCKET` | Actions secret | Same bucket as Airflow's `S3_BUCKET_NAME`. |
| `DASHBOARD_S3_PREFIX` | Actions secret | Same dedicated prefix as Airflow's setting. |

The deployment job also checks this repository and `refs/heads/main`, and requests only Contents read, Pages write, and ID token write. Pull-request validation has no production credential access. Do not grant the Pages role Snowflake access or S3 write access.

## First automatic publication and routine verification

Complete AWS/reader/token setup and the `github-pages` restrictions before enabling automatic Airflow publication. Source permission for this dashboard was confirmed by the owner on October 2, 2026. Merge the implementation to `main`, make that DAG available to Airflow, and run the complete DAG. No earlier dbt-only run substitutes for this verification. Runs predating the success-only completion receipt are deliberately ineligible; run the complete DAG after merging the implementation.

Confirm all ten Airflow tasks succeeded. Privately compare the S3 pointer with the immutable bundle: checksum, bundle ID, schema version, warehouse completion, and export time must agree. Then inspect the **Deploy dashboard** run for the selected current-main commit, Pages deployment, and successful public checksum check. Check that private bucket, prefix, account, and role identifiers are masked in runner logs. Open the site at the URL returned by Pages and verify that its displayed bundle/timestamps match, both markets render, and stale/unavailable states are clear. Record a live README link only after this check succeeds.

The site displays an eight-day warning based on warehouse completion or either TMDB capture date. Export time is not source capture time. A local scheduler cannot refresh while its host or Docker services are stopped.

### Manually redeploy the latest valid bundle

Use GitHub **Actions → Deploy dashboard → Run workflow → main** after setup. There is no arbitrary commit, object key, or bundle input: the workflow resolves current `main` and the latest valid pointer after acquiring its publication lock. This supports UI-only updates and retrying deployment after an infrastructure failure without rebuilding the warehouse. Relevant pushes to `main` trigger the same process automatically.

## Failure recovery

| Failure | Recovery |
| --- | --- |
| Source extraction, enrichment, RAW load, or dbt fails | Fix the cause and run the complete DAG. Full refreshes replace tables independently; partially refreshed warehouse contents are not eligible for publication. |
| Export says predecessors changed, another run touched the warehouse, or history is incomplete | Run the complete DAG. Do not mark tasks successful or clear just the exporter to bypass provenance checks. |
| Contract, coverage, rank, or checksum validation fails | Correct the data/model or code and rerun the appropriate complete build. Do not weaken validation or substitute a fixture. |
| Private upload fails | Check private credentials, bucket/prefix policy, encryption permissions, and network access. An unreferenced immutable bundle is harmless; retry the task only while its source run remains eligible. |
| Pointer update outcome is unconfirmed | Inspect the pointer privately and compare its bundle ID/checksum with the attempted export. A lost response may follow a successful write. Retry only after checking the current pointer and run eligibility. |
| Export succeeded but dispatch failed | Rotate or repair the dispatch configuration. Retry the dispatch task or manually run the `main` workflow; the accepted private bundle remains available. |
| GitHub OIDC, environment, or assembly fails | Repair the scoped role or environment/secret/variable settings, then manually redeploy the latest bundle. Predeployment failures preserve the last successful site. |
| Code or pointer keeps changing | Let changes settle, then manually run the workflow. Do not deploy an earlier artifact from a queued run. |
| Pages deploy succeeded but public checksum verification failed | Inspect the deployed URL and artifact before claiming success. The new deployment may already be visible; this check does not automatically restore the previous site. Rerun current-main publication once the cause is resolved. |
| No first bundle exists | Complete setup and one full DAG run. Keep the first deployment failed rather than publishing invented data. |

Intentional code rollback is a new reviewed revert commit on `main`, followed by a fresh deployment. Do not rerun an old event to restore old code; deployment deliberately resolves current `main`. Intentional data rollback requires a separately authorized pointer change to a retained, checksum- and contract-validated immutable bundle. Preserve its original warehouse/export timestamps so age remains visible, record the operator's reason privately, and deploy through the normal current-main workflow. Automatic publication refuses to move the pointer backward in warehouse time.

## Metadata and bundle retention

Airflow metadata and the success-only dbt completion receipt are publication evidence. Preserve the candidate dbt task’s return-value XCom along with its task and attempt history; missing evidence fails publication safely. Task-instance scans use pages of 100 and stop after 10,000 rows; dbt attempt history is also bounded at 10,000. Monitor growth before reaching those limits. Keep at least 90 days of completed run/task/attempt metadata as an initial operational policy, and always preserve the latest candidate, all active runs, their attempts, and any overlapping or later warehouse mutations. Clean up only terminal runs older than that window, while publication is paused. A deleted history row cannot prove that a warehouse write never occurred; after disruptive metadata cleanup, require a new complete DAG before publishing.

For private S3 bundles, use an explicit bounded policy such as the latest 12 successful bundles plus any bundles deployed within 90 days. Always retain the current `latest-success.json` target, the currently deployed bundle, and bundles referenced by active deployments or an authorized recovery. Resolve those references again immediately before deletion. A separate maintenance principal should perform reviewed deletion; the publisher and Pages role have no delete permission. Do not apply a blanket age-based expiration rule to `latest-success.json` or all bundles: a prolonged outage must not expire the last good data. Retain pointer versions and any KMS key needed to read retained objects according to the recovery policy.

## Source terms and attribution

On October 2, 2026, the owner confirmed that their permission covers this dashboard’s public aggregates and ranked movie/person rows. This records the owner’s confirmation; it does not extend permission to other uses or new public fields. Preserve the required attribution and source restrictions. See [IMDb's usage conditions](https://help.imdb.com/article/imdb/general-information/can-i-use-imdb-data-in-my-software/G5JTRESSHJBBHTGX).

The bundled `web_dashboard/assets/tmdb-logo.svg` is the unmodified primary-short logo from [TMDB's official attribution page](https://www.themoviedb.org/about/logos-attribution). Preserve this approved logo in the dashboard's credits and the notice: “This product uses the TMDB API but is not endorsed or certified by TMDB.” Check that the logo renders on the deployed site and remains less prominent than the application's branding. Commercial use has separate licensing requirements. See [TMDB's attribution guidance](https://developer.themoviedb.org/docs/faq). Do not add posters, raw source downloads, or new public fields without checking their terms and the public data contract.
