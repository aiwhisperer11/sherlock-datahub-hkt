# DataHub Technical Spike

Date: 2026-07-23

## Scope

This is a validation-only spike. It does not modify the Evidence Engine, deploy services, configure a remote, or store credentials. No DataHub URN, MCP tool, asset metadata, lineage, freshness signal, or quality signal is inferred below unless it was observed locally.

## Official sources consulted

- [DataHub Quickstart Guide](https://docs.datahub.com/docs/quickstart) (DataHub 1.6.0): requires Docker plus Compose v2, Python 3.10+, installs the CLI with `acryl-datahub`, and starts the local instance with `datahub docker quickstart`.
- [DataHub MCP Server guide](https://docs.datahub.com/docs/features/feature-guides/mcp): the self-hosted server requires `uv`, a reachable GMS endpoint, and a token passed only at process startup.

## Prerequisite results

| Requirement | Command | Observed result | Status |
| --- | --- | --- | --- |
| Docker daemon | `docker version --format 'Server {{.Server.Version}}'` | `Server 29.5.3`; daemon access succeeded. | Pass |
| Docker resources | `docker info --format 'CPUs={{.NCPU}} Memory={{.MemTotal}}'` | `CPUs=8`, `Memory=8269295616` bytes (~7.7 GiB). | Pass, below the guide's tested 8 GiB configuration |
| Existing containers | `docker ps -a` | Four unrelated containers were already stopped. They were not started, removed, or changed. | Pass |
| DataHub CLI | `/tmp/sherlock-datahub-cli-venv/bin/datahub version` | `DataHub CLI version: 1.6.0.15`; installed in a temporary isolated environment. | Pass with Python 3.12 warning |
| Python | `python3 --version` | `Python 3.12.3` | Pass |
| uv | `/home/work/.local/bin/uv --version` | `uv 0.11.31` | Pass |
| Port inspection | `ss -ltn '( sport = :9002 or sport = :8080 )'` | `Cannot open netlink socket: Operation not permitted` | Inconclusive |
| DataHub web reachability | `curl --max-time 3 --fail http://127.0.0.1:9002/` | `curl: (7) Failed to connect to 127.0.0.1 port 9002` | Not running |
| GMS reachability | `curl --max-time 3 --fail http://127.0.0.1:8080/` | `curl: (7) Failed to connect to 127.0.0.1 port 8080` | Not running |

## Quickstart execution

The official command was run without inventing a compose file:

```text
/tmp/sherlock-datahub-cli-venv/bin/datahub docker quickstart --no-pull-images --dump-logs-on-failure
```

The CLI selected its official Quickstart plan `v1.5.0.6` and created the `datahub` stack. Image pull and creation completed, but startup stopped when the new MySQL service attempted to publish port 3306:

```text
Error response from daemon: ports are not available: exposing port TCP
0.0.0.0:3306 -> 127.0.0.1:0: /forwards/expose returned unexpected status: 500
```

At the stop point, `datahub-kafka-broker-1` and `datahub-opensearch-1` were healthy with zero restarts. MySQL, GMS, frontend, actions, system update remained `Created`; none was `unhealthy`, and no OOM or restart was observed. GMS and the frontend never became reachable on 8080 or 9002.

## MySQL port workaround attempt

Before retrying, port 53306 was verified as neither published by a Docker container nor reachable on `127.0.0.1`. The documented CLI workaround was then used exactly once:

```text
/tmp/sherlock-datahub-cli-venv/bin/datahub docker quickstart \
  --mysql-port 53306 --no-pull-images --dump-logs-on-failure
```

Despite the requested override, the Quickstart output again attempted to expose `0.0.0.0:3306` and returned the same Docker `/forwards/expose` HTTP 500 error. The created MySQL container has no published port because it never reached `running`. No additional ports were tried and the existing DataHub stack was left in place.

## Minimal MySQL container recovery

The previously created MySQL container was verified to be the `datahub` Compose project's `mysql` service, in `created` state with `HostPort` 3306. It was then removed without `--force` or volume flags, as authorized. A single replacement Quickstart run used the same official options:

```text
--mysql-port 53306 --no-pull-images --dump-logs-on-failure
```

The replacement `datahub-mysql-1` was created, but its immediately observed port binding was still:

```json
{"3306/tcp":[{"HostIp":"","HostPort":"3306"}]}
```

The startup again failed to publish 3306 with the same `/forwards/expose` HTTP 500 error. Per the recovery gate, no further containers were removed, no ports were tried, and Quickstart was not repeated.

## Compose override fallback

A temporary override was created outside the repository at `/tmp/datahub-mysql-port.override.yml` with only this service change:

```yaml
services:
  mysql:
    ports: !override
      - "53306:3306"
```

The observed Compose service label was `mysql`, and Docker Compose v5.1.4 rendered the official Quickstart Compose file plus the override with one MySQL port entry: published `53306`, target `3306`, protocol `tcp`. This passed the pre-start port gate.

After removing only the `created` MySQL container, `docker compose --profile quickstart ... up -d` was invoked with the official Compose file and that temporary override. Compose warned that required Quickstart variables were unset and failed on the invalid image reference `acryldata/datahub-gms:`. It nevertheless recreated `datahub-mysql-1`, whose immediately observed binding was again HostPort `3306`, not `53306`.

This fallback is therefore not safe to continue: the rendered configuration and the created container diverged, and direct Compose invocation lacks the Quickstart runtime configuration. No additional Compose commands, port attempts, container removals, or secret-file reads were performed.

No existing non-DataHub container, image, or volume was removed or started. The Quickstart's local secret file was not read, copied, or committed; no credential is included in this repository.

## Blocker analysis

Docker Desktop's port-forwarding layer rejected port 3306 with HTTP 500 despite the official `--mysql-port 53306` override and despite 53306 being free. The Compose override rendered correctly but did not become the recreated container's binding, and direct Compose also lacked the Quickstart's runtime variables. This is a deployment/configuration failure, not a catalog or MCP result. The stack cannot progress to MySQL, GMS, or frontend in this state.

The MCP guide requires a reachable GMS endpoint and a token for the self-hosted server. Since local DataHub is not running, installing or starting MCP would not establish a real connection. It was intentionally not attempted, and no token or configuration was written.

The currently published Quickstart guide demonstrates `datahub datapack load showcase-ecommerce`; this spike did not find or execute an official `nyc-taxi` datapack command. It must be discovered from the installed CLI only after the prerequisite gate passes.

## Criteria status

| Success criterion | Status | Evidence |
| --- | --- | --- |
| Local DataHub operational | Blocked | Quickstart failed to start MySQL because Docker could not publish port 3306. |
| NYC Taxi loaded | Not attempted | GMS and frontend never started. |
| Real URN identified | Not available | No catalog query was possible. |
| MCP connected | Not attempted | No reachable GMS; no token stored. |
| MCP inventory generated | Blocked | No local MCP process was connected. See `mcp-tools.json`. |
| Read-only asset query succeeds | Blocked | No real NYCTaxi asset exists locally to query. See `sample-asset.json`. |

## Safe workaround and next action

1. Investigate why Docker Desktop / WSL or the Quickstart lifecycle recreates MySQL with 3306 despite a validated 53306 Compose override, and how to supply Quickstart runtime configuration without exposing secrets. Do not delete or modify unrelated Docker resources.
2. Re-run the official Quickstart and require MySQL, Kafka, OpenSearch, GMS, and frontend to report healthy/running before continuing.
3. Run `datahub init` against the local instance. Use `datahub datapack --help` to discover whether `nyc-taxi` is actually available; only execute a command listed by that CLI.
4. After a real asset is loaded, capture its URN from a read-only CLI/API/MCP result, then configure the official self-hosted MCP server using runtime-only environment variables. Do not commit a token or configuration file containing one.
5. Enumerate tools from the connected server and perform a read-only metadata/schema/lineage query. Replace the blocked JSON artifacts with sanitized observed results.
