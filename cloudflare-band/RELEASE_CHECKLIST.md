# v3.5.3 / Cloud Band security release checklist

**Release candidate, not deployed or published.** This Worker upgrade requires a host credential issued only to the client that creates a room. Current v3.5.2 clients cannot host on the upgraded backend. Existing rooms must be recreated after rollout. Do not claim production deployment based on Wrangler `--dry-run` or CI tests alone.

## Before merging the release candidate

- [ ] Check PR #56 final-head CI: Cloudflare security tests, Wrangler dry run, repository hygiene, Lite full Windows test/build, and Studio full Windows test/build.
- [ ] Test with actual BPSR on Windows: known game process names are recognized; pressing Play with Discord/browser focused fails closed; focus loss releases held keys; host/guest join, MIDI sharing, synchronized Start, and reconnect work. For any unrecognized regional game binary use `BPSR_GAME_EXECUTABLES` with the **exact** `.exe` basename, then test again.
- [ ] Confirm v3.5.3 Lite and Studio beta.9 hotfix10 binaries are built from the same reviewed source commit. Do not reuse v3.5.2 tags or overwrite release assets. Announce the mandatory client upgrade and room recreation.

## Coordinated production deployment

- [ ] Configure GitHub Actions repository secrets `CLOUDFLARE_API_TOKEN` (scoped permission to deploy the existing Worker) and `CLOUDFLARE_ACCOUNT_ID` for the correct Cloudflare account. Do not paste credentials into issues, commits, workflow inputs or chat.
- [ ] Merge the reviewed PR into `main` **only after CI and game checks pass**, making `.github/workflows/deploy-cloud-band.yml` available on the default branch. Merging alone does not deploy the Worker or publish an EXE.
- [ ] In GitHub Actions choose **Deploy Cloud Band production** → **Run workflow** on `main`, enter `DEPLOY-BAND-AUTH`, and approve the `production` environment if one is configured to require approval. The workflow tests, dry-runs, deploys via Wrangler and runs `node cloudflare-band/smoke-live.mjs` against production. A missing Cloudflare secret causes an explicit failure before deployment.
- [ ] If deployment succeeds and the live smoke and an actual updated-host/updated-guest test pass, trigger a new v3.5.3 GitHub release from the **same reviewed commit** via the existing release workflow (or an audited `[release v3.5.3]` commit after the code and backend are ready). The Lite workflow creates a new release; Studio only attaches its assets if its source matches the Lite release. Inspect SHA-256 verification results and published binaries.
- [ ] Verify normal users can install and host/join using the published Lite and Studio binaries, and ask existing room hosts to recreate their rooms.

## Failure or rollback

- [ ] If the Cloudflare deployment fails, do not publish incompatible clients. If the post-deploy smoke fails, stop the rollout and disable/publicly warn about Band Mode while correcting the backend. Reverting to the previously vulnerable Worker reintroduces the host-authorization flaw, so don't treat an insecure rollback as a long-term fix.

The GitHub review connector cannot set Cloudflare secrets, dispatch this workflow, observe the user's game window, or attest a live deployment. The manual production workflow exists so the repository owner can perform these authenticated steps without exposing credentials here.
