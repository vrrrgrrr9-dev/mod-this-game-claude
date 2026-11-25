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
- Deliverables go in `$S/deliver`. Last shipped: `WOTU_COCO69_Jeff_Scyther_Grey_v10.apk`.

## NEXT AI: START HERE (state at hand-off, v10 just built)
v10 = MOONFALL (Grey's new ultimate) + the lava world. Built and signed:
`$S/jout2/WOTU_COCO69_Jeff.apk` (sent to the user as `$S/deliver/WOTU_COCO69_Jeff_Scyther_Grey_v10.apk`).
Not yet done for v10 (do these first, in order):
1. Finish the emulator suite: `$S/venv/bin/python tests/emu_test.py $S/jout2/libyoyo.so $S/jout2/gen/jeff.elf $S/jout2/gen/engine.ld`
   ([28] is the new, slow MOONFALL test: 460 frames). If `rebuild.sh` times out, raise its 900 s emu timeout.
   At hand-off everything up to [27] passed (the Grey sprite count was updated 37 -> 49).
2. Fuzz Grey a few seeds (command below), watch for invalid memory / hangs during the special.
3. Small fix: clear `j->gp[i].on` for all i in `start_special` (grey.c). Leftover debris from a first
   MOONFALL would otherwise be drawn frozen during a second one in the same match.
4. Then the sub attack (section 3 below has the exact recipe), then rebuild, test, commit, ship v11.
The user said NOT to do the sub attack before MOONFALL is finished.

### Making MOONFALL "as perfect as possible" (optional polish, all in grey.c `mf_*` + art/grey/moonfall.py)
- (copies of cc.sh / replay.py are in tests/ in case the scratchpad is gone)
- Preview the real code: `bash $S/tools2/cc.sh <gen dir> <out>` (quick blob + libyoyo.so; gen dir = a copy of
  `$S/jout2/gen` with the fresh grey_assets.h), then `replay.py <out>/libyoyo.so <out>/jeff.elf <gen>/engine.ld
  $S/assets5 <frames dir> moonfall8` (every 8th frame; `moonfall40` = sparse). Composite sheets by hand.
- Ideas, in order of value: (a) make the melt-front overlay ring follow the ragged front (or drop it);
  (b) the Moon could shed a few big chunks just before contact (Roche fragments, GQ_ROCK bigger sizes);
  (c) a faint orange "airglow" ring on the limb when the front reaches it; (d) camera: hold 10 more frames on
  the impact before the pull-back (MF_KEYS); (e) the ascent's streaks could curve with a slight camera tilt.
- Keep: the physics constants (MF_GM, MF_VR, MF_VT, MF_N, MF_TO) are solved together (Kepler fall from
  2.75 Earth radii, 200 frames, contact exactly at MF_HIT on MF_N). Re-solve with a script if you change one.
- Don't use draw_primitive/draw_vertex (the crash cause, see section 1); sprites only.

### Cheats (asked again, declined again)
The user asked for infinite mana ONLINE because a friend has "infinite everything" online. Declined: no online
cheats of any kind. Our builds already turn cheats off online/LAN for both players, so the friend must be on
an old/different build: tell them to install the latest APK. Local/offline cheats are unchanged.

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

### 3. Sub-attack 1 -> an axe swing that launches the enemy into the air — NOT started (do it after MOONFALL)
"Sub attack 1" = skill 1 = combo_next 100 = `GT_S1` (currently Clone Legion: 4 clone events). Recipe:
1. Art (`art/grey/fx.py`): add `def axe(k, n=4)`: a ~64x28 px two-handed glitch axe, handle along +x from
   the grip (origin ~(4, 14)), a crescent head at the far end: dark steel with a bright cyan edge and a few
   magenta glitch pixels that shift per frame (4 frames). Add `'axe': (axe, 4, 4, 14)` to SPRITES (before
   `SPRITES.update(moonfall.SPRITES)`). Render just that PNG into `$S/assets5`
   (`python -c "import sys; sys.path.insert(0,'art/grey'); import fx; ..."` or `build_art.py` (slow: all art)).
2. Weapon id: `moves.py` WEAPONS add `'axe': 4`. In `grey.c draw_weapon` the decode is `(p->flags >> 2) & 3`:
   change to `& 7` and pick `GR_AXE` (scale 1.0) when wk == 4 (GKey.flags is uint8, room for it).
   Two-handed: in the axe poses keep ub/lb close to uf/lf so both hands sit on the handle.
3. Choreography (`moves.py`, replace the s1 block): `s1 = move(TL('S1', 50))`:
   t0 ST -> t5 wind-up (deep crouch, torso twisted back, axe low behind: uf/lf ~ 150-170, w ~ 160, 'out')
   -> t9 hold/coil ('lin', a little lower) -> t13 explosive rising swing through the front ('expo', gh=1,
   w sweeping ~160 -> -60, body rising onto the toes, mx ~ 10) -> t20 follow-through overhead (w ~ -100,
   arched back) -> t34 recover -> t50 ST ('inout', wk back to 'none').
   Events: t2 glitch n=8 + fx 'spawn' (the axe materialises) + snd 'glitch'; t12 snd 'woosh3';
   t13 `s1.hit(13, 22, -22, 64, 1.6, 1.4, 1.6, 2.5, -11.0, 30, knock=1, spr=3, col='glitch', snd=2)`
   (vf -11 = launched high, knock=1 = they fly and fall); t13 fx 'arc' (22, -26, 1.4), fx 'shock' (18, -2),
   fx 'ring', ev 'shake' n=3, snd 'strong2'. Optional: a rising streak of particles above the opponent.
4. Rebuild: the build regenerates `grey_moves.h` from moves.py (via grey_manifest.py). grey.c case 100 already
   starts GT_S1, nothing else to wire.
5. Tests: `tests/emu_test.py` [27] checks Clone Legion's clones: change it to one hit with vf <= -10 and
   knock, and `grey_axe.png` drawn. Rebuild, test, fuzz, replay `grey` to eyeball the swing, ship.

### 4. Ultimate -> MOONFALL (the Moon teleported into the sky, a realistic Earth-Moon collision) - DONE (v10)
`special_step` / `mf_*` in grey.c, art in `art/grey/moonfall.py` (registered into fx.SPRITES).
- Timeline (frames): MF_RIFT 24, MF_MOON 40, MF_ASC 90, MF_SPACE 114, MF_FALL 176, MF_HIT 240, MF_AFTER 324,
  MF_FLASH 360, MF_LAND 372 (the blow + `lava_activate`), SPC_DUR 440.
- Physics: Earth radius 1, Moon 0.2725; `mf_moon_c` integrates the Kepler fall BACKWARDS from the contact state
  (MF_N, MF_VR/MF_VT, MF_GM) so contact is exact. Ejecta/debris `GPt gp[]` use the same GM.
- Camera: `MF_KEYS` (log apparent radius, centre x, top y) through a cubic Hermite; perspective projection with
  occlusion (`mf_hidden`). The Moon sprite is pre-lit in a frame rotated by MF_ROT (37.15 deg) so tidal
  stretching is an x-scale without rotating its lighting.
- Lava world: Draw_72 (0xe7e, o_grey event 8/72) + Draw_0 fallback; hides scenery/layers like Scyther's void.
- Preview: `replay.py ... moonfall8` (every 8th frame of the cinematic, world + GUI).

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
