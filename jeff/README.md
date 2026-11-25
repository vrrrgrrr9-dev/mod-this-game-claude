# Jeff + Black Holing Scyther — new fighters for the WOTU Coco mod

Jeff is drawn from the original artwork (`art/jeff_reference.jpg`): the drawing is cut into its
parts (head + ears + snout, eyes, body, bandana, tail, arms, feet) and re-posed for every frame as
64-px-scale pixel art with 1 px outlines, i.e. the same size/look as the game's fighters
(benchmark: Erbito Black Rose, `o_plr_erbitobkr`).

## Moves

| Input | Move |
|---|---|
| Attack A | **Dark flame punches**: jab -> cross -> hook -> flame flurry (5 quick hits) -> uppercut (launches, knocks down) |
| Attack B | **Blue flame kicks**: front kick -> roundhouse -> spinning back kick -> axe kick (heel slams down, knockdown) |
| Down + attack A / B | crouching jab / flame sweep (trips) |
| Air attack A / B | air punch / diving flame kick |
| Shield | crouches and **blocks with both hands** |
| Skill | **Meteor Shower**: three black holes tear open in the sky and rain meteors wrapped in dark blue flame onto the ground in front of him |
| Down + skill | **Abyss Palm**: his palm opens a black hole that drags the opponent in, then his punch detonates it |
| **Shield + skill together** (full energy bar) | **Bone Breaker**: Jeff dashes and grabs the nearest enemy, X-ray cutscene (arm CRACK, ribs SNAP, spine CRUNCH, skull CRACK, K.O.), the opponent's HP is set to **0** |
| **Double-tap shield** | **Switch power**: blue (dark flame) <-> red (the sun). Blue fire spins up round him and turns to sun fire, and he turns black from the feet up: the red-power form (see below). Double-tap again to go back. |
| **Double-tap skill** (full bar) | **RED BLACK HOLE** cinematic: a black hole ringed in sun fire opens over the opponent, pulls them up, stretches them thin and swallows them, then bursts. **K.O.** (HP set to 0) |
| **Double-tap shield + double-tap skill together** (full bar) | **HOLLOW PURPLE** cinematic: blue in one hand, red in the other, he merges them into a purple orb, flicks it, a purple nuclear blast, then he strikes a pose. **K.O.** |

In the **red power** he fights with a **sun sword** (front hand) and a **sun shield** (back hand):

| Input (red power) | Move |
|---|---|
| Attack A | **Sun sword**: slash -> rising slash -> thrust -> spin slash -> solar cleave (knockdown) |
| Attack B | **Sun shield**: shield bash -> shield uppercut (launches) -> shield charge -> sun slam (knockdown, shock ring) |
| Down / air attacks | the same blows as blue, burning with sun fire |
| Shield | raises the sun shield |
| Skill | **Solar Flare**: a crescent of sun fire flies across the screen (5 hits) |
| Down + skill | **Corona**: the sun on his shield flares and blasts both sides, with shock rings |

With a full bar, one skill tap waits about a quarter of a second (16 frames) to see if a second
tap follows. One tap then gives the normal skill (down is remembered, so down + skill still gives
skill 2), or the Bone Breaker if shield was held. A double tap gives a cinematic. Both cinematics
make Jeff untouchable while they play. The K.O. lands as the fight fades back in, the same way as
the Bone Breaker.

**The red-power form** is the user's "dark Jeff" drawing: the same body gone black, glowing white
eyes with a flat top, ringed in yellow, and a white chest tag with two black buttons. Every body
animation has a black copy (`jeff_d_*.png`, rendered by `rig.py` in its `dark` style). The game's
logic always sees the normal sprite. Only the draw swaps in the black copy, so every state
(hurt, knocked down, jumping...) has the right form without touching the framework. The eyes also
get a soft additive glow, and the HUD portrait switches to a black-form card (`jeff_face_d.png`).
The transformation draws the new form row by row from his feet up, with a band of fire at the edge.

