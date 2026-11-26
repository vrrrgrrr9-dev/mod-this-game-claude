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

## NEXT AI: START HERE (v12 BUILT AND SHIPPED: `$S/deliver/WOTU_COCO69_Jeff_Scyther_Grey_v12.apk`)
v12 was built in the session with the toolchain (out dir `$S/jout3`, assets `$S/assets6` = assets5 + Grey art
re-rendered by `art/grey/build_art.py`). Same signing certificate, save-recovery fix applied, no warnings.
Unicorn emu_test.py at wrap-up: 266 checks ok, 0 FAIL through [30b] (all MOONFALL / axe / arrow tests passed;
the run was cut short at [30b] by the user's wrap-up). Fuzz grey seed 11 clean, seed 12 clean at frame 1000.
Previews from the real code looked right (axe swing; INFERNO ARROW every phase). Next: finish the last emu
sections ([30b]..end) once, then the open items below (Grey's position while fighting, polish ideas).
(previous note:) v12 = v11 + the bow; source done and tested on the host
v12 adds Grey's **bow stance + INFERNO ARROW** (from a concept video the user sent: an archer draws a giant
fire bow, releases, the arrow streaks across, a yellow flash, a top-down crater, a white flash with a black
spike, a mushroom cloud). The user chose: Grey gets it; a double-tap shield toggles a bow stance; in the
stance shield + skill fires INFERNO ARROW instead of MOONFALL. Original art (not the video's character).
- Code: grey.c `bow_input` (double tap, TAP_WINDOW 16, cooldown 24, only free + grounded), the bow shown in
  the hand when src < 100 and no move weapon (GW_BOW = 5, w -90, mirrored like the axe), `start_special`
  sets `sp_kind` (SPK_ARROW if `bow`), the CPU picks randomly. Section "INFERNO ARROW": `ia_step` (pose from
  the frame alone via `ia_pose`, sounds, the blow at IA_LAND 318: dmg x9, defend 0, knock, vforce -11),
  `ia_draw_world` (fire gathering at the hand; the cloud behind the target afterwards), `ia_draw_gui` ->
  close-up (Grey drawn ~10x by `ia_big` from the real skeleton), flight, flash, top, spike, cloud.
  Timeline: IA_CUT 26, IA_LOOSE 122, IA_FLY 134, IA_FLASH 178, IA_TOP 186, IA_SPIKE 238, IA_CLOUD 248,
  IA_LAND 318, IA_DUR 380. Peak 403 draws, 16 blend switches per frame.
- Art: art/grey/arrow.py (10 sprites, registered into fx.SPRITES after moonfall: GR_ indices shifted, all by
  name). Poses BOW_AIM / BOW_DRAW / BOW_LOOSE in poses.py.
- Tests: emu_test.py [22] 60 sprites, new [28c] (single press no bow, double tap bow, the cinematic: one
  unblockable hit at 316..320, every phase's art drawn, not MOONFALL, 380 frames, toggle back -> MOONFALL).
  Host: all Grey tests pass, fuzz 6 x 6000 frames clean (fuzz now double-taps shield too).
- Ideas if the user wants more: a bow-stance moveset (arrow shots on attack), a hit-confirm close-up of the
  target, a proper cel-shaded rock sprite for the cloud shot (the moon rocks read dark up close).

### v11 (still not built either)
v11 = everything the user asked for after v10, in source:
- MOONFALL fixes: the leftover-debris bug (`start_special` clears `gp[]`), blend switches 26 -> 18 per frame
  (all additive glows of a layer share one block: see the comments in `mf_draw_space`), and it is now
  **500 frames at 60 fps** (MF_HOLD 254, MF_AFTER 354, MF_FLASH 400, MF_LAND 412 = the blow, SPC_DUR 500;
  MF_MOON..MF_HIT untouched, so the Kepler constants are still exact; slow-mo ejecta for MF_SLOWMO 54).
- MOONFALL polish, all 5 handoff ideas: (a) the shock ring follows the textures' ragged melt front
  (`moonfall.front_table()` -> `k_mf_front` in grey_assets.h, `mf_front_lag`); (b) Roche fragments: big
  chunks shed from the Earth-facing side in the last 26 frames, they strike first; (c) orange airglow on the
  melted limb (`mf_draw_airglow`, soft glows, no seg joints); (d) a 14-frame camera hold on the impact
  (MF_KEYS); (e) the ascent streaks lean and bend with a slight camera roll.
- Sub attack 1 = **Glitch Axe** (section 3 recipe): `fx.axe` (64x28, grip (4,14), edge up), weapon id 4
  (`GW_AXE`, decode `>> 2 & 7` in draw_weapon AND trails_push; mirrored with yscale -1 when facing left so
  the edge leads), choreography in moves.py `s1` with `grip2()` (2-hand IK; the target is just out of reach
  so both hands meet at the grip), an extra low-pass key at t11 so the swing goes down-under-up (the short-
  way-round lerp would otherwise swing it backwards over the top), floor-scrape sparks t10-11, hit t13 vf -11
  knock, rising sparks over the opponent, glitch-out t44. Clone Legion's CL_* scripts are kept, unused.
- Tests: emu_test.py [22] 50 sprites, [27] axe (1 hit, vforce <= -10, can_knock, grey_axe drawn),
  [28] windows for 500 frames + hit at 410..416, new [28b] second MOONFALL (no frozen debris) + 500 frames.

### Why no APK yet, and how to build v11
The session that made v11 had no Unicorn, no uber-apk-signer.jar, no original Coco APK and no network.
So it verified with a **host harness** instead (`tests/host/`, see its files' docstrings):
- `compile_check.sh <jeff> <out>` (env V10 = unzipped v10 APK dir, ASSETS = rendered art): the real ARM
  build of the blob, minus elfpatch. Compiles clean, no draw_primitive.
- `build_host.sh` + `grey_test.py`: grey.c compiled for x86-64 with a ctypes shim that forwards every engine
  call to Python stubs ported 1:1 from emu_test.py, then runs emu_test.py's Grey section ([23]..[31]) on it.
  On v10 code it reproduced the v10 emulator result exactly (blend 26, blow at 372, 674 draws), so trust it.
  UBSan in trap mode. `fuzz_grey.py` (6 x 6000 frames clean), `host_replay.py` (moonfall / axe / axeL).
**TODO for v11:** in an env with the parts + signer: `python build/build.py --parts ... --out <dir>
--signer uber-apk-signer.jar`, then the FULL emu_test.py under Unicorn (ARM, all characters), then ship as
`WOTU_COCO69_Jeff_Scyther_Grey_v11.apk`. Expect [28] max draws ~720, blend 18.
Still open (unchanged): section 2 (Grey's position), the optional texture-memory safety net.
Possible next polish: the shock ring's seg joints show as beads (same in v10) - soft glows like the airglow
would fix it; the axe's low pass dips under the floor for ~1 frame (like Glitch Sweep Blade's sword).

### Cheats (asked again, declined again)
The user asked for infinite mana ONLINE because a friend has "infinite everything" online. Declined: no online
cheats of any kind. Asked a third time with v10 ("Restore cheats online"): declined again, offline cheats unchanged. Our builds already turn cheats off online/LAN for both players, so the friend must be on
an old/different build: tell them to install the latest APK. Local/offline cheats are unchanged.

## Custom characters with the bow (v13/v14)
Characters made in the game's Character Creation holding the bow (img_wp == 62) fire INFERNO ARROW with
shield + skill on a full bar (cust_step / cust_draw / cust_draw_gui in grey.c; droidpatch repoints
o_plr_custom's Step/Draw, adds Draw GUI). OFFLINE ONLY (v14): online the game's own move runs.
Why: online is rollback netcode (nonline_save_state / nonline_set_state / nonline_rollback in o_control_online);
each phone simulates from inputs (scr_send_char_data also sends x, y, xscale, hspeed, vspeed) and checksums
(plr_hp, p2_checksum_tick) are compared -> a phone without the mod plays the normal special, mismatches, and
the match drops ("connection lost") for both. To enable online it needs, untested here (needs two phones):
(1) a both-have-the-mod handshake in the match-start data that unmodded phones ignore, and (2) the arrow's
timeline keyed to the netcode's shared tick (o_control_online.tick) instead of our own counter, so rollback /
re-simulation replays it identically on both phones.

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

### 3. Sub-attack 1 -> an axe swing that launches the enemy into the air — DONE in source (v11), see START HERE
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

### 4. Ultimate -> MOONFALL (the Moon teleported into the sky, a realistic Earth-Moon collision) - DONE (v10, retimed to 500 frames in v11)
`special_step` / `mf_*` in grey.c, art in `art/grey/moonfall.py` (registered into fx.SPRITES).
- Timeline (frames, v11): MF_RIFT 24, MF_MOON 40, MF_ASC 90, MF_SPACE 114, MF_FALL 176, MF_HIT 240, MF_HOLD 254,
  MF_AFTER 354, MF_FLASH 400, MF_LAND 412 (the blow + `lava_activate`), SPC_DUR 500.
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
