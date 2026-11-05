# FINAL-1: steps for the user (NOT run by the agent)

Do these after the rename PR is squash-merged to main and no Claude Code session is open in
the old directory.

```sh
# 1. GitHub repo rename (redirects the old URL; keeps issues/PRs)
gh repo rename tome-of-the-dead --repo alstepan/wazhack

# 2. Point the local remote at the new URL (run in the old checkout, before the mv)
cd ~/sources/zxspectrum/wazhack
git remote set-url origin git@github.com:alstepan/tome-of-the-dead.git
git remote -v

# 3. Rename the local directory (leave it first: shell cwd must not be inside)
cd ~/sources/zxspectrum
mv wazhack tome-of-the-dead

# 4. Claude Code project memory is keyed by the absolute path
mv ~/.claude/projects/-Users-alexs-sources-zxspectrum-wazhack \
   ~/.claude/projects/-Users-alexs-sources-zxspectrum-tome-of-the-dead
```

Notes
- After step 3 the `.claude/settings.json` `Read(//Users/alexs/sources/zxspectrum/tome-of-the-dead/**)`
  rule already matches (changed in the PR); `~/.claude/settings*.json` entries naming the old
  path, if any, need the same edit (`grep -rn "zxspectrum/wazhack" ~/.claude --include=*.json -l`).
- Worktrees: `git worktree list` then `git worktree remove` the stale `.claude/worktrees/*`
  (absolute paths inside `.git/worktrees/*/gitdir` point at the old directory); if one is kept,
  run `git worktree repair` from the renamed checkout.
- Branch cleanup after the squash merge: `git branch -D chore/rename-tome-of-the-dead`; delete the
  remote branch with `git push origin --delete chore/rename-tome-of-the-dead`.
- Rebuild once (`tools/build.sh`) after the move: old `build/wazhack.*` files are untracked
  leftovers and can be deleted (`rm -f build/wazhack.*`).
- Re-create the Design canvas / artifact title as "Tome of the Dead Spectrum Sprites" if wanted
  (`assets/gfx/source/tome-of-the-dead_sprites.dc.html` is the local mirror).
- FINAL-2 (GitHub CI) needs the renamed repo and Actions enabled.