The flame is blue fire with darkness flowing inside it, in pixel art (`art/flame.py`: a 5-colour
palette from black-indigo to white-cyan, ordered dithering, hard edges, a dark rim). The game draws
it on whichever fist or foot is burning in the current frame; `art/anims.py` records those points
per frame. The black holes and meteors use the same pixel style. Jeff himself keeps the original
look from the drawing.

Stats (edit in `src/jeff.c`, `gml_Object_o_jeff_Create_0`): HP 2300, damage 46, walk 3.2, run 7.4,
skill costs 55 / 45 (same in both powers). The three finishers (Bone Breaker, Red Black Hole, Hollow
Purple) each need a full energy bar and cost all of it.

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
* `art/` — everything is generated: `anims.py` (body in both forms, including the kicking legs
  from `rig.py`, and the sun sword's angle per frame), `flame.py` (the dark flame, meteors and
  black holes, in blue / sun / purple palettes), `sun.py` (sun sword and shield, Solar Flare,
  transformation swirl, and the art of both cinematics: red black hole, blue/red/purple orbs,
  nuclear blast, shock ring, skies), `vfx.py` + `cutscene.py` (Bone Breaker), `face.py` (portrait
  card using the game's card frame), `sfx.py` (bone cracks, KO, flame, meteor, black hole, power
  switch, nuclear blast). Other sounds are the game's own.

## Build

```
pip install numpy pillow scipy            # art
# + clang/ld.lld, binutils nm, llvm-objdump, ffmpeg (libvorbis), java + uber-apk-signer.jar
python build/build.py --parts WOTU_COCO69.apk.xz.part0{1..5} --out out --signer uber-apk-signer.jar
# --assets out/assets reuses already rendered art (the art takes a few minutes)
```

Output: `out/WOTU_COCO69_Jeff.apk`, signed with the debug key built into uber-apk-signer. That is
the same certificate the Coco build is signed with
(SHA-256 `1E:08:A9:03:AE:F9:C3:A7:21:51:0B:64:EC:76:4D:01:D3:D0:94:EB:95:41:61:B6:25:44:EA:8F:18:7B:59:53`),
and the package name and version (`com.GamerMind.Warriors_of_the_Universe_CocoV3`, 2.8.1 / 2008041)
are unchanged. After signing, `build.py` compares the certificate with the input APK's and stops if
they differ. To compare any two APKs: `python build/apksig.py old.apk new.apk`.

`tests/emu_test.py` runs the injected code under Unicorn with a mocked engine (table registration,
menu + select hooks incl. the online select gating, create, both combos, both skills, the special,
the power switch both ways, the red combos and skills, both cinematics and their K.O., the tap
timing, the CPU's finishers, destroy):

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
* Jeff is offline only, and so is Scyther. Neither appears in online/LAN character select: other
  players' games don't have them, and the instant-KO finishers aren't fair against real players.
  Online play itself is not changed. The Coco build also carries the cheat menu, so this mod does
  not open online play to modded clients.

## Black Holing Scyther (char id 1006, object 686)

A cosmic-violet fighting rooster with a double-bladed obsidian scythe. Art is generated by
`art/scyther/` (rig, weapon, rifts, 3D arcs, VFX, cutscene, void stage, face, sfx) at 2x pixel
density and drawn at half scale; code is `src/scyther.c`.

| Input | Move |
|---|---|
| Attack A | Rift Cleave -> Twin Crescent -> **Comet Thrust** -> Orbit Reap -> Event Horizon Cleave |
| Attack B | Crescent Throw -> Spur Vault -> **Phase Step** (blinks through the opponent 3x) -> Dimensional Stitch -> Singular Rend (portal, cuts from behind) |
| Run + attack | **Meteor Dash** - dashes straight through the opponent, leaves a tear behind, then the rest of the combo |
| Down + attack A / B | Ground Reaper (trip) / **Rising Moon** (launcher) |
| Air attack A / B | Falling Star, attack again -> **Sky Splitter** (diving cleave, crater) / **Gravity Drop** (plunge, crater) |
| Skill | Event Horizon - a black hole that drags the opponent in, then collapses |
| Down + skill | Void Lance - an aperture tear fires a beam, ends in a nova |
| Shield + skill (full bar) | SINGULARITY - cutscene, one huge unblockable hit (no instant K.O.), then the stage becomes a void of floating rocks |

Pacing: moves are 16-46 frames at 60 fps, each one moves him (lunges, hops, dashes, blinks, dives)
and homes in on the opponent so the cut connects; he stops at contact instead of walking through
(except Meteor Dash, which is meant to pass through).

3D, drawn by the game every frame from the scythe's real pose: blade trails (triangle strips from
mid-blade to tip across the last 10 poses, split in front of / behind the body), shockwave rings in
a perspective ground plane (far half behind him, near half in front), debris thrown with depth
(scaled and sorted by z), portals that turn edge-on -> facing -> edge-on, motion smears along his
velocity. Pre-rendered 3D: the swing arcs and the scythe sprite (angle, tilted orbit, spinning disc).

