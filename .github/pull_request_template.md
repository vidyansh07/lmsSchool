## What changed

<!-- One paragraph. Link the issue. -->

## Production-readiness checklist

Every box must be genuinely true before review. "Works on my machine" is not
acceptance.

- [ ] Code works and has been run, not only compiled
- [ ] Tests exist for the new behaviour and the whole suite passes
- [ ] API changes are documented (OpenAPI schema regenerated where relevant)
- [ ] Permissions are enforced **server-side**, not only hidden in the UI
- [ ] Input validation exists at the API boundary
- [ ] Errors are handled and return the shared error envelope without internals
- [ ] Security implications considered (authn/authz, injection, rate limits, uploads)
- [ ] Logs and audit entries contain no passwords, tokens or other secrets
- [ ] Configuration is environment-specific; no secret is committed
- [ ] Staging can reproduce the change with fake data
- [ ] Documentation updated (README / docs/)

## Database migrations

- [ ] No migrations, or: migrations are backwards compatible and reviewed
- [ ] Rollback plan described below

## How this was verified

<!-- Commands run, environments used, manual checks performed. -->
