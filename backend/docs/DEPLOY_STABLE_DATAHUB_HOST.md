# Stable DataHub Host (replaces the temporary tunnel)

## Why

The MCP/GraphQL live-metadata validations recorded in the top-level README
(`Live metadata-context endpoint validation`) depended on a local DataHub
instance behind a temporary Cloudflare quick tunnel, run with
`METADATA_SERVICE_AUTH_ENABLED=false`, and closed immediately after capture.
That is unsuitable for the hackathon judging window (through
2026-08-31): the deployed Render backend needs `DATAHUB_GMS_URL` to resolve
to something that (a) does not expire, (b) is not an unauthenticated
instance sitting on the open internet, and (c) is not tied to this
workstation's uptime.

This document replaces the tunnel with a small, permanent, authenticated
DataHub host.

## Why not repeat the WSL Docker Desktop path

`docs/spike/DATAHUB_SPIKE.md` recorded a hard blocker: Docker Desktop's
port-forwarding layer on WSL2 refused to publish MySQL's port 3306 no matter
which override was used. That failure is specific to Docker Desktop's WSL
integration, not to DataHub or Docker Compose in general. Running the same
`datahub docker quickstart` on a plain Linux VM with native Docker Engine
avoids that failure mode entirely.

## Provider and sizing

DataHub's Quickstart guide is tested against an 8 GB configuration; the
previous spike ran with only 7.7 GB available, which the CLI itself flagged.
Pick a VM with **8 GB RAM minimum**.

- Recommended: **Hetzner Cloud, CX32** (4 vCPU / 8 GB RAM / 80 GB disk),
  ~€13-14/mo. Cheapest option that meets the RAM floor.
- Fallback if Hetzner signup/ID verification is too slow before the
  submission deadline: **DigitalOcean, 8 GB Basic droplet**, ~$48/mo. Same
  steps below, just created through DO's console instead.
- OS image: **Ubuntu 22.04 LTS**.
- Add an SSH key at creation time; do not rely on a mailed root password.

Budget note: at Hetzner pricing, running this from now through the end of
judging (2026-08-31) costs roughly €15-20 total. Destroy the VM once judging
ends.

## Hostname without buying a domain

Use **sslip.io**: `<anything>.<a-b-c-d>.sslip.io` resolves to IP `a.b.c.d`
automatically, with no registration. It is a real public DNS name, so
Caddy/Let's Encrypt can issue it a real certificate. Once the VM has a
public IP, e.g. `203.0.113.5`, the GMS hostname becomes:

```text
datahub.203-0-113-5.sslip.io
```

## Setup steps (run on the VM as root over SSH)

1. Install Docker Engine + Compose plugin from Docker's official apt repo
   (not the `docker.io` snap, not Docker Desktop):

   ```bash
   curl -fsSL https://get.docker.com | sh
   ```

2. Install the DataHub CLI:

   ```bash
   apt-get update && apt-get install -y python3-pip
   pip install --break-system-packages acryl-datahub
   datahub version
   ```

3. Lock the firewall down before starting anything:

   ```bash
   ufw allow 22/tcp
   ufw allow 80/tcp
   ufw allow 443/tcp
   ufw enable
   ```

   GMS (8080) and the frontend (9002) must **not** be opened on the public
   firewall — they stay reachable only via `localhost`, fronted by Caddy.

4. Start DataHub with auth enabled (this is the flip side of the
   `METADATA_SERVICE_AUTH_ENABLED=false` instance described in the
   top-level README — do not repeat that with a public IP):

   ```bash
   METADATA_SERVICE_AUTH_ENABLED=true datahub docker quickstart
   ```

   Wait for GMS and frontend to report healthy (`docker ps`).

5. Load a richer demo dataset than the single `ORDER_DETAILS` URN used in
   the earlier live validation:

   ```bash
   datahub datapack load showcase-ecommerce
   ```

6. Log into the frontend UI at `http://localhost:9002` (SSH port-forward:
   `ssh -L 9002:localhost:9002 root@<vm-ip>`) with the default `datahub` /
   `datahub` credentials, then **Settings → Access Tokens → Generate
   Personal Access Token**. Copy the token; it is shown once.

7. Install Caddy and point it at GMS only:

   ```bash
   apt-get install -y caddy
   ```

   `/etc/caddy/Caddyfile`:

   ```text
   datahub.203-0-113-5.sslip.io {
       reverse_proxy localhost:8080
   }
   ```

   (substitute the VM's real IP with dashes). Reload:

   ```bash
   systemctl reload caddy
   ```

8. Verify from outside the VM:

   ```bash
   curl --fail \
     -H "Authorization: Bearer <token>" \
     -H 'Content-Type: application/json' \
     -d '{"query":"{ __typename }"}' \
     https://datahub.203-0-113-5.sslip.io/api/graphql
   ```

## Point the deployed backend at it

In the Render dashboard, set on the backend service:

```bash
SHERLOCK_METADATA_MODE=auto
DATAHUB_GMS_URL=https://datahub.203-0-113-5.sslip.io
DATAHUB_GMS_TOKEN=<token from step 6>
```

`auto` is deliberate: if the VM ever goes down mid-judging, the app falls
back to the labelled snapshot instead of returning an error, per the
provider-selection behavior already implemented in
`backend/src/sherlock/connectors/datahub/provider.py`. Redeploy the backend,
then re-run the same live check already documented in the top-level README
(`GET /api/v1/metadata/context?urn=...`) against the deployed Render URL to
confirm `source=mcp`, `live=true`.

## After it's verified live

Update the top-level README's "DataHub MCP Integration Status" section:
replace the "temporary tunnel, closed immediately" language with the
persistent, authenticated host described here, and note the token is
stored only in Render's environment configuration, never committed.

## Teardown

Destroy the VM after the judging period ends (2026-08-31) to stop billing.
