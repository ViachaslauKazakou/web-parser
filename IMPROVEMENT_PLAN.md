# Improvement plan

## Goal

Harden forum parsing against oversized or script-generated pages, then verify the Docker deployment end to end. Preserve the current product scope: direct access without authentication, and local-only binding unless access controls are deliberately added later.

## Work items

1. **Make JavaScript an explicit opt-in for parsing**
   - Add `PARSER_ENABLE_JAVASCRIPT` to application settings with a safe default of `false`.
   - Document the option in `.env.example` and the README; do not inspect or modify the local `.env` file.
   - When disabled, block page scripts and stylesheets; when enabled, preserve support for trusted client-rendered forums.
   - Add tests for both default-off and explicit opt-in behavior.

2. **Enforce parser resource limits before content is materialized**
   - Review browser navigation, response, DOM, and extraction limits so a large DOM is bounded before `page.content()` returns it.
   - Keep the existing host allowlist, pinned public DNS, egress proxy, page/deadline limits, and WebRTC protections.
   - Add regression coverage for oversized responses/pages and verify the parser fails with a controlled error rather than exhausting memory.

3. **Verify the complete deployment**
   - Run the full test suite.
   - Build and start the Docker Compose services, check health endpoints, and smoke-test parsing/export against the local PostgreSQL service.
   - Keep PostgreSQL data in the existing ignored `data/postgres/` directory; do not prune unrelated Docker resources.
   - Confirm the app remains bound to localhost and no authentication has been introduced.

## Acceptance criteria

- JavaScript is disabled by default and can be enabled explicitly for trusted forums.
- Parser limits and failure behavior are covered by regression tests.
- Tests pass and Docker Compose build/health/smoke checks succeed.
- The local `.env` is neither read nor modified.
- The current no-auth, localhost-only product behavior is unchanged.
