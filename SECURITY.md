# Security Policy

## Scope and trust boundaries

- **Project-local writes only:** `bootstrap.py` previews changes by default (`--apply` is required to write) and only writes inside the `--project` directory; it never modifies your home directory or global CLI configuration.
- **Best-effort specialist restrictions:** Read-only (`reviewer`) and command-only (`inspector`) tool restrictions vary by AI platform and are not a substitute for OS, container, or network sandboxing.
- **API credentials in `tools/kicad/check_availability.py`:** Credentials (`DIGIKEY_CLIENT_ID`, `DIGIKEY_CLIENT_SECRET`, `MOUSER_API_KEY`, and optional `FEEDER_URL`/`FEEDER_API_KEY`) are read from environment variables or `*.env` files in `$DISTRIBUTOR_API_DIR` (default `~/.config/distributor-api`). The script warns if `*.env` files have group/other permissions, never writes secrets into reports or error output, and requires `https://` for non-localhost `FEEDER_URL` endpoints.
- **Hardware safety:** No tool or kit sends G-code, starts prints, flashes firmware, energizes hardware, or submits fabrication/part orders.

## Reporting a vulnerability

Please do **not** open a public GitHub issue for security vulnerabilities.

Instead, report issues privately using GitHub's **Private Vulnerability Reporting** in this repository's **Security** tab ("Report a vulnerability"), and include:

- The affected file or command
- Reproduction steps or proof of concept
- Potential impact and any suggested mitigation