The void stage: the stages paint their scenery with background/tile layers and with placed
instances (`o_map_bk` paints the whole backdrop from a 900000-deep instance layer; `o_tile_*` are
trees, houses, grass). Everything behind the fighters is hidden: layers with `layer_set_visible`,
scenery instances (listed from game.droid at build time by `build/gen_stage.py`) with
`visible = false`, so they keep their collisions. Draw Begin then paints space, floating rocks and a
perspective stone slab on every solid platform (the top face narrows toward the camera centre, so it
parallaxes as the camera pans). If a device never runs Draw Begin, the normal Draw event paints it.

In the cutscene's last act the rooster is drawn live from his 2x sprites, so he stays sharp on any
screen size. Offline only, same as Jeff.

## Crash in the Scyther mirror match

Reported from play: Scyther vs Scyther, the game froze and closed as Event Horizon Cleave slammed
down. Under the emulator, our code never looped or touched bad memory in that scene: a fuzz test
with two Scythers and Jeff using random moves ran more than 12,000 frames without a fault. So the
fix hardens what the code asks the engine to do:

* sounds: our OGGs are streamed (`audio_create_stream`; the engine exports no way to load them into
  memory), and every playing copy decodes on its own thread. A mirror match fires them twice as
  often. Now a stream never plays twice at once, and at most 3 to 4 of ours play together;
* triangle strips: they are only sent when they have at least 4 finite vertices, and each draw has
  a vertex budget;
* angle and sine helpers are bounded, so no loop can spin on a huge or NaN value;
* Create always starts from a clean state, because instances destroyed by a room change never run
  Destroy and their slot could be matched again;
* an unused 4 MB scythe texture is gone.

This is not confirmed on a phone yet.

## CPU opponents

Reported from play: when Jeff was the CPU, his attacks didn't hurt the player. The game's AI
(`scr_ai_medium`) presses attack from up to ~50 px away (plus a lead for the target's speed) and
never holds shield and skill together. The likely cause is that the CPU's short punches fell short,
and it could never use a shield + skill special. This is not confirmed on a phone. Both characters
now:

* step in a little at the start of each melee move, only toward an opponent close in front (Jeff:
  within 90 px, at most 40 px over 6 frames; Scyther: within its reach + 60 px, at most 45 px).
  They turn round only when the opponent is right behind. (An earlier version lunged from up to
  ~170 px away, which looked like a random dash at the start of an attack; reported from play and
  toned down.)
* use their special when the CPU (`plr_controller == 2`) presses skill with a full bar and an
  opponent in reach. CPU Jeff picks one of his three finishers at random. The CPU may also
  double-tap shield and switch his power, then not again for 600 frames.

The emulator test covers both, for Scyther and for Jeff. It has not been checked on a phone yet.
