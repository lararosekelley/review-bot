# Releasing

Callers use the moving major tag (`@v1`), so a release reaches them as soon as it is tagged.

1. Run the sandbox fidelity check on `main` (see "Fidelity check" in
   [eval/DESIGN.md](eval/DESIGN.md)) and read any PR it flags.
2. Draft the notes with `git cliff --unreleased --tag vX.Y.Z`, then write them up at the top of
   `CHANGELOG.md` under `## X.Y.Z - YYYY-MM-DD`, in words for the people using the action. Bump the
   major version only for a change callers must act on.
3. Commit the changelog to `main` and push it.
4. Run `npm run release -- X.Y.Z`. It checks that `main` is clean and in sync with `origin`, that the
   version is newer than the last release, and that `CHANGELOG.md` has its section, then asks before
   it tags `vX.Y.Z`, moves the major tag to the same commit, and pushes both.

Pushing `vX.Y.Z` runs the release workflow, which publishes the GitHub release with the
`CHANGELOG.md` section as its notes. To list a release on the GitHub Marketplace, edit it on GitHub
and tick "Publish this Action to the GitHub Marketplace".
