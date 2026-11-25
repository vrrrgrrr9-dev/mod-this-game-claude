# Handoff — WOTU Coco mod (Jeff / Black Holing Scyther / Grey)

Branch: `claude/character-hooks-mechanics-3xqa5v`. Commit/push only here; no PR unless asked.
Attribution lines go at the end of every commit (see any recent commit for the two lines).

## How to build + test (no Android emulator in this env — static + Unicorn only)
Scratch root: `S=/tmp/claude-0/-home-user-mod-this-game-claude/51a3ce15-244d-5021-bb4f-fc7dfc2fb7b8/scratchpad`
- Full build + emulator tests: `bash $S/tools2/rebuild.sh $S/assets5`
  - builds `$S/jout2/WOTU_COCO69_Jeff.apk` (signed, same debug key), runs `tests/emu_test.py`.
  - the build applies the shader fix + the user's save-recovery dex fix automatically.
- Fuzz (randomized fights under Unicorn, catches hangs / invalid memory):
  `$S/venv/bin/python $S/tools2/fuzz.py $S/jout2/libyoyo.so $S/jout2/gen/jeff.elf $S/jout2/gen/engine.ld 1600 <seed> cpu grey`
- Replay renderer (rasterizes real draw calls to PNGs): `$S/tools2/replay.py ... <scenario>`
  scenarios: `grey`, `grey2`, `grey3`, `combos`, `moves`, `void`.
- Run python art/move scripts WITHOUT `-I` (they import sibling modules): `$S/venv/bin/python art/grey/moves.py <out.h>`.
- Deliverables go in `$S/deliver`. Last shipped: `WOTU_COCO69_Jeff_Scyther_Grey_v8.apk`.

## STATUS of the 4 requests in the user's last message

### 1. CRASH FIX — DONE in source, NOT yet built/tested/shipped  ← do this first
Commit `63369bb`. Root cause (strong evidence): the base game makes **0** `draw_primitive`/
`draw_vertex` calls (grep'd the whole binary). Our mod was the only user of that GPU path, and only
the two characters that used it (Grey, Scyther) crash to the launcher mid-move — a native/driver
crash, not a GML error. Replaced all triangle-strip drawing with stretched sprite quads (`seg()` in
grey.c and scyther.c, using GR_SHAPE / the new `scyther_smear` sprite). Both compile; zero primitive
relocations remain.
TODO: `bash $S/tools2/rebuild.sh $S/assets5`, confirm emu tests pass, fuzz a few seeds, eyeball a
`grey`/`combos` replay so the new trails/rings/lightning still look good, then ship as v9.
SECOND safety net (optional, not done): texture memory is large (Scyther ~44MB raw; six 3840x180
cutscene strips at 2.76MB each — see `art/cutscene.py` and `art/scyther/cutscene.py`, 320x180 x12).
Shrinking those would relieve OOM pressure for combined modded-vs-modded fights.

### 2. Fix Grey's position while fighting — NOT started
User says Grey sits at the wrong spot in a fight. Likely the draw origin / feet alignment or the
hitmask offset vs. where he's rendered. Look at `grey.c` `fk()` (forward kinematics, feet at y) and
`spawn_hit` offsets, and `src/hooks.c` put_char for Grey (the `2200,47,14,90,99` stats / mask args).
Compare to how Jeff/Scyther sit. Grey's sprite_index markers are 1px invisible strips; the game
positions him by those — check `spr_mask_stand`/`spr_mask_crouch` (SPR_MASK_STAND/CROUCH) match his
drawn height, else he floats or sinks.

### 3. Sub-attack 1 → an axe swing that launches the enemy up — NOT started
"Sub attack 1" = skill 1 = **Clone Legion** currently (combo_next 100, `GT_S1` in `art/grey/moves.py`,
`grey_start` case 100). Replace/retheme S1 as a big overhead AXE swing that hits with high upward
`vf` (negative = up) and `knock=1` so the enemy flies up. There's already an axe-ish pose set
(`AXE_UP`/`AXE_DOWN` in moves.py used by B4 "Meteor Axe") and a `giant` weapon (wk='giant') — reuse
the giant blade as an axe, or add an axe sprite. Pattern: edit the `s1` TL in moves.py, re-export
(`$S/venv/bin/python art/grey/moves.py $S/jout2/gen/grey_moves.h`), rebuild. Keep a hit with large
negative vf (e.g. vf=-10) + knock=1 at the impact frame.

### 4. Ultimate → teleport the whole MOON into the sky with realistic collision — NOT started
Current Grey special = SYSTEM CRASH (`special_step` in grey.c, SPC_* timings). User wants a cinematic
where Grey teleports the moon up and drops it (meteor-impact collision). This is the big one. Plan:
- new art: a big moon sprite (circle, craters) + impact shockwave/debris (reuse GR_RING, GR_SHATTER,
  smoke particles already in grey.c).
- rewrite `special_step`: charge → teleport flash → moon rises into sky (draw moon via `spr` at a
  screen-space y that climbs) → pause → moon falls with accelerating velocity → impact: huge
  unblockable hit (see the SLAM hit in special_step for the template), camera_shake, rings, crater,
  screen flash, dust. Use real-ish physics: y += vy; vy += g each frame for the fall.
- draw the moon on the GUI layer (Draw_64) so it's above everything, like the current crash screen.
Scyther's ultimate (SINGULARITY, black hole) is a good reference for a cinematic special with a
cutscene — see `scyther.c` special + `art/scyther/cutscene.py`.

### 5. Cheats online via a secret code — DECLINED, do not build
The user asked for a hidden code that turns the Coco cheats (infinite HP, one-tap KO, immunity...)
on in online matches. That is cheating against real players; it was declined. Cheats stay
local-only (`jeff_frame` in `src/hooks.c` forces the cheat word to 0 when `global.game_gm == 2`).

## Key files
- `src/grey.c` — Grey fighter (poses from skeleton, timelines, effects). `src/scyther.c`, `src/jeff.c`.
- `src/hooks.c` — registration, char-select gating, cheats gating.
- `art/grey/moves.py` — Grey choreography (edit → re-export grey_moves.h). `poses.py`, `skel.py`, `fx.py`.
- `build/elfpatch.py` — patches libyoyo.so (hooks + cheat patches, each verified byte-for-byte first).
- `build/droidpatch.py` — adds the o_jeff/o_scyther/o_grey objects + shader fix.
- `build/dexpatch.py` — the user's save-recovery fix (classes5.dex).
- `tests/emu_test.py` — Unicorn harness; the fuzz + replay tools reuse its setup half.

## Constraints (still in effect)
- Jeff/Scyther/Grey are OFFLINE-ONLY in character select (online play unchanged). Keep it that way.
- Cheats: local-only. Do not add an online unlock.
- Same signing key / package / version (installs as an update; checked by the build).
- No model identifiers in commits/code. Don't commit secrets. User email is private.
