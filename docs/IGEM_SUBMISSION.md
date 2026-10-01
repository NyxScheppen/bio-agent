# iGEM Software Submission Guide

Last reviewed: 2026-10-01

## Official 2026 requirements captured here

The 2026 iGEM deliverables pages require Software & AI Village teams, and teams applying for Best Software Tool, to place open-source and reproducible software in the team's dedicated iGEM GitLab repository. The repository must include source code, a README with build instructions, and CI/CD configuration. The published repository freeze date is **2026-10-21**. Teams may submit up to five repositories.

Official references:

- <https://competition.igem.org/deliverables>
- <https://competition.igem.org/deliverables/guides#h-software>
- <https://teams.igem.org/go/deliverables>
- <https://teams.igem.org/go/deliverables/software/requirements> (team login may be required)

The official portal remains authoritative. Re-check it while logged into the team account before the freeze because form fields and judging instructions can change.

## Verified team identity

- Team display name: **LZU GANSU**
- Official slug: `lzu-gansu`
- Team wiki: <https://2026.igem.wiki/lzu-gansu>
- iGEM GitLab wiki project: <https://gitlab.igem.org/2026/lzu-gansu>
- Software submission portal: <https://teams.igem.org/go/deliverables/software>

The public `2026/lzu-gansu` project is the team wiki repository. Do not overwrite it with this software repository unless the authenticated submission portal explicitly instructs the team to do so. The dedicated 2026 Software Tools namespace is login-gated as of the review date.

## Repository readiness

This repository now provides:

- MIT `LICENSE` and third-party notices;
- English and Chinese READMEs with build, run, test, security, and scope information;
- backend source, frontend source, and production frontend assets;
- pinned Python requirements, npm lockfile, and R lockfile;
- `.gitlab-ci.yml` for backend, frontend, and submission-integrity checks;
- behavioral documents and an evidence-based feature verification report;
- `scripts/verify_submission.py` to reject common secret and runtime-data leaks.
- verified team identity and official wiki links for iGEM 2026 Team LZU GANSU.
- a privacy-safe interface screenshot generated from an isolated empty database.

## Team actions before upload

1. Log in at the Software submission portal and claim or locate the dedicated software repository assigned to LZU GANSU.
2. Add the final member contribution statement, supervisors, advisors, and official team contact details to the wiki/Attributions Form; mirror an appropriate public summary in both READMEs.
3. Add the dedicated software repository URL, screenshots or a short demonstration, and preferred citation/DOI when available.
4. Review dependencies, datasets, icons, screenshots, and example inputs for redistribution permission and attribution.
5. Run the commands in `CONTRIBUTING.md` from a clean clone. Confirm that `backend/.env`, storage, databases, local caches, and `runtime/run_backend.bat` are absent.
6. Push to the dedicated iGEM GitLab repository and confirm all GitLab CI jobs pass there.
7. Connect the exact repository in the logged-in submission form before **2026-10-21**. Confirm visibility and access using a logged-out browser where allowed.

## Suggested Git transfer

Keep the existing GitHub remote as a backup and add the iGEM remote separately:

```bash
git remote add igem <TEAM_IGEM_GITLAB_URL>
git fetch igem
git push igem main
```

Do not paste access tokens into the remote URL, documentation, terminal screenshots, or CI files. Use the Git credential manager or an SSH key registered to the team account.

## Claims that still require team input

- Individual member, supervisor, and advisor credits
- Human contribution statement and final Attributions Form
- Demonstration media and final wiki links
- Citation/archival DOI
- Dedicated software repository URL supplied by the authenticated portal
- Any judging-form declarations visible only after team login

These cannot be inferred safely from the code and must be completed by the team.
