# Jeff the anteater — new fighter for the WOTU Coco mod

Jeff is drawn from the original artwork (`art/jeff_reference.jpg`): the drawing is cut into its
parts (head + ears + snout, eyes, body, bandana, tail, arms, feet) and re-posed for every frame as
64-px-scale pixel art with 1 px outlines, i.e. the same size/look as the game's fighters
(benchmark: Erbito Black Rose, `o_plr_erbitobkr`).

Animated preview: `art/showcase.py` renders a GIF of the whole kit from the built assets (it uses Erbito Black Rose sprites extracted from game.droid as the sparring dummy).

## Moves

| Input | Move |
|---|---|
| Attack A (combo 1) | **Jab → Cross → Hook → Uppercut** (uppercut launches + knocks down) |
| Attack B (combo 2) | **Jab → Cross → Hook → Uppercut** (same punches, arcane violet hits, +10% dmg) |
| Down + attack / air attack | crouching jab / air punch |
| Shield | crouches and **blocks with both hands** |
| Skill | **Formic Arcana** — rune circle, then a swarm of glowing magic ants sweeps forward (multi-hit) and bursts in a rune explosion (knockdown) |
| Down + skill | **Starlight Lance** — star orb charges on the snout, a helix star-beam fires across the screen (multi-hit) and ends in a nova (knockdown) |
| **Shield + skill together** (full energy bar) | **Bone Breaker** — Jeff dashes and grabs the nearest enemy, X-ray cutscene (arm CRACK, ribs SNAP, spine CRUNCH, skull CRACK, K.O.), the opponent's HP is set to **0** |

Stats (edit in `src/jeff.c`, `gml_Object_o_jeff_Create_0`): HP 2300, damage 46, walk 3.2, run 7.4,
skill costs 55 / 45. The special needs a full energy bar and costs all of it.

## How it is wired into the game

The game is a GameMaker **YYC** build: all game logic is native code in `libyoyo.so`; the Coco mod
added its fighters as an extra code segment + objects appended to `game.droid`. Jeff uses the same
technique, chained on top of the mod:

* `src/hooks.c`
  * `jeff_initllvm` — runs after the mod's `InitLLVM` hook and appends Jeff's 8 event functions to
    the YYC function table (code ids `0xe65..0xe6c`).
  * `jeff_get_char` — `scr_menu_get_char(1005)` returns Jeff (name, title, object 685, face card…);
    every other id falls through to the mod's hook.
  * `jeff_charsel_ext` — after the mod rebuilds `global.charord`, Jeff (id 1005) is put first in the
    character select list and marked owned (`global.char[1005] = 1`). Only outside online/LAN mode
    (`global.game_gm != 2`): in online character select Jeff is left out, and a Jeff pick left over
    from an offline match is cleared (`game_plrchar[1..2] = -1`), because the other player's game
    has no `o_jeff`.
* `src/jeff.c` — the fighter. Same structure as the game's own characters: `scr_plr_step` does
  movement/inputs, `alarm[3]`/`alarm[2]` drive the combo chain (native copies of the game's
  `scr_combos_*` / `scr_alarm2_combo`), melee hits use the game's `scr_combo_normal`, projectiles
  spawn `o_mask_hit` hitboxes, so blocking, knockback and KO work like for everyone else.
* `build/elfpatch.py` — adds two PT_LOAD segments (code @ `0x3600000`, data/bss @ `0x3700000`),
  relocates the program header table and patches 4 branches (each verified first).
* `build/droidpatch.py` — adds object `o_jeff` (#685, parent `o_parent_character`) to `game.droid`.
* `art/` — everything is generated: `anims.py` (body), `vfx.py` (skills), `cutscene.py`
  (Bone Breaker), `face.py` (portrait card using the game's card frame), `sfx.py` (bone cracks,
  swarm, beam, KO). Other sounds are the game's own.

## Build

```
pip install numpy pillow scipy            # art
# + clang/ld.lld, binutils nm, llvm-objdump, ffmpeg (libvorbis), java + uber-apk-signer.jar
python build/build.py --parts WOTU_COCO69.apk.xz.part0{1..5} --out out --signer uber-apk-signer.jar
```

Output: `out/WOTU_COCO69_Jeff.apk`, signed with the debug key built into uber-apk-signer. That is
the same certificate the Coco build is signed with
(SHA-256 `1E:08:A9:03:AE:F9:C3:A7:21:51:0B:64:EC:76:4D:01:D3:D0:94:EB:95:41:61:B6:25:44:EA:8F:18:7B:59:53`),
and the package name and version (`com.GamerMind.Warriors_of_the_Universe_CocoV3`, 2.8.1 / 2008041)
are unchanged. After signing, `build.py` compares the certificate with the input APK's and stops if
they differ. To compare any two APKs: `python build/apksig.py old.apk new.apk`.

`tests/emu_test.py` runs the injected code under Unicorn with a mocked engine (table registration,
menu + select hooks incl. the online select gating, create, both combos, both skills, the special,
destroy):

```
pip install unicorn
python tests/emu_test.py out/libyoyo.so out/gen/jeff.elf out/gen/engine.ld
```

## Notes

* Same certificate, package and version as the Coco build, so it installs **as an update** over an
  existing Coco install, with no uninstall, and the app's data is kept. Because the version code is
  unchanged, the original Coco APK can also be installed back over it the same way.
* Built and checked statically + in emulation only; it has not been run on a phone yet. Try the
  update on one phone with a test account before sending it out.
* Jeff is offline only. He doesn't appear in online/LAN character select: other players' games
  don't have him, and an instant-KO special isn't fair against real players. Online play itself
  is not changed.
