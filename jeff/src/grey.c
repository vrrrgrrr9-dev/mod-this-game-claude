/*
 * Grey - a dark grey stickman for the WOTU "Coco" mod: glitch, clones and every element.
 *
 * He is not drawn from sprite frames.  Every frame the game draws his lines from a skeleton
 * (art/grey/skel.py); each attack is an eased keyframe timeline with timed events
 * (art/grey/moves.py -> gen/grey_moves.h), so all his motion is smooth at 60 fps, and moving
 * between any two poses (attacks, walking, landing...) cross-fades.
 *
 *  attack A: Glitch Jab-Cross -> Clone Cut (a clone slashes from behind him) -> Frost Rise (ice
 *            spikes, rising uppercut) -> Fireball Flip (backflip, two fireballs) -> Fatal Glitch
 *            (teleports behind, three clones and he spear him at once, shatter, knockdown)
 *  attack B: Roundhouse -> Twin Clone Kick (low sweep, a clone flies over with a kick) -> Ice
 *            Lance Shatter (lance, spinning heel shatters it into shards) -> Meteor Axe (flip,
 *            burning heel, knockdown)
 *  down + A / B: Glitch Sweep Blade / Frost Slide      air A / B: Aerial Glitch Spin / Phantom Dive
 *  run + attack: Glitch Dash (through him, echoes slash behind)
 *  skill 1: Clone Legion (four clones: ice, fire, spear from the sky, lightning)
 *  skill 2: Element Overload (ice prison, fire pillar, glitch spear rain)
 *  special (shield + skill, full bar): MOONFALL - Grey tears the sky open and glitches the Moon into
 *            it; the camera climbs out of the atmosphere and pulls back to watch the Moon, cracking inside
 *            the Roche limit, fall onto the Earth (real size ratio, Kepler fall, oblique impact, vapour
 *            plume, a crust wave melting the globe, ejecta on ballistic arcs, a debris disc). White-out,
 *            back down: the battlefield is a lava world for the rest of the match, and the blow lands.
 *
 * Same framework as the other fighters: scr_plr_step drives movement / input, combos run through
 * alarm[3] / alarm[2], hits are o_mask_hit hitboxes.  The framework's sprite_index values are tiny
 * invisible marker strips, one per state, so the game's logic sees normal sprites.
 */
#include "yyc.h"
#include "grey_assets.h"
#include "grey_moves.h"
#include "stage_decor.h"

#define GREY_CHAR_ID  1007
#define OBJ_GREY      687
#define OBJ_MASK_HIT  224
#define OBJ_PARENT_CHARACTER 420
#define OBJ_PARENT_SOLID 425
#define OBJ_CAMERA    9

#define SPR_MASK_STAND 1684
#define SPR_MASK_CROUCH 1682
#define SPR_MASK16 656
#define SPR_MASK24 658
#define SPR_MASK32 659
#define SPR_MASK64 660
#define SPR_HIT_1 312
#define SPR_HIT_3 314
#define SPR_HIT_5 317
#define SND_JUMP 190
#define SND_WOOSH3 467
#define SND_SUSPENSE 13
#define SND_WINLOSE_IMPACT 464
#define SND_STRONG2 163
#define SND_EXPLOSION_MEGA 100
#define SND_BALL_CHARGE 266
#define SND_THUNDER 177
#define SND_DARKEXPLOSION 82
#define SND_MAGIC3 203

#define C_WHITE  0xFFFFFF
#define RGB(r, g, b) ((int)((r) | ((g) << 8) | ((b) << 16)))   /* GameMaker colours are BGR */
#define C_FILL   RGB(70, 70, 78)
#define C_BACK   RGB(52, 52, 60)
#define C_LINE   RGB(10, 10, 14)
#define C_CYAN   RGB(60, 230, 255)
#define C_MAG    RGB(255, 60, 210)
#define C_ICE    RGB(150, 225, 255)
#define C_FIRE   RGB(255, 140, 40)
#define C_VOLT   RGB(160, 150, 255)
#define C_CLONE  RGB(90, 200, 240)
#define C_CLONEB RGB(60, 140, 190)
#define C_CLONEL RGB(10, 40, 70)

#define PI_F 3.14159265f
#define DEG (PI_F / 180.0f)
#define N_CLONE 8
#define N_PROJ 16
#define N_SPIKE 14
#define N_FX 28
#define N_GHOST 8
#define MOVE_NONE (-1)
#define BLEND_N 6
/* MOONFALL (the special): the timeline, in frames */
#define MF_RIFT   24           /* a rift tears open in the sky */
#define MF_MOON   40           /* the Moon glitches into the sky */
#define MF_ASC    90           /* the camera rises out of the atmosphere */
#define MF_SPACE  114          /* space: pull back from Earth's horizon to the whole system */
#define MF_FALL   176          /* inside the Roche limit: the Moon breaks up and falls */
#define MF_HIT    240          /* contact (MF_MOON..MF_HIT is the solved Kepler fall: keep it 200 frames) */
#define MF_HOLD   254          /* the camera holds on the impact (slow motion) before it pulls back */
#define MF_AFTER  354          /* the aftermath: a magma ocean, a debris ring forming */
#define MF_FLASH  400          /* white out, back down to the ground */
#define MF_LAND   412          /* the battlefield is a lava world; the blow lands */
#define SPC_DUR   500          /* 500 frames = 8.3 s at 60 fps */
#define MF_SLOWMO 54           /* frames after contact the ejecta fly in slow motion */
/* INFERNO ARROW: the bow ultimate (shield + skill in the bow stance; double-tap shield toggles the stance) */
#define SPK_MOON  0
#define SPK_ARROW 1
#define TAP_WINDOW 16           /* double-tap shield: the second press within this many frames */
#define IA_CUT    26            /* fire gathers at his bow hand, then: cut to the close-up */
#define IA_LOOSE  122           /* the giant bow of fire drawn to the cheek ... released */
#define IA_FLY    134           /* the arrow in flight, low over the plain */
#define IA_FLASH  178           /* it strikes: a yellow flash, ink focus lines */
#define IA_TOP    186           /* from straight above: the crater rips open, rocks fly at the camera */
#define IA_SPIKE  238           /* white-out: a black spike of earth and flame */
#define IA_CLOUD  248           /* the mushroom cloud over the plain */
#define IA_LAND   318           /* back on the ground: the blow lands */
#define IA_DUR    380
#define ENTRY_T 40             /* frames he takes to materialise when the match starts */
#define DEAD_FADE 90           /* frames a KO takes to dissolve him (down to a faint ghost) */

typedef struct { float hx, hy, rot, mx; float a[GA_N]; int flags; } GPose;
typedef struct { float x, y; } V2;
typedef struct { int on, tl, t, ev, tint, fade; float x, y, f; } Clone;
typedef struct { int on, kind, t; float x, y, vx, vy, dmg, f, floor_y; } Proj;
typedef struct { int on, t, hit; float x, y, size, vf, dmg, f; } Spike;
typedef struct { int on, t, a, tpf, n, add, col; float x, y, xs, ys, rot; } Fx;
typedef struct { int on, t, col; GPose p; float x, y, f; } Ghost;
#define N_GP 260               /* MOONFALL space particles (Earth radii, Earth at the origin) */
enum { GQ_EJECTA, GQ_ROCK, GQ_DUST, GQ_SPLASH };
typedef struct { unsigned char on, kind; short t, life; float x, y, z, vx, vy, vz, rot, vr, size; int frame; } GPt;
#define N_PART 200
#define N_TRS 9                /* ribbon trail samples */
#define N_TRP 5                /* tracked points: front hand, back hand, front foot, back foot, blade tip */
#define N_BOLT 10
#define N_MARK 10
enum { PK_SPARK, PK_EMBER, PK_FROST, PK_PIXEL, PK_SMOKE, PK_STREAK, PK_BIT, PK_SHARD, PK_FLASH };
typedef struct { int on, kind, t, life, col, frame; float x, y, vx, vy, g, drag, size, dsize, rot, vr, a0; } Part;
typedef struct { float x[N_TRP], y[N_TRP]; int on[N_TRP]; } TrailS;
typedef struct { int on, t, life, seed, col; float x0, y0, x1, y1, w; } Bolt;
typedef struct { int on, t, life, kind; float x, y, w; } Mark;

typedef struct {
    CInstance *inst;
    int move, t, ev, has_mx;
    float dir, mx_prev;
    GPose drawn, from;
    int blend_t, src, air_t, idle_t;
    float phase;
    int glitch_t, aura_t, fail_t, home_t; float home_v;
    Clone cl[N_CLONE]; Proj pr[N_PROJ]; Spike sp[N_SPIKE]; Fx fx[N_FX]; Ghost gh[N_GHOST];
    int gh_head;
    /* the overhaul: particles, ribbon trails, lightning, ground marks, hit-stop, screen tears */
    Part pt[N_PART]; int pt_head;
    TrailS tr[N_TRS]; int tr_head, tr_n;
    Bolt bo[N_BOLT]; Mark mk[N_MARK];
    int hitstop, scr_t, was_air;
    int entry_t, prev_loco, dead_t;             /* materialising at the start, getting hit, KO'd */
    int pz_tl, pz_t, pz_ev, win_wait;           /* a pose override that is not an attack: victory, idle flourish */
    GPt gp[N_GP]; int gp_head;                  /* MOONFALL: ejecta, moon debris, the Roche stream */
    int lava_on, lava_t, lava_hidden, lava_drawn; float lava_gy;   /* the destroyed world after MOONFALL */
    /* MOONFALL */
    int sp_on, sp_t, tgt_id, depth_saved, hit_done; float tgt_x, tgt_y; double old_depth;
    int sp_kind;                                /* SPK_MOON / SPK_ARROW */
    int cust;                                   /* a creator-made character with the bow, not Grey */
    int bow, prev_def, def_t1, bow_cool;        /* the bow stance (double-tap shield) */
} Grey;

static Grey g_grey[4];
static Grey g_cust[2];                          /* INFERNO ARROW for the game's custom characters (see below) */
static void impact(Grey *j, float x, float y, int col, float power);
static Part *part(Grey *j, int kind, float x, float y, float vx, float vy, int life, float size, int col);
static void burst(Grey *j, int kind, float x, float y, int n, float spd, int life, float size, int col);
static void bolt(Grey *j, float x0, float y0, float x1, float y1, int life, float w, int col);
static void mark(Grey *j, int kind, float x, float y, float w, int life);
static int glitch_col(void);
int g_grey_spr[GR_COUNT];
int g_grey_snd[GS_COUNT];
int g_grey_loaded;
static unsigned g_grey_tick;

/* ------------------------------------------------------------------------------------------ */
/* runtime helpers (same as the other fighters)                                                */
/* ------------------------------------------------------------------------------------------ */
static double get_rv(const RValue *inst, YYVAR *v, int idx) {
    RValue r = rv_undef();
    YYGML_Variable_GetValue(inst, v->id, idx, &r, false, false);
    double d = rv_num(&r);
    rv_free(&r);
    return d;
}
static double sget(CInstance *s, YYVAR *v) { RValue i = rv_inst(s); return get_rv(&i, v, ARRAY_INDEX_NONE); }
static double sget_i(CInstance *s, YYVAR *v, int idx) { RValue i = rv_inst(s); return get_rv(&i, v, idx); }
static void bset(CInstance *s, YYVAR *v, double d) { RValue r = rv_real(d); Variable_SetValue_Direct(s, v->id, ARRAY_INDEX_NONE, &r); }
static void bset_i(CInstance *s, YYVAR *v, int idx, double d) { RValue r = rv_real(d); Variable_SetValue_Direct(s, v->id, idx, &r); }
static void iset(CInstance *s, YYVAR *v, double d) { RValue *slot = var_slot_w(s, v->id); rv_free(slot); *slot = rv_real(d); }
static void iset_b(CInstance *s, YYVAR *v, bool b) { RValue *slot = var_slot_w(s, v->id); rv_free(slot); *slot = rv_bool(b); }
static void iset_str(CInstance *s, YYVAR *v, const char *str) { RValue *slot = var_slot_w(s, v->id); rv_free(slot); YYCreateString(slot, str); }
static double iget(CInstance *s, YYVAR *v) { RValue *slot = var_slot_r(s, v->id); return slot ? rv_num(slot) : 0.0; }
static const RValue *parent_of(CInstance *s) { return var_slot_r(s, g_VAR_parent.id); }
static double pget(CInstance *s, YYVAR *v) { const RValue *p = parent_of(s); return p ? get_rv(p, v, ARRAY_INDEX_NONE) : 0; }
static void pset(CInstance *s, YYVAR *v, double d) { const RValue *p = parent_of(s); if (!p) return; RValue r = rv_real(d); YYGML_Variable_SetValue(p, v->id, ARRAY_INDEX_NONE, &r); }
static void pset_b(CInstance *s, YYVAR *v, bool b) { const RValue *p = parent_of(s); if (!p) return; RValue r = rv_bool(b); YYGML_Variable_SetValue(p, v->id, ARRAY_INDEX_NONE, &r); }

static bool inst_exists_rv(CInstance *s, const RValue *id) {
    RValue r = rv_undef();
    RValue a = *id;
    if (NEEDS_FREE(a.kind)) return false;
    F_InstanceExists(&r, s, s, 1, &a);
    bool b = rv_num(&r) > 0.5;
    rv_free(&r);
    return b;
}
static bool parent_ok(CInstance *s) {
    const RValue *p = parent_of(s);
    if (!p) return false;
    uint32_t k = p->kind & KIND_MASK;
    if (k == VALUE_UNDEFINED) return false;
    if ((k == VALUE_REAL) && p->val <= 0.0) return false;
    return inst_exists_rv(s, p);
}

static unsigned g_rng = 0x51afe7u;
static unsigned rnd(void) { g_rng ^= g_rng << 13; g_rng ^= g_rng >> 17; g_rng ^= g_rng << 5; return g_rng; }
static float frand(float a, float b) { return a + (b - a) * (float)(rnd() & 0xffff) / 65535.0f; }
static float fabsf_(float v) { return v < 0 ? -v : v; }
static bool finite_(float v) { return v == v && v < 1e7f && v > -1e7f; }
static float clampf(float v, float a, float b) { return v < a ? a : (v > b ? b : v); }
static float wrap180(float a) {
    if (!finite_(a)) return 0;
    a -= 360.0f * (float)(int)(a / 360.0f);
    if (a > 180) a -= 360;
    if (a < -180) a += 360;
    return a;
}
static float sinf_(float x) {                       /* small, bounded sine (radians) */
    if (!finite_(x)) return 0;
    x -= 6.2831853f * (float)(int)(x / 6.2831853f);
    if (x > PI_F) x -= 6.2831853f;
    if (x < -PI_F) x += 6.2831853f;
    float x2 = x * x;
    return x * (1 - x2 / 6 * (1 - x2 / 20 * (1 - x2 / 42 * (1 - x2 / 72))));
}
static float cosf_(float x) { return sinf_(x + PI_F / 2); }
static float sqrtf_(float x) { return x > 0 ? __builtin_sqrtf(x) : 0; }
static float atan2f_(float y, float x) {
    if (!finite_(x) || !finite_(y)) return 0;
    float ax = fabsf_(x), ay = fabsf_(y);
    if (ax < 1e-9f && ay < 1e-9f) return 0;
    float a = ax > ay ? ay / ax : ax / ay;
    float s = a * a;
    float r = ((-0.0464964749f * s + 0.15931422f) * s - 0.327622764f) * s * a + a;
    if (ay > ax) r = 1.57079637f - r;
    if (x < 0) r = PI_F - r;
    return y < 0 ? -r : r;
}

/* sounds: the game's own are in memory; ours (4) are streams - one copy each at a time, at most 2
   alive, at most one new per frame, and the pitch only on a voice that really started */
static double play_v(CInstance *s, int snd, double pitch) {
    if (snd < 0) return -1;
    RValue r = rv_undef();
    RValue a[3] = { rv_real(snd), rv_real(10), rv_real(0) };
    F_AudioPlaySound(&r, s, s, 3, a);
    double v = (r.kind & KIND_MASK) == VALUE_UNDEFINED ? -1 : rv_num(&r);
    if (pitch != 1.0 && v >= 0) {
        RValue r2 = rv_undef();
        RValue b[2] = { r, rv_real(pitch) };
        F_AudioSoundPitch(&r2, s, s, 2, b);
        rv_free(&r2);
    }
    rv_free(&r);
    return v;
}
static bool voice_playing(CInstance *s, double v) {
    if (v <= 0) return false;
    RValue r = rv_undef(); RValue a = rv_real(v);
    F_AudioIsPlaying(&r, s, s, 1, &a);
    bool b = rv_num(&r) > 0.5;
    rv_free(&r);
    return b;
}
static double g_grey_voice[GS_COUNT];
static unsigned g_grey_last_start = 0xffffffffu;
static void play_c(CInstance *s, int which, double pitch) {
    if (which < 0 || which >= GS_COUNT || g_grey_snd[which] < 0) return;
    if (g_grey_last_start == g_grey_tick) return;
    if (voice_playing(s, g_grey_voice[which])) return;
    int alive = 0;
    for (int k = 0; k < GS_COUNT; k++) if (voice_playing(s, g_grey_voice[k])) alive++;
    if (alive >= 2) return;
    double v = play_v(s, g_grey_snd[which], pitch);
    g_grey_voice[which] = v > 0 ? v : 0;
    g_grey_last_start = g_grey_tick;
}
static void play(CInstance *s, int snd, double pitch) { play_v(s, snd, pitch); }

static int g_blend_cur = -1;              /* the blend mode we last set in this draw event (-1: unknown) */
static void blend(CInstance *s, int mode) {
    if (mode == g_blend_cur) return;      /* nothing between our calls changes it: no flush for nothing */
    g_blend_cur = mode;
    RValue r = rv_undef(); RValue a = rv_real(mode);
    F_GPUSetBlendMode(&r, s, s, 1, &a);
    rv_free(&r);
}
static void spr(CInstance *s, int a, float img, float x, float y, float xs, float ys, float rot, int col, float alpha) {
    if (a < 0 || a >= GR_COUNT) return;
    int id = g_grey_spr[a];
    if (id < 0 || !finite_(x) || !finite_(y) || !finite_(xs) || !finite_(ys) || !finite_(rot)) return;
    YYGML_draw_sprite_ext(s, id, img, x, y, xs, ys, rot, col, alpha);
}
static void camera_shake(double amount) {
    if (amount > 3) amount = 3;
    RValue cam = rv_real(OBJ_CAMERA);
    RValue v = rv_real(amount);
    YYGML_Variable_SetValue(&cam, g_VAR_camera_shake.id, ARRAY_INDEX_NONE, &v);
}
static float sx_(CInstance *s) { return (float)sget(s, &g_VAR_x); }
static float sy_(CInstance *s) { return (float)sget(s, &g_VAR_y); }
static float facing(CInstance *s) { return sget(s, &g_VAR_image_xscale) < 0 ? -1.0f : 1.0f; }
static double my_dmg(CInstance *s) { return parent_ok(s) ? pget(s, &g_VAR_plr_dmg) : 47; }
static double legacy0(CInstance *s, YYVAR *f) {
    RValue r = rv_undef();
    YYGML_CallLegacyFunction(s, s, &r, 0, f->id, 0);
    double d = rv_num(&r);
    rv_free(&r);
    return d;
}
static int inst_count(CInstance *s, int obj) {
    RValue n = rv_undef(); RValue a = rv_real(obj);
    F_InstanceNumber(&n, s, s, 1, &a);
    int c = (int)rv_num(&n); rv_free(&n);
    return c < 0 ? 0 : (c > 32 ? 32 : c);
}
static CInstance *inst_nth(CInstance *s, int obj, int i, int *out_id) {
    RValue id = rv_undef(); RValue fa[2] = { rv_real(obj), rv_real(i) };
    F_InstanceFind(&id, s, s, 2, fa);
    int iid = INT32_RValue(&id);
    rv_free(&id);
    *out_id = iid;
    return YYGML_FindInstance(iid);
}
/* the nearest living opponent within maxdx / maxdy of the point (mx, my) */
static CInstance *nearest_enemy_at(CInstance *s, double mx, double my, int *out_id, float maxdx, float maxdy) {
    *out_id = -1;
    if (!parent_ok(s)) return 0;
    RValue me = rv_undef();
    YYGML_Variable_GetValue(parent_of(s), g_VAR_plr_team.id, ARRAY_INDEX_NONE, &me, false, false);
    double my_team = rv_num(&me); rv_free(&me);
    int cnt = inst_count(s, OBJ_PARENT_CHARACTER);
    CInstance *best = 0; double bestd = 1e9; int best_id = -1;
    for (int i = 0; i < cnt; i++) {
        int iid = -1;
        CInstance *c = inst_nth(s, OBJ_PARENT_CHARACTER, i, &iid);
        if (!c || c == s) continue;
        RValue cp = rv_undef(); RValue id = rv_real(iid);
        YYGML_Variable_GetValue(&id, g_VAR_parent.id, ARRAY_INDEX_NONE, &cp, false, false);
        if (!inst_exists_rv(s, &cp)) { rv_free(&cp); continue; }
        double team = get_rv(&cp, &g_VAR_plr_team, ARRAY_INDEX_NONE);
        double dead = get_rv(&cp, &g_VAR_is_dead, ARRAY_INDEX_NONE);
        rv_free(&cp);
        if (team == my_team || dead > 0.5) continue;
        double dx = sget(c, &g_VAR_x) - mx, dy = sget(c, &g_VAR_y) - my;
        double adx = dx < 0 ? -dx : dx, ady = dy < 0 ? -dy : dy;
        double d = adx + ady * 1.5;
        if (d < bestd && adx < maxdx && ady < maxdy) { bestd = d; best = c; best_id = iid; }
    }
    *out_id = best_id;
    return best;
}
static CInstance *nearest_enemy(CInstance *s, int *out_id, float maxdx, float maxdy) {
    return nearest_enemy_at(s, sget(s, &g_VAR_x), sget(s, &g_VAR_y), out_id, maxdx, maxdy);
}
/* does an opponent's body (about 24 x 62 above his feet) overlap a hitbox centred on x, y? */
static bool enemy_in_box(CInstance *s, float x, float y, float hw, float hh) {
    int id = -1;
    return nearest_enemy_at(s, x, y + 31, &id, hw + 12, hh + 31) != 0;
}
/* is every opponent down (K.O.)? (false with no opponent at all, or if he is down himself) */
static bool enemies_beaten(CInstance *s) {
    if (!parent_ok(s) || pget(s, &g_VAR_is_dead) > 0.5) return false;
    RValue me = rv_undef();
    YYGML_Variable_GetValue(parent_of(s), g_VAR_plr_team.id, ARRAY_INDEX_NONE, &me, false, false);
    double my_team = rv_num(&me); rv_free(&me);
    int cnt = inst_count(s, OBJ_PARENT_CHARACTER), foes = 0, down = 0;
    for (int i = 0; i < cnt; i++) {
        int iid = -1;
        CInstance *c = inst_nth(s, OBJ_PARENT_CHARACTER, i, &iid);
        if (!c || c == s) continue;
        RValue cp = rv_undef(); RValue id = rv_real(iid);
        YYGML_Variable_GetValue(&id, g_VAR_parent.id, ARRAY_INDEX_NONE, &cp, false, false);
        if (!inst_exists_rv(s, &cp)) { rv_free(&cp); continue; }
        double team = get_rv(&cp, &g_VAR_plr_team, ARRAY_INDEX_NONE);
        double dead = get_rv(&cp, &g_VAR_is_dead, ARRAY_INDEX_NONE);
        rv_free(&cp);
        if (team == my_team) continue;
        foes++;
        if (dead > 0.5) down++;
    }
    return foes > 0 && down == foes;
}
static bool free_at(CInstance *s, float x, float y) {
    RValue r = rv_undef();
    RValue a[3] = { rv_real(x), rv_real(y), rv_real(OBJ_PARENT_SOLID) };
    F_PlaceMeeting(&r, s, s, 3, a);
    bool hit = rv_num(&r) > 0.5;
    rv_free(&r);
    float rw = (float)sget(s, &g_VAR_room_width);
    if (rw > 100 && (x < 16 || x > rw - 16)) return false;
    return !hit;
}

typedef struct { double dmg, hforce, vforce, stun, dur, xs, ys; int mask, hits, knock, defend, fallen, hit_spr, color, snd; } Hit;
static void spawn_hit(CInstance *s, double x, double y, const Hit *h) {
    if (!parent_ok(s) || !finite_((float)x) || !finite_((float)y)) return;
    RValue id = rv_undef();
    RValue a[4] = { rv_real(x), rv_real(y), rv_real(sget(s, &g_VAR_depth) - 1), rv_real(OBJ_MASK_HIT) };
    F_InstanceCreateDepth(&id, s, s, 4, a);
    if ((id.kind & KIND_MASK) == VALUE_UNDEFINED) return;
    CInstance *hb = YYGML_FindInstance(INT32_RValue(&id));
    if (hb) {
        bset(hb, &g_VAR_sprite_index, h->mask);
        bset(hb, &g_VAR_mask_index, h->mask);
        bset(hb, &g_VAR_image_xscale, h->xs);
        bset(hb, &g_VAR_image_yscale, h->ys);
    }
    RValue par = *parent_of(s);
    YYGML_Variable_SetValue(&id, g_VAR_obj_parent.id, ARRAY_INDEX_NONE, &par);
    RValue t;
    t = rv_bool(false); YYGML_Variable_SetValue(&id, g_VAR_can_follow.id, ARRAY_INDEX_NONE, &t);
    t = rv_real(h->dmg); YYGML_Variable_SetValue(&id, g_VAR_stats_dmg.id, ARRAY_INDEX_NONE, &t);
    t = rv_real(h->hits); YYGML_Variable_SetValue(&id, g_VAR_stats_hits.id, ARRAY_INDEX_NONE, &t);
    t = rv_real(h->dur); YYGML_Variable_SetValue(&id, g_VAR_stats_duration.id, ARRAY_INDEX_NONE, &t);
    t = rv_real(h->hforce); YYGML_Variable_SetValue(&id, g_VAR_hforce.id, ARRAY_INDEX_NONE, &t);
    t = rv_real(h->vforce); YYGML_Variable_SetValue(&id, g_VAR_vforce.id, ARRAY_INDEX_NONE, &t);
    if (h->knock) { t = rv_bool(true); YYGML_Variable_SetValue(&id, g_VAR_can_knock.id, ARRAY_INDEX_NONE, &t); }
    else { t = rv_real(h->stun); YYGML_Variable_SetValue(&id, g_VAR_stuntime.id, ARRAY_INDEX_NONE, &t); }
    t = rv_bool(h->defend); YYGML_Variable_SetValue(&id, g_VAR_can_defend.id, ARRAY_INDEX_NONE, &t);
    t = rv_bool(h->fallen); YYGML_Variable_SetValue(&id, g_VAR_can_hit_fallen.id, ARRAY_INDEX_NONE, &t);
    t = rv_real(h->hit_spr); YYGML_Variable_SetValue(&id, g_VAR_hit_spr.id, ARRAY_INDEX_NONE, &t);
    t = rv_real(h->color); YYGML_Variable_SetValue(&id, g_VAR_hit_color.id, ARRAY_INDEX_NONE, &t);
    t = rv_real(h->snd); YYGML_Variable_SetValue(&id, g_VAR_hit_snd.id, ARRAY_INDEX_NONE, &t);
    t = rv_bool(false); YYGML_Variable_SetValue(&id, g_VAR_hit_snd_miss.id, ARRAY_INDEX_NONE, &t);
    rv_free(&id);
}

/* ------------------------------------------------------------------------------------------ */
/* assets and per-instance state                                                               */
/* ------------------------------------------------------------------------------------------ */
static int g_tl_has_mx[GT_COUNT];
void grey_load_assets(CInstance *s) {
    if (g_grey_loaded) return;
    g_grey_loaded = 1;
    for (int i = 0; i < GR_COUNT; i++) {
        RValue r = rv_undef();
        RValue a[6];
        YYCreateString(&a[0], k_grey_sprites[i].file);
        a[1] = rv_real(k_grey_sprites[i].frames);
        a[2] = rv_bool(false);
        a[3] = rv_bool(false);
        a[4] = rv_real(k_grey_sprites[i].ox);
        a[5] = rv_real(k_grey_sprites[i].oy);
        F_SpriteAdd(&r, s, s, 6, a);
        g_grey_spr[i] = (r.kind & KIND_MASK) == VALUE_UNDEFINED ? -1 : (int)rv_num(&r);
        rv_free(&r);
        rv_free(&a[0]);
    }
    for (int i = 0; i < GS_COUNT; i++) {
        RValue r = rv_undef();
        RValue a;
        YYCreateString(&a, k_grey_sounds[i]);
        F_AudioCreateStream(&r, s, s, 1, &a);
        g_grey_snd[i] = (r.kind & KIND_MASK) == VALUE_UNDEFINED ? -1 : (int)rv_num(&r);
        rv_free(&r);
        rv_free(&a);
    }
    for (int t = 0; t < GT_COUNT; t++) {                  /* root motion only where a move travels */
        const GTimeline *T = &k_gtl[t];
        for (int k = 0; k < T->nkey; k++) if (k_gkeys[T->key0 + k].mx != 0) g_tl_has_mx[t] = 1;
    }
    if (g_grey_spr[GR_PREVIEW] >= 0) {                    /* character select preview */
        RValue r = rv_undef();
        RValue a[2] = { rv_real(OBJ_GREY), rv_real(g_grey_spr[GR_PREVIEW]) };
        F_ObjectSetSprite(&r, s, s, 2, a);
        rv_free(&r);
    }
}
int grey_face_sprite(void) { return g_grey_spr[GR_FACE]; }

static void key_pose(const GKey *k, GPose *p) {
    p->hx = k->hx / 4.0f; p->hy = k->hy / 4.0f; p->rot = (float)k->rot; p->mx = k->mx / 4.0f;
    for (int i = 0; i < GA_N; i++) p->a[i] = (float)k->a[i];
    p->flags = k->flags;
}
static void base_pose(int which, GPose *p) { key_pose(&k_gposes[which], p); }

static void grey_reset(Grey *j, CInstance *s) {
    char *p = (char *)j; for (unsigned k = 0; k < sizeof(Grey); k++) p[k] = 0;
    j->inst = s; j->dir = 1; j->move = MOVE_NONE; j->tgt_id = -1; j->src = -1; j->pz_tl = -1;
    base_pose(GPZ_STAND, &j->drawn); j->from = j->drawn;
}
static Grey *slot(CInstance *s, bool create) {
    for (int i = 0; i < 4; i++) if (g_grey[i].inst == s) return &g_grey[i];
    for (int i = 0; i < 2; i++) if (g_cust[i].inst == s) return &g_cust[i];
    if (!create) return 0;
    for (int i = 0; i < 4; i++) if (!g_grey[i].inst) { grey_reset(&g_grey[i], s); return &g_grey[i]; }
    grey_reset(&g_grey[3], s);
    return &g_grey[3];
}

/* ------------------------------------------------------------------------------------------ */
/* poses: easing, interpolation, timelines                                                     */
/* ------------------------------------------------------------------------------------------ */
static float ease(int kind, float u) {
    u = clampf(u, 0, 1);
    switch (kind) {
    case 0: return u;
    case 1: return u * u;
    case 2: return 1 - (1 - u) * (1 - u);
    case 3: return u * u * (3 - 2 * u);
    case 4: { float c = 1.70158f, v = u - 1; return 1 + (c + 1) * v * v * v + c * v * v; }
    case 5: return u >= 1 ? 1.0f : 0.0f;
    case 6: { float v = 1 - u; return 1 - v * v * v * v * v; }        /* fast start, soft stop */
    }
    return u;
}
static void lerp_pose(const GPose *a, const GPose *b, float u, GPose *o) {
    o->hx = a->hx + (b->hx - a->hx) * u;
    o->hy = a->hy + (b->hy - a->hy) * u;
    o->rot = a->rot + (b->rot - a->rot) * u;
    o->mx = a->mx + (b->mx - a->mx) * u;
    for (int i = 0; i < GA_N; i++) o->a[i] = a->a[i] + wrap180(b->a[i] - a->a[i]) * u;
    o->flags = u < 0.5f ? a->flags : b->flags;
}
static void tl_sample(int tl, float t, GPose *o) {
    if (tl < 0 || tl >= GT_COUNT) { base_pose(GPZ_STAND, o); return; }
    const GTimeline *T = &k_gtl[tl];
    const GKey *k = &k_gkeys[T->key0];
    int n = T->nkey;
    if (n <= 0) { base_pose(GPZ_STAND, o); return; }
    if (t <= k[0].t) { key_pose(&k[0], o); return; }
    for (int i = 0; i + 1 < n; i++) {
        if (t <= k[i + 1].t) {
            GPose a, b;
            key_pose(&k[i], &a); key_pose(&k[i + 1], &b);
            int span = k[i + 1].t - k[i].t;
            float u = ease(k[i + 1].ease, (t - k[i].t) / (float)(span > 0 ? span : 1));
            lerp_pose(&a, &b, u, o);
            o->flags = k[i].flags;                       /* flags (weapon, trails) hold until the next key */
            return;
        }
    }
    key_pose(&k[n - 1], o);
}

/* joints: 0 hip, 1 neck, 2 shoulder, 3 head, 4 back elbow, 5 back hand, 6 front elbow, 7 front hand,
   8 back knee, 9 back foot, 10 front knee, 11 front foot */
static V2 dir_of(float a, float rot, float f) { float r = (a + rot) * DEG; V2 v = { cosf_(r) * f, sinf_(r) }; return v; }
static V2 add(V2 o, V2 d, float l) { V2 r = { o.x + d.x * l, o.y + d.y * l }; return r; }
static void fk(const GPose *p, float x, float y, float f, V2 *J) {
    V2 hip = { x + p->hx * f, y + p->hy };
    J[0] = hip;
    J[1] = add(hip, dir_of(p->a[GA_SP], p->rot, f), G_L_SPINE);
    J[2] = add(hip, dir_of(p->a[GA_SP], p->rot, f), G_L_SPINE - G_SHOULDER_DROP);
    J[3] = add(J[1], dir_of(p->a[GA_HD], p->rot, f), G_L_NECK);
    J[4] = add(J[2], dir_of(p->a[GA_UB], p->rot, f), G_L_UARM);
    J[5] = add(J[4], dir_of(p->a[GA_LB], p->rot, f), G_L_FARM);
    J[6] = add(J[2], dir_of(p->a[GA_UF], p->rot, f), G_L_UARM);
    J[7] = add(J[6], dir_of(p->a[GA_LF], p->rot, f), G_L_FARM);
    J[8] = add(hip, dir_of(p->a[GA_TB], p->rot, f), G_L_THIGH);
    J[9] = add(J[8], dir_of(p->a[GA_SB], p->rot, f), G_L_SHIN);
    J[10] = add(hip, dir_of(p->a[GA_TF], p->rot, f), G_L_THIGH);
    J[11] = add(J[10], dir_of(p->a[GA_SF], p->rot, f), G_L_SHIN);
}

/* ------------------------------------------------------------------------------------------ */
/* drawing the stickman: white square / disc sprites, tinted and stretched                     */
/* ------------------------------------------------------------------------------------------ */
static void bone(CInstance *s, V2 a, V2 b, float w, int col, float al, int caps) {
    float dx = b.x - a.x, dy = b.y - a.y, len = sqrtf_(dx * dx + dy * dy);
    if (len > 0.3f)
        spr(s, GR_SHAPE, 0, (a.x + b.x) * 0.5f, (a.y + b.y) * 0.5f, len / 32.0f, w / 32.0f,
            -atan2f_(dy, dx) * 57.29578f, col, al);
    if (caps) {
        spr(s, GR_SHAPE, 1, a.x, a.y, w / 32.0f, w / 32.0f, 0, col, al);
        spr(s, GR_SHAPE, 1, b.x, b.y, w / 32.0f, w / 32.0f, 0, col, al);
    }
}
static const int BACK_ARM[2][2] = { { 2, 4 }, { 4, 5 } }, BACK_LEG[2][2] = { { 0, 8 }, { 8, 9 } };
static const int FRONT_LEG[2][2] = { { 0, 10 }, { 10, 11 } }, FRONT_ARM[2][2] = { { 2, 6 }, { 6, 7 } };
static void layer(CInstance *s, const V2 *J, const int (*b)[2], int nb, float extra, int col, float al) {
    for (int i = 0; i < nb; i++) bone(s, J[b[i][0]], J[b[i][1]], G_W_LIMB + extra, col, al, 1);
}
/* the weapon in his front hand: sword, spear or the giant blade */
static void draw_weapon(CInstance *s, const GPose *p, const V2 *J, float f, float al, int col) {
    int wk = (p->flags >> 2) & 7;                 /* GW_*: 3 bits */
    if (!wk) return;
    V2 d = dir_of(p->a[GA_W], p->rot, f);
    float ang = -atan2f_(d.y, d.x) * 57.29578f;
    int a = wk == GW_BOW ? GR_BOW : wk == GW_AXE ? GR_AXE : wk == GW_SPEAR ? GR_SPEAR : GR_SWORD;
    if ((wk == GW_AXE || wk == GW_BOW) && f < 0) {   /* mirrored: the axe's edge leads, the bow's string faces him */
        spr(s, a, (float)((g_grey_tick / 3) % 4), J[7].x, J[7].y, 1, -1, ang, col, al);
        return;
    }
    float k = wk == 3 ? 3.2f : 1.0f;
    spr(s, a, (float)((g_grey_tick / 3) % 4), J[7].x, J[7].y, k, k, ang, col, al);
}
static float g_extra_w;            /* extra line width for the flat silhouette (the neon glow) */
/* full = outline + fill, back limbs a shade darker; !full = one flat silhouette (ghosts, chroma, glow) */
static void draw_stick(CInstance *s, const GPose *p, float x, float y, float f, int fill, int back, int line,
                       float al, int full) {
    V2 J[12];
    fk(p, x, y, f, J);
    for (int i = 0; i < 12; i++) if (!finite_(J[i].x) || !finite_(J[i].y)) return;
    int over = p->flags & 1;
    float o2 = 2 * G_W_OUT;
    if (full) {
        layer(s, J, BACK_LEG, 2, o2, line, al);
        if (!over) layer(s, J, BACK_ARM, 2, o2, line, al);
        layer(s, J, BACK_LEG, 2, 0, back, al);
        if (!over) layer(s, J, BACK_ARM, 2, 0, back, al);
        draw_weapon(s, p, J, f, al, C_WHITE);
        layer(s, J, FRONT_LEG, 2, o2, line, al);
        bone(s, J[0], J[1], G_W_TORSO + o2, line, al, 1);
        layer(s, J, FRONT_ARM, 2, o2, line, al);
        if (over) layer(s, J, BACK_ARM, 2, o2, line, al);
        spr(s, GR_SHAPE, 1, J[3].x, J[3].y, (G_HEAD_R + G_W_OUT) / 16.0f, (G_HEAD_R + G_W_OUT) / 16.0f, 0, line, al);
        layer(s, J, FRONT_LEG, 2, 0, fill, al);
        bone(s, J[0], J[1], G_W_TORSO, fill, al, 1);
        layer(s, J, FRONT_ARM, 2, 0, fill, al);
        if (over) layer(s, J, BACK_ARM, 2, 0, fill, al);
        spr(s, GR_SHAPE, 1, J[3].x, J[3].y, G_HEAD_R / 16.0f, G_HEAD_R / 16.0f, 0, fill, al);
    } else {
        float e = g_extra_w;
        layer(s, J, BACK_LEG, 2, e, fill, al); layer(s, J, BACK_ARM, 2, e, fill, al);
        layer(s, J, FRONT_LEG, 2, e, fill, al); bone(s, J[0], J[1], G_W_TORSO + e, fill, al, 1);
        layer(s, J, FRONT_ARM, 2, e, fill, al);
        spr(s, GR_SHAPE, 1, J[3].x, J[3].y, (G_HEAD_R + e * 0.5f) / 16.0f, (G_HEAD_R + e * 0.5f) / 16.0f, 0, fill, al);
        draw_weapon(s, p, J, f, al * 0.8f, fill);
    }
}
/* the glitch look: a cyan and a magenta copy split sideways (additive), then him */
static void draw_glitched(CInstance *s, const GPose *p, float x, float y, float f, int fill, int back, int line,
                          float al, float split) {
    if (split > 0.2f) {
        blend(s, 1);
        draw_stick(s, p, x - split, y, f, C_CYAN, C_CYAN, C_CYAN, al * 0.45f, 0);
        draw_stick(s, p, x + split, y, f, C_MAG, C_MAG, C_MAG, al * 0.45f, 0);
        blend(s, 0);
    }
    draw_stick(s, p, x, y, f, fill, back, line, al, 1);
}

/* ------------------------------------------------------------------------------------------ */
/* effects, clones, projectiles, ice spikes                                                    */
/* ------------------------------------------------------------------------------------------ */
static int color_of(int c) {
    switch (c) { case GC_GLITCH: return C_CYAN; case GC_ICE: return C_ICE; case GC_FIRE: return C_FIRE;
                 case GC_VOLT: return C_VOLT; }
    return C_WHITE;
}
static Fx *fx_at(Grey *j, int a, float x, float y, float xs, float ys, float rot, int tpf, int add, int col) {
    int best = 0;
    for (int i = 0; i < N_FX; i++) { if (!j->fx[i].on) { best = i; break; } if (j->fx[i].t > j->fx[best].t) best = i; }
    Fx *f = &j->fx[best];
    f->on = 1; f->t = 0; f->a = a; f->tpf = tpf < 1 ? 1 : tpf; f->n = k_grey_sprites[a].frames; f->add = add; f->col = col;
    f->x = x; f->y = y; f->xs = xs; f->ys = ys; f->rot = rot;
    return f;
}
static void fx_kind(Grey *j, int kind, float x, float y, float sc, float f) {
    switch (kind) {
    case GF_GLITCH: fx_at(j, GR_GLITCH, x, y, sc, sc, 0, 2, 0, C_WHITE); break;
    case GF_SPARK: fx_at(j, GR_SPARK, x, y, sc, sc, frand(0, 45), 1, 1, C_WHITE); break;
    case GF_SHOCK: fx_at(j, GR_RING, x, y, sc, sc, 0, 2, 1, C_CYAN); break;
    case GF_FIREBURST: fx_at(j, GR_FIREBURST, x, y, sc * 0.7f, sc * 0.7f, 0, 2, 0, C_WHITE); break;
    case GF_SHATTER: fx_at(j, GR_SHATTER, x, y, sc, sc, 0, 2, 0, C_WHITE); break;
    case GF_ARC: fx_at(j, GR_ARC, x, y, f * sc, sc, 0, 2, 1, C_WHITE); break;
    case GF_RING: fx_at(j, GR_RING, x, y, sc * 1.1f, sc * 1.1f, 0, 2, 1, RGB(120, 190, 235)); break;
    case GF_BOLT: fx_at(j, GR_BOLT, x, y - 30 * sc, sc, sc, 0, 2, 1, C_WHITE); break;
    case GF_PILLAR: fx_at(j, GR_PILLAR, x, y, sc * 1.1f, sc * 1.1f, 0, 3, 0, C_WHITE); break;
    case GF_ERROR: fx_at(j, GR_ERROR, x, y, sc, sc, 0, 6, 0, C_WHITE); break;
    case GF_SPAWN: fx_at(j, GR_SPAWN, x, y, sc * 0.7f, sc * 0.75f, 0, 1, 1, RGB(110, 200, 240)); break;
    }
}
/* a hitbox; the impact (star, sparks, debris, a screen tear on knockdowns) only if it lands on someone */
static bool hit_at(CInstance *s, Grey *j, float x, float y, int mask, float xs, float ys, double dmg, double hf,
                   double vf, int stun, int knock, int spr_hit, int col, int snd) {
    Hit h = { my_dmg(s) * dmg, hf, vf, stun, 6, xs, ys, mask, 1, knock, 1, knock,
              spr_hit == 3 ? SPR_HIT_3 : spr_hit == 5 ? SPR_HIT_5 : SPR_HIT_1, color_of(col), snd < 1 ? 1 : snd };
    spawn_hit(s, x, y, &h);
    float half = mask == SPR_MASK64 ? 32.0f : mask == SPR_MASK32 ? 16.0f : mask == SPR_MASK24 ? 12.0f : 8.0f;
    if (!enemy_in_box(s, x, y, half * fabsf_(xs), half * fabsf_(ys))) return false;
    float power = knock ? 1.0f : (dmg >= 0.9 ? 0.7f : 0.4f);
    impact(j, x, y, col, power);
    if (knock && j->scr_t < 5) j->scr_t = 5;
    return true;
}
static void spawn_clone(Grey *j, int tl, float x, float y, float f, int tint) {
    int best = 0;
    for (int i = 0; i < N_CLONE; i++) { if (!j->cl[i].on) { best = i; break; } if (j->cl[i].t > j->cl[best].t) best = i; }
    Clone *c = &j->cl[best];
    c->on = 1; c->tl = tl; c->t = 0; c->ev = 0; c->tint = tint; c->fade = 0; c->x = x; c->y = y; c->f = f;
    fx_kind(j, GF_SPAWN, x, y, 1, f);
    fx_kind(j, GF_GLITCH, x, y - 30, 0.8f, f);
    for (int k = 0; k < 16; k++) {                                   /* pixels rushing in to build him */
        float ox = frand(-26, 26), oy = frand(-62, 6);
        Part *q = part(j, PK_PIXEL, x + ox, y - 28 + oy, -ox / 7.0f, -oy / 7.0f, 8, frand(1.5f, 3), glitch_col());
        if (q) { q->g = 0; q->drag = 1; }
    }
}
static void spawn_proj(Grey *j, int kind, float x, float y, float vx, float vy, float dmg, float f, float floor_y) {
    int best = 0;
    for (int i = 0; i < N_PROJ; i++) { if (!j->pr[i].on) { best = i; break; } if (j->pr[i].t > j->pr[best].t) best = i; }
    Proj *p = &j->pr[best];
    p->on = 1; p->kind = kind; p->t = 0; p->x = x; p->y = y; p->vx = vx; p->vy = vy; p->dmg = dmg; p->f = f; p->floor_y = floor_y;
}
static void spawn_spike(Grey *j, float x, float y, float size, float vf, float dmg, float f) {
    int best = 0;
    for (int i = 0; i < N_SPIKE; i++) { if (!j->sp[i].on) { best = i; break; } if (j->sp[i].t > j->sp[best].t) best = i; }
    Spike *k = &j->sp[best];
    k->on = 1; k->t = 0; k->hit = 0; k->x = x; k->y = y; k->size = size; k->vf = vf; k->dmg = dmg; k->f = f;
}

/* the events of a timeline at time t: for Grey himself (c == 0) or for a clone */
static void run_events(CInstance *s, Grey *j, int tl, int t, int *ev, float bx, float by, float f) {
    const GTimeline *T = &k_gtl[tl];
    while (*ev < T->nevt && k_gevts[T->evt0 + *ev].t <= t) {
        const GEvt *e = &k_gevts[T->evt0 + *ev];
        (*ev)++;
        float x = bx, y = by;
        if (e->flags & 2) {                                   /* measured from the opponent */
            int tid = -1;
            CInstance *en = nearest_enemy(s, &tid, 360, 160);
            if (en) { x = (float)sget(en, &g_VAR_x); y = (float)sget(en, &g_VAR_y); }
            else x = bx + f * 50;
        }
        const int16_t *q = e->p;
        switch (e->type) {
        case GE_HIT: {
            int mask = q[2] >= 64 ? SPR_MASK64 : q[2] >= 32 ? SPR_MASK32 : q[2] >= 24 ? SPR_MASK24 : SPR_MASK16;
            bool landed = hit_at(s, j, x + f * q[0] / 4.0f, y + q[1] / 4.0f, mask, q[3] / 100.0f, q[4] / 100.0f, q[5] / 100.0,
                                 f * q[6] / 10.0, q[7] / 10.0, q[8], e->flags & 1, (e->flags >> 2) & 7, q[9], (e->flags >> 5) & 3);
            if (landed && tl < GT_FIRST_CLONE && j->move == tl) {  /* hit-stop on his own blows that land */
                int hs = (e->flags & 1) ? 6 : (q[5] >= 90 ? 3 : 0);
                if (hs > j->hitstop) {
                    double a2 = sget_i(s, &g_VAR_alarm, 2);
                    if (a2 > 0) bset_i(s, &g_VAR_alarm, 2, a2 + (hs - j->hitstop));   /* the combo window waits too */
                    j->hitstop = hs;
                }
            }
            break;
        }
        case GE_CLONE:
            if (q[2] >= 0 && q[2] < GT_COUNT) spawn_clone(j, q[2], x + f * q[0] / 4.0f, y + q[1] / 4.0f, f * (q[3] < 0 ? -1.0f : 1.0f), q[4]);
            break;
        case GE_PROJ:
            spawn_proj(j, q[2], x + f * q[0] / 4.0f, y + q[1] / 4.0f, f * q[3] / 10.0f, q[4] / 10.0f, q[5] / 100.0f, f, by);
            break;
        case GE_SPIKE:
            spawn_spike(j, x + f * q[0] / 4.0f, y, q[2] / 100.0f, q[3] / 10.0f, q[4] / 100.0f, f);
            break;
        case GE_FX:
            fx_kind(j, q[2], x + f * q[0] / 4.0f, y + q[1] / 4.0f, q[3] / 100.0f, f);
            break;
        case GE_SND:
            if (q[0] > 0) play(s, q[0], q[1] / 100.0);
            else play_c(s, -q[0] - 1, q[1] / 100.0);
            break;
        case GE_SHAKE: camera_shake(q[0]); break;
        case GE_TELE: if (tl < GT_FIRST_CLONE) {             /* blink to the other side of him */
            int tid = -1;
            CInstance *en = nearest_enemy(s, &tid, 260, 120);
            if (!en) break;
            float ex = (float)sget(en, &g_VAR_x), ox = sx_(s), oy = sy_(s);
            float nx = ex + j->dir * (q[0] == 0 ? 28.0f : -28.0f);
            if (!free_at(s, nx, oy)) break;
            fx_kind(j, GF_GLITCH, ox, oy - 30, 1.2f, j->dir);
            bset(s, &g_VAR_x, nx);
            if (q[0] == 0) { j->dir = -j->dir; bset(s, &g_VAR_image_xscale, j->dir); }
            fx_kind(j, GF_SPAWN, nx, oy, 1, j->dir);
            j->blend_t = 0;
            break;
        }
        case GE_VEL: if (tl < GT_FIRST_CLONE) { bset(s, &g_VAR_hspeed, f * q[0] / 10.0); bset(s, &g_VAR_vspeed, q[1] / 10.0); } break;
        case GE_GLITCH: if (j->glitch_t < q[0]) j->glitch_t = q[0]; break;
        }
    }
}

static void clones_step(CInstance *s, Grey *j) {
    for (int i = 0; i < N_CLONE; i++) {
        Clone *c = &j->cl[i];
        if (!c->on) continue;
        if (c->fade) { if (++c->fade > 8) c->on = 0; continue; }
        c->t++;
        GPose p; tl_sample(c->tl, (float)c->t, &p);
        run_events(s, j, c->tl, c->t, &c->ev, c->x + c->f * p.mx, c->y, c->f);
        if (c->t >= k_gtl[c->tl].dur) {                              /* falls apart into pixels */
            float cx = c->x + c->f * p.mx;
            c->fade = 1; fx_kind(j, GF_GLITCH, cx, c->y - 30, 0.7f, c->f);
            for (int k = 0; k < 14; k++) part(j, PK_PIXEL, cx + frand(-10, 10), c->y - frand(4, 58), frand(-1.5f, 1.5f), frand(-3.5f, -1), 26, frand(1.5f, 3), glitch_col());
            for (int k = 0; k < 4; k++) part(j, PK_BIT, cx + frand(-8, 8), c->y - frand(10, 50), frand(-0.6f, 0.6f), frand(-1.4f, -0.5f), 34, 1, C_CYAN);
        }
    }
}
static void proj_step(CInstance *s, Grey *j) {
    for (int i = 0; i < N_PROJ; i++) {
        Proj *p = &j->pr[i];
        if (!p->on) continue;
        p->t++;
        if (p->kind == GP_FIRE) p->vy += 0.05f;
        p->x += p->vx; p->y += p->vy;
        if (p->kind == GP_FIRE) {                                    /* embers and smoke behind it */
            part(j, PK_EMBER, p->x - p->vx, p->y + frand(-3, 3), -p->vx * 0.2f + frand(-0.5f, 0.5f), frand(-0.8f, 0.2f), 22, frand(1.5f, 3), (rnd() & 1) ? C_FIRE : RGB(255, 210, 90));
            if (p->t % 4 == 0) part(j, PK_SMOKE, p->x - p->vx * 2, p->y, 0, -0.3f, 24, 5, RGB(70, 66, 70));
        } else if (p->kind == GP_SHARD) {
            if (p->t % 2 == 0) part(j, PK_FROST, p->x, p->y, 0, 0, 14, 1.6f, C_ICE);
        } else {
            part(j, PK_PIXEL, p->x - p->vx * 0.5f + frand(-3, 3), p->y - p->vy * 0.5f + frand(-3, 3), 0, 0, 14, 2, glitch_col());
            if (p->t % 2 == 0) part(j, PK_STREAK, p->x, p->y, -p->vx * 0.6f, -p->vy * 0.6f, 6, 1.3f, C_CYAN);
        }
        int tid = -1, boom = 0;
        CInstance *en = p->t > 2 ? nearest_enemy(s, &tid, 400, 200) : 0;   /* armed after 3 frames: seen leaving */
        if (en) {
            float ex = (float)sget(en, &g_VAR_x), ey = (float)sget(en, &g_VAR_y) - 28;
            if (fabsf_(ex - p->x) < 18 && fabsf_(ey - p->y) < 34) boom = 1;
        }
        if (p->kind == GP_SPEAR_DOWN && p->y >= p->floor_y - 4) boom = 1;
        if (p->y > p->floor_y + 2 && p->kind != GP_SPEAR_DOWN) boom = 1;
        if (!boom && p->t > 80) { p->on = 0; continue; }
        if (!boom) continue;
        p->on = 0;
        if (p->kind == GP_FIRE) {
            hit_at(s, j, p->x, p->y, SPR_MASK32, 1.3f, 1.3f, p->dmg, p->vx > 0 ? 3.0 : -3.0, -4.0, 16, 0, 3, GC_FIRE, 1);
            fx_kind(j, GF_FIREBURST, p->x, p->y, 0.6f, p->f);
            for (int k = 0; k < 3; k++) part(j, PK_SMOKE, p->x + frand(-6, 6), p->y + frand(-6, 2), frand(-0.6f, 0.6f), -0.8f, 40, 8, RGB(80, 76, 80));
            if (p->y > p->floor_y - 24) mark(j, 0, p->x, p->floor_y, 26, 150);
        } else if (p->kind == GP_SHARD) {
            hit_at(s, j, p->x, p->y, SPR_MASK16, 1.2f, 1.2f, p->dmg, p->vx > 0 ? 1.5 : -1.5, -1.5, 10, 0, 1, GC_ICE, 1);
            fx_kind(j, GF_SHATTER, p->x, p->y, 0.4f, p->f);
        } else {
            float y = p->kind == GP_SPEAR_DOWN ? p->floor_y - 20 : p->y;
            hit_at(s, j, p->x, y, SPR_MASK32, 1.0f, 1.6f, p->dmg, 0.5 * p->f, -3.0, 18, p->dmg > 0.5f, 3, GC_GLITCH, 1);
            fx_kind(j, GF_GLITCH, p->x, y, 0.9f, p->f);
            if (p->kind == GP_SPEAR_DOWN) fx_kind(j, GF_SHOCK, p->x, p->floor_y - 1, 0.5f, p->f);
        }
    }
}
static void spikes_step(CInstance *s, Grey *j) {
    for (int i = 0; i < N_SPIKE; i++) {
        Spike *k = &j->sp[i];
        if (!k->on) continue;
        if (++k->t >= 30) { k->on = 0; continue; }
        if (k->t == 1) {
            burst(j, PK_FROST, k->x, k->y - 6, 12, 2.4f * k->size, 40, 2.6f, C_ICE);
            fx_at(j, GR_RING, k->x, k->y - 1, 0.45f * k->size, 0.45f * k->size, 0, 2, 1, C_ICE);
            mark(j, 1, k->x, k->y, 30 * k->size, 160);
        }
        if (k->t % 5 == 0) part(j, PK_FROST, k->x + frand(-5, 5), k->y - frand(4, 36 * k->size), frand(-0.3f, 0.3f), -0.4f, 30, 2.2f, C_ICE);
        if (k->t == 21) burst(j, PK_SHARD, k->x, k->y - 20 * k->size, 7, 3.2f, 30, 2.4f, RGB(200, 240, 255));
        if (k->t == 3 && !k->hit) {
            k->hit = 1;
            hit_at(s, j, k->x, k->y - 20 * k->size, SPR_MASK32, 0.7f * k->size, 1.3f * k->size, k->dmg, 1.0 * k->f, k->vf,
                   18, k->vf < -6.5f, 3, GC_ICE, 1);
        }
    }
}
static void fx_step(Grey *j) {
    for (int i = 0; i < N_FX; i++) if (j->fx[i].on && ++j->fx[i].t >= j->fx[i].n * j->fx[i].tpf) j->fx[i].on = 0;
    for (int i = 0; i < N_GHOST; i++) if (j->gh[i].on && ++j->gh[i].t >= 12) j->gh[i].on = 0;
}
static void ghost_push(Grey *j, const GPose *p, float x, float y, float f, int col) {
    Ghost *g = &j->gh[j->gh_head];
    j->gh_head = (j->gh_head + 1) % N_GHOST;
    g->on = 1; g->t = 0; g->p = *p; g->x = x; g->y = y; g->f = f; g->col = col;
}

/* ------------------------------------------------------------------------------------------ */
/* the overhaul: particles, ribbon trails, lightning, ground marks, impacts                     */
/* ------------------------------------------------------------------------------------------ */
/* a thin stretched GR_SHAPE quad between two points: the proven sprite path, no draw_primitive
   (the base game never uses draw_primitive/draw_vertex, so we don't either). Additive is set by
   the caller. */
static void seg(CInstance *s, float x0, float y0, float x1, float y1, float w, int col, float a) {
    if (!finite_(x0) || !finite_(y0) || !finite_(x1) || !finite_(y1) || a <= 0.004f) return;
    float dx = x1 - x0, dy = y1 - y0, len = sqrtf_(dx * dx + dy * dy);
    if (len < 0.3f) len = 0.3f;
    spr(s, GR_SHAPE, 0, (x0 + x1) * 0.5f, (y0 + y1) * 0.5f, (len + w) / 32.0f, (2 * w) / 32.0f,
        -atan2f_(dy, dx) * 57.29578f, col, a);
}

/* particles */
static Part *part(Grey *j, int kind, float x, float y, float vx, float vy, int life, float size, int col) {
    if (!finite_(x) || !finite_(y)) return 0;
    Part *p = &j->pt[j->pt_head];
    j->pt_head = (j->pt_head + 1) % N_PART;
    p->on = 1; p->kind = kind; p->t = 0; p->life = life < 2 ? 2 : life; p->col = col; p->frame = (int)(rnd() % 8);
    p->x = x; p->y = y; p->vx = vx; p->vy = vy; p->size = size; p->dsize = 0; p->rot = frand(0, 360); p->vr = 0; p->a0 = 1;
    switch (kind) {
    case PK_SPARK: p->g = 0.18f; p->drag = 0.9f; break;
    case PK_EMBER: p->g = -0.05f; p->drag = 0.95f; break;
    case PK_FROST: p->g = -0.015f; p->drag = 0.94f; p->dsize = 0.05f; break;
    case PK_PIXEL: p->g = 0.12f; p->drag = 0.96f; p->vr = frand(-12, 12); break;
    case PK_SMOKE: p->g = -0.04f; p->drag = 0.94f; p->dsize = 0.03f; p->a0 = 0.55f; break;
    case PK_STREAK: p->g = 0; p->drag = 0.88f; break;
    case PK_BIT: p->g = -0.03f; p->drag = 0.97f; p->frame = (int)(rnd() % 2); break;
    case PK_SHARD: p->g = 0.25f; p->drag = 0.97f; p->vr = frand(-20, 20); break;
    case PK_FLASH: p->g = 0; p->drag = 1; p->dsize = size * 0.4f; p->a0 = 0.75f; break;
    }
    return p;
}
static void burst(Grey *j, int kind, float x, float y, int n, float spd, int life, float size, int col) {
    for (int i = 0; i < n; i++) {
        float a = frand(0, 6.2831f), v = spd * frand(0.35f, 1.0f);
        part(j, kind, x, y, cosf_(a) * v, sinf_(a) * v, life + (int)frand(-life * 0.3f, life * 0.3f), size * frand(0.7f, 1.3f), col);
    }
}
static void parts_step(Grey *j) {
    for (int i = 0; i < N_PART; i++) {
        Part *p = &j->pt[i];
        if (!p->on) continue;
        if (++p->t >= p->life) { p->on = 0; continue; }
        p->vy += p->g; p->vx *= p->drag; p->vy *= p->drag;
        p->x += p->vx; p->y += p->vy; p->rot += p->vr; p->size += p->dsize;
        if (p->kind == PK_SHARD && p->vy > 0 && p->t > 6 && p->vy > 3) p->vy *= -0.3f;
    }
}
static int glitch_col(void) { unsigned r = rnd() % 4; return r == 0 ? C_WHITE : r == 1 ? C_MAG : C_CYAN; }
static void parts_draw(CInstance *s, Grey *j, int additive) {
    /* two groups per pass, one texture each (additive: shapes, then bits; normal: smoke under the pixels) */
    for (int grp = 0; grp < 2; grp++)
    for (int i = 0; i < N_PART; i++) {
        Part *p = &j->pt[i];
        if (!p->on) continue;
        int add = p->kind != PK_PIXEL && p->kind != PK_SMOKE && p->kind != PK_SHARD;
        if (add != additive) continue;
        if ((additive ? p->kind == PK_BIT : p->kind != PK_SMOKE) != grp) continue;
        float u = (float)p->t / p->life, a = p->a0 * (1 - u * u);
        switch (p->kind) {
        case PK_SPARK: case PK_STREAK: {
            float sp = sqrtf_(p->vx * p->vx + p->vy * p->vy);
            float len = p->kind == PK_STREAK ? p->size * 6 : 1.5f + sp * 1.6f;
            spr(s, GR_SHAPE, 0, p->x, p->y, len / 32.0f, p->size / 32.0f, -atan2f_(p->vy, p->vx) * 57.29578f, p->col, a);
            break;
        }
        case PK_EMBER: case PK_FROST: case PK_FLASH:
            spr(s, GR_SHAPE, 1, p->x, p->y, p->size / 32.0f, p->size / 32.0f, 0, p->col,
                p->kind == PK_EMBER ? a * (0.6f + 0.4f * (float)((p->t + p->frame) % 3 != 0)) : a);
            break;
        case PK_PIXEL: case PK_SHARD:
            spr(s, GR_SHAPE, 0, p->x, p->y, p->size / 32.0f, p->size / 32.0f, p->rot, p->col, a);
            break;
        case PK_SMOKE:
            spr(s, GR_SMOKE, (float)(u * 7.99f), p->x, p->y, p->size / 12.0f, p->size / 12.0f, 0, p->col, a);
            break;
        case PK_BIT:
            spr(s, GR_BITS, (float)p->frame, p->x, p->y, 1, 1, 0, p->col, a * (p->t % 6 < 4 ? 1.0f : 0.3f));
            break;
        }
    }
}

/* ribbon trails: where his hands, feet and blade tip have been over the last frames */
static void trails_push(Grey *j, const GPose *p, float x, float y, float f) {
    V2 J[12]; fk(p, x, y, f, J);
    TrailS *t = &j->tr[j->tr_head];
    j->tr_head = (j->tr_head + 1) % N_TRS;
    if (j->tr_n < N_TRS) j->tr_n++;
    const int idx[4] = { 7, 5, 11, 9 };
    for (int k = 0; k < 4; k++) { t->x[k] = J[idx[k]].x; t->y[k] = J[idx[k]].y; t->on[k] = 1; }
    int wk = (p->flags >> 2) & 7;
    t->on[4] = wk != 0;
    if (wk) {
        V2 d = dir_of(p->a[GA_W], p->rot, f);
        float len = wk == GW_SPEAR ? 50 : wk == GW_GIANT ? 141 : wk == GW_AXE ? 52 : wk == GW_BOW ? 28 : 44;   /* tips: spear 50, sword 44 (x3.2 giant), axe head 52, bow tip 28 */
        t->x[4] = J[7].x + d.x * len; t->y[4] = J[7].y + d.y * len;
    }
}
static void trails_clear(Grey *j) { j->tr_n = 0; }
static void trails_draw(CInstance *s, Grey *j, float strength) {
    if (j->tr_n < 3 || strength <= 0.02f) return;
    for (int k = 0; k < N_TRP; k++) {
        float fastest = 0;                                           /* only the points moving fast */
        for (int i = 0; i + 1 < j->tr_n && i < 4; i++) {
            const TrailS *a = &j->tr[(j->tr_head - 1 - i + 2 * N_TRS) % N_TRS], *b = &j->tr[(j->tr_head - 2 - i + 2 * N_TRS) % N_TRS];
            if (!a->on[k] || !b->on[k]) continue;
            float dx = a->x[k] - b->x[k], dy = a->y[k] - b->y[k], d = sqrtf_(dx * dx + dy * dy);
            if (d > fastest) fastest = d;
        }
        if (fastest < (k == 4 ? 4.0f : 3.2f)) continue;
        float w0 = k == 4 ? 5.0f : 3.2f;
        for (int i = 0; i < j->tr_n - 1; i++) {
            const TrailS *a = &j->tr[(j->tr_head - 1 - i + 2 * N_TRS) % N_TRS], *b = &j->tr[(j->tr_head - 2 - i + 2 * N_TRS) % N_TRS];
            if (!a->on[k] || !b->on[k]) break;
            float dx = a->x[k] - b->x[k], dy = a->y[k] - b->y[k], d = sqrtf_(dx * dx + dy * dy);
            if (d > 90) break;                                       /* a teleport: don't smear across */
            float u = (float)i / (j->tr_n - 1), w = w0 * (1 - u * 0.85f);
            int col = u < 0.3f ? C_WHITE : (u < 0.65f ? C_CYAN : C_MAG);
            float al = strength * (1 - u) * (k == 4 ? 0.9f : 0.6f);
            seg(s, a->x[k], a->y[k], b->x[k], b->y[k], w, col, al);
        }
    }
}

/* lightning: a jagged ribbon between two points, re-rolled every other frame */
static void bolt(Grey *j, float x0, float y0, float x1, float y1, int life, float w, int col) {
    int best = 0;
    for (int i = 0; i < N_BOLT; i++) { if (!j->bo[i].on) { best = i; break; } if (j->bo[i].t > j->bo[best].t) best = i; }
    Bolt *b = &j->bo[best];
    b->on = 1; b->t = 0; b->life = life; b->seed = (int)(rnd() & 0xffff); b->col = col;
    b->x0 = x0; b->y0 = y0; b->x1 = x1; b->y1 = y1; b->w = w;
}
static void bolts_draw(CInstance *s, Grey *j) {
    for (int i = 0; i < N_BOLT; i++) {
        Bolt *b = &j->bo[i];
        if (!b->on) continue;
        unsigned save = g_rng;
        g_rng = (unsigned)(b->seed * 2654435761u) + (unsigned)(b->t / 2) * 40503u + 1u;
        float dx = b->x1 - b->x0, dy = b->y1 - b->y0, len = sqrtf_(dx * dx + dy * dy);
        if (len < 1) { g_rng = save; continue; }
        float nx = -dy / len, ny = dx / len, fade = 1 - (float)b->t / b->life;
        const int SEG = 10;
        float px[SEG + 1], py[SEG + 1];
        for (int k = 0; k <= SEG; k++) {
            float u = (float)k / SEG, off = (k == 0 || k == SEG) ? 0 : frand(-1, 1) * len * 0.12f;
            px[k] = b->x0 + dx * u + nx * off; py[k] = b->y0 + dy * u + ny * off;
        }
        g_rng = save;
        for (int pass = 0; pass < 2; pass++) {                       /* wide coloured glow, then a white core */
            float w = pass ? b->w : b->w * 0.4f;
            int col = pass ? b->col : C_WHITE;
            float a = fade * (pass ? 0.5f : 1.0f);
            for (int k = 0; k < SEG; k++) seg(s, px[k], py[k], px[k + 1], py[k + 1], w, col, a);
        }
    }
}
static void bolts_step(Grey *j) { for (int i = 0; i < N_BOLT; i++) if (j->bo[i].on && ++j->bo[i].t >= j->bo[i].life) j->bo[i].on = 0; }

/* scorch and frost marks on the floor */
static void mark(Grey *j, int kind, float x, float y, float w, int life) {
    int best = 0;
    for (int i = 0; i < N_MARK; i++) { if (!j->mk[i].on) { best = i; break; } if (j->mk[i].t > j->mk[best].t) best = i; }
    Mark *m = &j->mk[best];
    m->on = 1; m->t = 0; m->life = life; m->kind = kind; m->x = x; m->y = y; m->w = w;
}
static void marks_step(Grey *j) { for (int i = 0; i < N_MARK; i++) if (j->mk[i].on && ++j->mk[i].t >= j->mk[i].life) j->mk[i].on = 0; }
static void marks_draw(CInstance *s, Grey *j) {
    for (int kind = 0; kind < 2; kind++) {                   /* scorch (normal), then frost (additive) */
        for (int i = 0; i < N_MARK; i++) {
            Mark *m = &j->mk[i];
            if (!m->on || m->kind != kind) continue;
            float a = 1 - (float)m->t / m->life;
            if (kind == 0) spr(s, GR_SHAPE, 1, m->x, m->y + 1, m->w / 32.0f, m->w * 0.16f / 32.0f, 0, RGB(30, 18, 14), 0.55f * a);
            else { blend(s, 1); spr(s, GR_SHAPE, 1, m->x, m->y + 1, m->w / 32.0f, m->w * 0.18f / 32.0f, 0, C_ICE, 0.35f * a); }
        }
    }
    blend(s, 0);
}

/* the moment a blow lands: a star, sparks, speed lines out from the hit, a flash, element bits */
static void impact(Grey *j, float x, float y, int col, float power) {
    fx_at(j, GR_STAR, x, y, 0.7f + 0.5f * power, 0.7f + 0.5f * power, frand(0, 30), 1, 1, C_WHITE);
    part(j, PK_FLASH, x, y, 0, 0, 4, 6 + 6 * power, C_WHITE);
    burst(j, PK_SPARK, x, y, (int)(8 + 10 * power), 4.5f + 3 * power, 12, 1.6f, glitch_col());
    for (int k = 0; k < 6; k++) {                                     /* speed lines bursting out */
        float a = k * 1.047f + frand(-0.3f, 0.3f);
        part(j, PK_STREAK, x + cosf_(a) * 8, y + sinf_(a) * 8, cosf_(a) * 7, sinf_(a) * 7, 7, 1.2f, C_WHITE);
    }
    switch (col) {
    case GC_FIRE: burst(j, PK_EMBER, x, y, 10, 3.0f, 34, 2.4f, C_FIRE); part(j, PK_SMOKE, x, y - 4, 0, -0.6f, 30, 10, RGB(90, 90, 96)); break;
    case GC_ICE: burst(j, PK_FROST, x, y, 10, 2.2f, 36, 3.0f, C_ICE); burst(j, PK_SHARD, x, y, 6, 3.5f, 26, 2.2f, RGB(200, 240, 255)); break;
    case GC_VOLT: bolt(j, x, y - 70, x + frand(-8, 8), y, 8, 3.5f, C_VOLT); burst(j, PK_SPARK, x, y, 6, 6, 10, 1.4f, C_VOLT); break;
    default: burst(j, PK_PIXEL, x, y, (int)(8 + 6 * power), 3.2f, 26, 2.2f, glitch_col()); break;
    }
}

/* ------------------------------------------------------------------------------------------ */
/* moves                                                                                       */
/* ------------------------------------------------------------------------------------------ */
static bool on_air(CInstance *s) { return parent_ok(s) && pget(s, &g_VAR_is_onair) > 0.5; }
static bool is_cpu(CInstance *s) { return parent_ok(s) && pget(s, &g_VAR_plr_controller) == 2; }
static bool running(CInstance *s) {
    if (parent_ok(s) && pget(s, &g_VAR_is_running) > 0.5) return true;
    double hs = sget(s, &g_VAR_hspeed);
    return (hs < 0 ? -hs : hs) > iget(s, &g_VAR_stats_walkspd) + 0.8;
}
static void crossfade(Grey *j, int frames) {
    j->from = j->drawn;
    j->from.rot = wrap180(j->from.rot);
    j->blend_t = frames;
}
/* a small step-in so the first blow connects (opponent close in front only; never a long dash) */
static void home(CInstance *s, Grey *j) {
    int tid = -1;
    j->home_t = 0;
    CInstance *e = nearest_enemy(s, &tid, 90, 60);
    if (!e) return;
    float dx = (float)sget(e, &g_VAR_x) - sx_(s);
    if (dx * j->dir < 0) {
        if (fabsf_(dx) > 30) return;
        j->dir = -j->dir; bset(s, &g_VAR_image_xscale, j->dir);
    }
    float gap = fabsf_(dx) - 30;
    if (gap <= 1) return;
    if (gap > 36) gap = 36;
    j->home_v = gap / 6; j->home_t = 6;
}
static void start_move(CInstance *s, Grey *j, int tl, int chain) {
    j->move = tl; j->t = 0; j->ev = 0; j->mx_prev = 0;
    j->dir = facing(s);
    iset(s, &g_VAR_combo_next, chain);
    iset_b(s, &g_VAR_combo_nextcombo, false);
    bset_i(s, &g_VAR_alarm, 2, k_gtl[tl].dur);
    bset(s, &g_VAR_sprite_index, g_grey_spr[GR_M_ATTACK]);
    bset(s, &g_VAR_image_index, 0);
    bset(s, &g_VAR_image_speed, 0);
    crossfade(j, 4);
    j->src = 100 + tl;
    if (tl == GT_A1 || tl == GT_B1 || tl == GT_CA) home(s, j);
}
static void end_move(CInstance *s, Grey *j) {
    j->move = MOVE_NONE; j->home_t = 0;
    bset(s, &g_VAR_image_speed, 0.25);
    if (sget_i(s, &g_VAR_alarm, 2) > 1) bset_i(s, &g_VAR_alarm, 2, 1);      /* finished early: chain now */
}
static void start_special(CInstance *s, Grey *j);
static void grey_start(CInstance *s, int step) {
    Grey *j = slot(s, true);
    if (j->sp_on) return;
    int run = running(s) && !on_air(s);
    switch (step) {
    case 1: if (run) start_move(s, j, GT_RD, 2); else start_move(s, j, GT_A1, k_gtl[GT_A1].chain); break;
    case 2: start_move(s, j, GT_A2, k_gtl[GT_A2].chain); break;
    case 3: start_move(s, j, GT_A3, k_gtl[GT_A3].chain); break;
    case 4: start_move(s, j, GT_A4, k_gtl[GT_A4].chain); break;
    case 5: start_move(s, j, GT_A5, -1); break;
    case 50: if (run) start_move(s, j, GT_RD, 51); else start_move(s, j, GT_B1, k_gtl[GT_B1].chain); break;
    case 51: start_move(s, j, GT_B2, k_gtl[GT_B2].chain); break;
    case 52: start_move(s, j, GT_B3, k_gtl[GT_B3].chain); break;
    case 53: start_move(s, j, GT_B4, -1); break;
    case 10: start_move(s, j, GT_CA, -1); break;
    case 60: start_move(s, j, GT_CB, -1); break;
    case 11: start_move(s, j, GT_AA, k_gtl[GT_AA].chain); break;
    case 12: if (on_air(s)) start_move(s, j, GT_AA2, k_gtl[GT_AA2].chain); else goto end_combo; break;   /* air chain */
    case 13: if (on_air(s)) start_move(s, j, GT_AA3, -1); else goto end_combo; break;
    case 61: start_move(s, j, GT_AB, -1); break;
    case 100: start_move(s, j, GT_S1, -1); bset(s, &g_VAR_hspeed, 0); break;
    case 110: start_move(s, j, GT_S2, -1); bset(s, &g_VAR_hspeed, 0); break;
    default:                                               /* unknown step: end the attack cleanly */
    end_combo:
        iset(s, &g_VAR_combo_next, -1);
        bset_i(s, &g_VAR_alarm, 2, 1);
        break;
    }
}
static bool air_move(int tl) { return tl == GT_AA || tl == GT_AB || tl == GT_AA2 || tl == GT_AA3; }
/* the end of the air chain: the spear hits the floor */
static void data_crash_landing(CInstance *s, Grey *j) {
    float x = sx_(s), y = sy_(s), f = j->dir;
    hit_at(s, j, x + f * 18, y - 14, SPR_MASK64, 1.6f, 1.0f, 1.4, f * 5.0, -7.0, 24, 1, 3, GC_GLITCH, 2);
    fx_kind(j, GF_SHATTER, x + f * 18, y - 20, 1.2f, f);
    fx_at(j, GR_RING, x, y - 1, 1.0f, 1.0f, 0, 2, 1, C_CYAN);
    fx_at(j, GR_RING, x, y - 1, 1.6f, 1.6f, 0, 3, 1, C_MAG);
    spawn_spike(j, x - f * 30, y, 0.9f, -4.0f, 0.2f, f);
    spawn_spike(j, x + f * 46, y, 1.0f, -4.0f, 0.2f, f);
    burst(j, PK_PIXEL, x, y - 10, 24, 5.0f, 30, 2.4f, C_CYAN);
    burst(j, PK_SPARK, x + f * 18, y - 8, 14, 6.0f, 14, 1.6f, C_WHITE);
    for (int k = 0; k < 4; k++) part(j, PK_SMOKE, x + frand(-24, 24), y - 2, frand(-1.5f, 1.5f), -frand(0.2f, 0.7f), 34, 8, RGB(150, 150, 160));
    mark(j, 0, x + f * 10, y, 60, 180);
    camera_shake(2);
    play(s, SND_STRONG2, 0.9); play_c(s, GS_GLITCH, 0.8);
    j->glitch_t = 10;
}
static void move_step(CInstance *s, Grey *j) {
    if (j->hitstop > 0) { j->hitstop--; bset(s, &g_VAR_hspeed, 0); return; }   /* frozen on the impact */
    int t = ++j->t;
    GPose p; tl_sample(j->move, (float)t, &p);
    if (g_tl_has_mx[j->move]) {                            /* root motion: the timeline walks him */
        float d = p.mx - j->mx_prev;
        j->mx_prev = p.mx;
        double hs = j->dir * d;
        if (j->home_t > 0) { j->home_t--; hs += j->dir * j->home_v; }
        bset(s, &g_VAR_hspeed, hs);
    } else if (!air_move(j->move)) {
        double hs = 0;
        if (j->home_t > 0) { j->home_t--; hs = j->dir * j->home_v; }
        bset(s, &g_VAR_hspeed, hs);
    }
    run_events(s, j, j->move, t, &j->ev, sx_(s), sy_(s), j->dir);
    if (j->move == MOVE_NONE) return;
    if (air_move(j->move) && t > 6 && !on_air(s)) {        /* landed: cut to the landing */
        if (j->move == GT_AB) { fx_kind(j, GF_SHOCK, sx_(s), sy_(s) - 1, 0.6f, j->dir); camera_shake(1); }
        if (j->move == GT_AA3) data_crash_landing(s, j);
        end_move(s, j);
        return;
    }
    if (t >= k_gtl[j->move].dur) end_move(s, j);
}

/* alarm[3]: start of an attack (scr_plr_step sets combo_next) */
void gml_Object_o_grey_Alarm_3(CInstance *s, CInstance *o) {
    (void)o;
    if (parent_ok(s)) pset_b(s, &g_VAR_is_attacking, true);
    grey_start(s, (int)iget(s, &g_VAR_combo_next));
}
/* alarm[2]: the move's window is over -> chain the next one or finish (scr_alarm2_combo) */
void gml_Object_o_grey_Alarm_2(CInstance *s, CInstance *o) {
    (void)o;
    Grey *j = slot(s, true);
    if (j->sp_on) return;
    double next = iget(s, &g_VAR_combo_next);
    RValue *nc = var_slot_r(s, g_VAR_combo_nextcombo.id);
    if (nc && BOOL_RValue(nc) && next > 0) { grey_start(s, (int)next); return; }
    if (j->move != MOVE_NONE) end_move(s, j);
    if (next == -1) {
        if (parent_ok(s)) {
            pset_b(s, &g_VAR_is_attacking, false);
            pset_b(s, &g_VAR_is_airattacking, false);
        }
    } else {
        bset_i(s, &g_VAR_alarm, 2, iget(s, &g_VAR_leavecombo_penaltytime));
        iset(s, &g_VAR_combo_next, -1);
    }
}

/* ------------------------------------------------------------------------------------------ */
/* moving about: walking, running, jumping (with a front flip), guard, hurt - all procedural    */
/* ------------------------------------------------------------------------------------------ */
static int loco_pose(CInstance *s, Grey *j, GPose *o) {
    bool pok = parent_ok(s);
    int sp = (int)sget(s, &g_VAR_sprite_index);
    float hs = (float)sget(s, &g_VAR_hspeed), vs = (float)sget(s, &g_VAR_vspeed);
    #define M(x) (g_grey_spr[GR_M_##x])
    if ((pok && pget(s, &g_VAR_is_fallen) > 0.5) || sp == M(FALLEN)) { base_pose(GPZ_FALLEN, o); j->air_t = 0; return 1; }
    if ((pok && pget(s, &g_VAR_is_hurt) > 0.5) || sp == M(HURT) || sp == M(HURTUP) || sp == M(HURTDOWN)) {
        base_pose(GPZ_HURT, o);
        o->a[GA_HD] += 6 * sinf_(j->aura_t * 1.3f);
        if (on_air(s)) o->rot = -20;
        return 2;
    }
    if (on_air(s)) {
        j->air_t++;
        float dash = (float)iget(s, &g_VAR_stats_airdashspd);
        if (dash > 1 && fabsf_(hs) >= dash * 0.95f) { base_pose(GPZ_AIRDASH, o); return 11; }   /* air dash */
        if (vs < -0.6f) {                                   /* rising: tuck and a front flip */
            base_pose(GPZ_TUCK, o);
            float u = clampf((j->air_t - 3) / 24.0f, 0, 1);
            o->rot = 360 * u * u * (3 - 2 * u);
            return 3;
        }
        base_pose(GPZ_FALL, o);
        o->a[GA_UF] += 8 * sinf_(j->aura_t * 0.3f); o->a[GA_UB] -= 8 * sinf_(j->aura_t * 0.3f);
        return 4;
    }
    j->air_t = 0;
    if (sp == M(CROUCH)) { base_pose(GPZ_CROUCH, o); return 5; }
    if (sp == M(DEFEND) || (pok && pget(s, &g_VAR_key_defend) > 0.5)) { base_pose(GPZ_DEFEND, o); return 6; }
    if (sp == M(CHARGE) || (pok && pget(s, &g_VAR_is_charging) > 0.5)) {
        base_pose(GPZ_CHARGE, o);
        o->hy += 0.6f * sinf_(j->aura_t * 0.9f);
        return 7;
    }
    if (sp == M(RUN) || running(s)) {
        GPose a, b; base_pose(GPZ_RUN1, &a); base_pose(GPZ_RUN2, &b);
        j->phase += (fabsf_(hs) > 1 ? fabsf_(hs) : 6) * 0.075f;
        lerp_pose(&a, &b, (1 - cosf_(j->phase)) * 0.5f, o);
        o->hy -= fabsf_(sinf_(j->phase)) * 2.5f;
        return 8;
    }
    if (sp == M(WALK) || fabsf_(hs) > 0.3f) {
        GPose a, b; base_pose(GPZ_WALK1, &a); base_pose(GPZ_WALK2, &b);
        j->phase += (fabsf_(hs) > 0.5f ? fabsf_(hs) : 3) * 0.085f;
        lerp_pose(&a, &b, (1 - cosf_(j->phase)) * 0.5f, o);
        o->hy -= fabsf_(sinf_(j->phase)) * 1.2f;
        return 9;
    }
    #undef M
    GPose a, b; base_pose(GPZ_STAND, &a); base_pose(GPZ_STAND2, &b);       /* breathing idle */
    lerp_pose(&a, &b, (1 - cosf_(j->aura_t * 0.055f)) * 0.5f, o);
    if (++j->idle_t % 230 == 120) j->glitch_t = 6;                          /* a twitch now and then */
    return 10;
}

/* ------------------------------------------------------------------------------------------ */
/* the special: readiness, the target, starting and ending it                                  */
/* ------------------------------------------------------------------------------------------ */
static bool special_ready(CInstance *s) {
    if (pget(s, &g_VAR_is_hurt) > 0.5 || pget(s, &g_VAR_is_fallen) > 0.5 || pget(s, &g_VAR_is_dead) > 0.5) return false;
    return pget(s, &g_VAR_is_onair) < 0.5;
}
static bool special_pressed(CInstance *s) {
    if (!parent_ok(s)) return false;
    if (pget(s, &g_VAR_keyp_special) < 0.5 || pget(s, &g_VAR_key_defend) < 0.5) return false;
    return special_ready(s);
}
static bool cpu_wants_special(CInstance *s) {
    if (!is_cpu(s) || pget(s, &g_VAR_keyp_special) < 0.5 || !special_ready(s)) return false;
    double e = pget(s, &g_VAR_plr_energy), emax = pget(s, &g_VAR_plr_maxenergy);
    double need = emax > 0 ? (emax < 100 ? emax : 100) : 100;
    if (e + 0.001 < need) return false;
    int tid = -1;
    return nearest_enemy(s, &tid, 300, 140) != 0;
}
static void target_frozen(CInstance *s, Grey *j, bool frozen) {
    if (j->tgt_id < 0) return;
    CInstance *c = YYGML_FindInstance(j->tgt_id);
    if (!c) return;
    RValue cp = rv_undef(); RValue cid = rv_real(j->tgt_id);
    YYGML_Variable_GetValue(&cid, g_VAR_parent.id, ARRAY_INDEX_NONE, &cp, false, false);
    if (inst_exists_rv(s, &cp)) {
        RValue v = rv_bool(!frozen);
        YYGML_Variable_SetValue(&cp, g_VAR_can_move.id, ARRAY_INDEX_NONE, &v);
        YYGML_Variable_SetValue(&cp, g_VAR_can_attack.id, ARRAY_INDEX_NONE, &v);
    }
    rv_free(&cp);
    if (frozen) {
        bset(c, &g_VAR_x, j->tgt_x);
        bset(c, &g_VAR_hspeed, 0);
    }
}
/* the bow stance: double-tap shield toggles it (free and on the ground); the bow forms out of fire and
   glitch, or breaks up into pixels. In the stance shield + skill fires INFERNO ARROW instead of MOONFALL */
static void bow_input(CInstance *s, Grey *j) {
    int now = j->aura_t;
    if (j->bow_cool > 0) j->bow_cool--;
    bool def = pget(s, &g_VAR_key_defend) > 0.5;
    if (def && !j->prev_def) {
        bool free_ = j->move == MOVE_NONE && !j->sp_on && pget(s, &g_VAR_is_hurt) < 0.5 && pget(s, &g_VAR_is_fallen) < 0.5
                     && pget(s, &g_VAR_is_dead) < 0.5 && pget(s, &g_VAR_is_onair) < 0.5;
        if (j->def_t1 > 0 && now - j->def_t1 <= TAP_WINDOW && j->bow_cool == 0 && free_) {
            j->bow = !j->bow; j->bow_cool = 24; j->def_t1 = -1000;
            GPose p; V2 J[12];
            p = j->drawn; fk(&p, sx_(s), sy_(s), facing(s), J);
            j->glitch_t = 10;
            fx_kind(j, GF_GLITCH, J[7].x, J[7].y, 0.9f, facing(s));
            if (j->bow) {                                    /* the bow catches fire as it forms */
                burst(j, PK_EMBER, J[7].x, J[7].y, 16, 2.6f, 26, 2.4f, C_FIRE);
                burst(j, PK_PIXEL, J[7].x, J[7].y, 10, 2.0f, 18, 2.0f, C_CYAN);
                play(s, SND_MAGIC3, 1.3);
            } else burst(j, PK_PIXEL, J[7].x, J[7].y, 16, 2.4f, 20, 2.0f, C_MAG);
            play_c(s, GS_GLITCH, j->bow ? 1.2 : 0.9);
        } else j->def_t1 = now;
    }
    j->prev_def = def;
}
static void start_special(CInstance *s, Grey *j) {
    pset_b(s, &g_VAR_keyp_special, false);
    double e = pget(s, &g_VAR_plr_energy), emax = pget(s, &g_VAR_plr_maxenergy);
    double need = emax > 0 ? (emax < 100 ? emax : 100) : 100;
    int tid = -1;
    CInstance *t = nearest_enemy(s, &tid, 320, 160);
    if (e + 0.001 < need || !t) { j->fail_t = 24; play(s, SND_WOOSH3, 0.6); return; }
    pset(s, &g_VAR_plr_energy, e - need);
    j->sp_on = 1; j->sp_t = 0; j->hit_done = 0; j->move = MOVE_NONE;
    j->sp_kind = j->bow ? SPK_ARROW : SPK_MOON;           /* the bow stance fires INFERNO ARROW, else MOONFALL */
    for (int i = 0; i < N_GP; i++) j->gp[i].on = 0;       /* no debris left over from an earlier MOONFALL */
    j->gp_head = 0;
    j->tgt_id = tid; j->tgt_x = (float)sget(t, &g_VAR_x); j->tgt_y = (float)sget(t, &g_VAR_y);
    j->dir = j->tgt_x >= sx_(s) ? 1.0f : -1.0f;
    bset(s, &g_VAR_image_xscale, j->dir);
    pset_b(s, &g_VAR_is_attacking, true);
    pset_b(s, &g_VAR_can_gethurt, false);
    iset(s, &g_VAR_combo_next, -1);
    bset_i(s, &g_VAR_alarm, 2, -1);
    j->old_depth = sget(s, &g_VAR_depth); j->depth_saved = 1;
    bset(s, &g_VAR_depth, -15000);                          /* the GUI glitch draws over the HUD */
    bset(s, &g_VAR_sprite_index, g_grey_spr[GR_M_ATTACK]);
    bset(s, &g_VAR_hspeed, 0); bset(s, &g_VAR_vspeed, 0);
    j->glitch_t = 24;
    crossfade(j, 6);
    play(s, SND_SUSPENSE, 1.0); play_c(s, GS_GLITCH, 0.8);
}
static void special_end(CInstance *s, Grey *j) {
    target_frozen(s, j, false);
    if (j->depth_saved) { bset(s, &g_VAR_depth, j->old_depth); j->depth_saved = 0; }
    j->sp_on = 0;
    if (parent_ok(s)) pset_b(s, &g_VAR_can_gethurt, true);
}
/* ------------------------------------------------------------------------------------------ */
/* MOONFALL                                                                                    */
/*   Grey reaches up, tears the sky open and glitches the Moon into it. The camera rises out of */
/*   the atmosphere and pulls back to the whole system: Earth and the Moon at their real size   */
/*   ratio (3.67 : 1), the Moon well inside the Roche limit, so it cracks, sheds a stream of     */
/*   debris and falls. Contact is played slow: a white-hot vapour plume, a shockwave racing      */
/*   around the globe, molten ejecta on ballistic arcs (inverse-square gravity, the fast ones    */
/*   escape into a ring), the Moon flattening and sinking, the crust turning to a magma ocean.  */
/*   Then a white-out, back down: the battlefield is now a lava world, and the blow lands.       */
/* ------------------------------------------------------------------------------------------ */
typedef struct { float x, y, z; } V3;
static V3 v3(float x, float y, float z) { V3 r = { x, y, z }; return r; }
static V3 v3s(V3 a, V3 b, float k) { return v3(a.x + b.x * k, a.y + b.y * k, a.z + b.z * k); }   /* a + b k */
static V3 v3k(V3 a, float k) { return v3(a.x * k, a.y * k, a.z * k); }
static float v3dot(V3 a, V3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
static float v3len(V3 a) { return sqrtf_(v3dot(a, a)); }
static V3 v3n(V3 a) { float l = v3len(a); return l > 1e-6f ? v3k(a, 1 / l) : v3(0, 0, 1); }
static float expf_(float x) {                       /* small, bounded exp: (1 + x/256)^256 */
    if (x < -30) return 0;
    if (x > 20) x = 20;
    float r = 1 + x / 256.0f;
    for (int i = 0; i < 8; i++) r *= r;
    return r;
}

/* Earth at the origin, radius 1; view space: x right, y down, z towards the camera (= art/grey/moonfall.py) */
static const V3 MF_N  = { 0.66026f, -0.50020f, 0.56022f };   /* the contact point (= the melt textures') */
static const V3 MF_T1 = { 0.60386f, 0.79709f, 0.0f };         /* the tangent plane there: along the ground ... */
static const V3 MF_T2 = { -0.44655f, 0.33830f, 0.82834f };    /* ... and up towards the camera */
static const V3 MF_TO = { -0.68865f, -0.10557f, 0.71736f };   /* downrange: where the Moon was heading */
static const V3 MF_H  = { -0.29968f, -0.85945f, -0.41417f };  /* its orbit's normal: the debris disc's plane */
#define MF_RM   0.2725f       /* Moon radius / Earth radius (the real ratio) */
#define MF_GM   0.000588f     /* G M_earth in Earth radii^3 / frame^2: the fall from 2.75 radii takes 200 frames */
#define MF_VR   (-0.018375f)  /* the Moon's velocity at contact: radial ... */
#define MF_VT   0.014221f     /* ... and downrange (a 38 degree oblique impact, the likeliest kind) */
#define MF_ROT  37.1467f      /* the Moon sprite's rotation: its local +x points away from the Earth */
#define MF_F    2.15f         /* the space camera's focal length, in GUI heights */
#define MELT_N  5
static const float MELT_TH[MELT_N] = { 0.35f, 0.85f, 1.45f, 2.2f, 3.5f };   /* = moonfall.py MELT (radians) */

static float ease_io(float u) { u = clampf(u, 0, 1); return u * u * (3 - 2 * u); }
static float lin01f(float t, float a, float b) { return clampf((t - a) / (b - a), 0, 1); }
static float lin01(int t, int a, int b) { return lin01f((float)t, (float)a, (float)b); }

static V3 mf_grav(V3 p) {
    float r2 = v3dot(p, p) + 1e-4f, r = sqrtf_(r2);
    return v3k(p, -MF_GM / (r2 * r));
}
/* The Moon's centre at frame t. From the teleport it falls freely (Kepler: from 2.75 Earth radii with 45 %
   of the circular speed, so it swings in on a curve and strikes obliquely). Integrated backwards from the
   moment of contact, so it touches down exactly at MF_HIT on MF_N. Then it ploughs in along its path. */
static float mf_pen(int t) {                         /* how far it has ploughed in (Earth radii) */
    if (t <= MF_HIT) return 0;
    return 0.52f * (1 - expf_(-(float)(t - MF_HIT) / 34.0f));
}
static V3 mf_moon_c(int t, V3 *vel) {
    V3 p = v3k(MF_N, 1 + MF_RM), v = v3s(v3k(MF_N, MF_VR), MF_TO, MF_VT);
    if (t >= MF_HIT) {
        if (vel) *vel = v3k(v, expf_(-(float)(t - MF_HIT) / 34.0f) * 0.6f);
        return v3s(p, v3n(v), mf_pen(t));
    }
    int n = (MF_HIT - (t < MF_MOON ? MF_MOON : t)) * 4;
    const float dt = -0.25f;
    V3 a = mf_grav(p);
    for (int i = 0; i < n; i++) {                    /* velocity Verlet: time-reversible, so this is the fall */
        v = v3s(v, a, dt * 0.5f); p = v3s(p, v, dt); a = mf_grav(p); v = v3s(v, a, dt * 0.5f);
    }
    if (vel) *vel = v;
    return p;
}
/* the melt front: the crustal wave racing round the globe from the contact point (radians) */
static float mf_melt(int t) {
    if (t <= MF_HIT) return 0;
    float k = (float)(t - MF_HIT);
    float th = 0.22f * (1 - expf_(-k / 5.0f)) + 0.031f * k;
    return th < 3.5f ? th : 3.5f;
}

static GPt *gp_new(Grey *j, int kind, V3 p, V3 v, int life, float size) {
    GPt *q = &j->gp[j->gp_head];
    j->gp_head = (j->gp_head + 1) % N_GP;
    q->on = 1; q->kind = (unsigned char)kind; q->t = 0; q->life = (short)life;
    q->x = p.x; q->y = p.y; q->z = p.z; q->vx = v.x; q->vy = v.y; q->vz = v.z;
    q->rot = 0; q->vr = 0; q->size = size; q->frame = (int)(rnd() % 8);
    return q;
}
/* a random direction: the outward normal at the impact, spread, leaning downrange (an oblique impact
   throws most of its ejecta forward) */
static V3 mf_cone(float spread, float down) {
    float a = frand(0, 6.2832f), r = frand(0, spread);
    V3 d = v3s(v3s(v3s(MF_N, MF_T1, cosf_(a) * r), MF_T2, sinf_(a) * r), MF_TO, down);
    return v3n(d);
}
static void gp_step(Grey *j, int t) {
    float dt = (t >= MF_HIT && t < MF_HIT + MF_SLOWMO) ? 0.6f : 1.0f;   /* the first moments in slow motion */
    for (int i = 0; i < N_GP; i++) {
        GPt *q = &j->gp[i];
        if (!q->on) continue;
        if (++q->t >= q->life) { q->on = 0; continue; }
        if (q->kind == GQ_SPLASH) continue;
        V3 p = v3(q->x, q->y, q->z), v = v3(q->vx, q->vy, q->vz);
        V3 a = mf_grav(p);                                         /* inverse-square gravity */
        v = v3s(v, a, dt * 0.5f); p = v3s(p, v, dt); a = mf_grav(p); v = v3s(v, a, dt * 0.5f);
        q->x = p.x; q->y = p.y; q->z = p.z; q->vx = v.x; q->vy = v.y; q->vz = v.z;
        float r = v3len(p);
        if (r < 1.0f && q->t > 4) {                                 /* back down: it splashes into the crust */
            if (q->kind != GQ_DUST) gp_new(j, GQ_SPLASH, v3k(p, 1 / (r + 1e-6f)), v3(0, 0, 0), 14 + (int)(rnd() % 10),
                                         q->kind == GQ_ROCK ? 0.05f : 0.03f);
            q->on = 0;
        } else if (r > 14) q->on = 0;                               /* escaped */
    }
}

/* the camera view in the room (Draw Begin / Draw: the world; the lava world and the sky Moon use it) */
static double fcall1(CInstance *s, void (*fn)(RValue *, CInstance *, CInstance *, int, RValue *), RValue a) {
    RValue r = rv_undef();
    fn(&r, s, s, 1, &a);
    double d = rv_num(&r);
    rv_free(&r);
    return d;
}
static void mf_view(CInstance *s, float *vx, float *vy, float *vw, float *vh) {
    RValue zero = rv_real(0);
    double cam = fcall1(s, F_ViewGetCamera, zero);
    RValue camv = rv_real(cam);
    *vx = (float)fcall1(s, F_CameraGetViewX, camv); *vy = (float)fcall1(s, F_CameraGetViewY, camv);
    *vw = (float)fcall1(s, F_CameraGetViewWidth, camv); *vh = (float)fcall1(s, F_CameraGetViewHeight, camv);
    if (!(*vw > 16) || !(*vh > 16) || *vw > 8000 || *vh > 8000 || !finite_(*vx) || !finite_(*vy)) {
        *vw = 600; *vh = 300; *vx = sx_(s) - 300; *vy = sy_(s) - 200;       /* no camera: around us */
    }
}
/* where the Moon hangs in the sky over the battlefield (world space) */
static void mf_sky_moon_at(CInstance *s, float *mx, float *my, float *mr) {
    float vx, vy, vw, vh;
    mf_view(s, &vx, &vy, &vw, &vh);
    *mx = vx + vw * 0.64f; *my = vy + vh * 0.30f; *mr = vh * 0.26f;
}

static void lava_activate(CInstance *s, Grey *j);
static void special_step(CInstance *s, Grey *j, GPose *pose) {
    int t = ++j->sp_t;
    bset(s, &g_VAR_hspeed, 0); bset(s, &g_VAR_vspeed, 0);
    if (!j->hit_done) target_frozen(s, j, true);
    float x = sx_(s), y = sy_(s);
    /* Grey: reaching up to the sky (and holding it there), then the cool pose once it is done */
    if (t < MF_LAND) {
        base_pose(GPZ_CHARGE, pose);
        float reach = ease_io(lin01(t, 4, 22));
        pose->a[GA_UF] = -10 + (-78 + 10) * reach; pose->a[GA_LF] = -20 + (-96 + 20) * reach;
        pose->hy += sinf_(t * 0.7f) * 0.6f * (1 - reach);
        if (t % 7 == 0) j->glitch_t = 3;
        if (t % 2 == 0) part(j, PK_BIT, x + frand(-16, 16), y - frand(0, 50), 0, -1.4f, 30, 1, (t / 2) % 2 ? C_CYAN : C_MAG);
    } else base_pose(GPZ_POSE_COOL, pose);
    /* sound: huge things sound low, and space is nearly silent - the impact is a deep, slowed boom */
    if (t == 1) { play(s, SND_SUSPENSE, 0.8); play_c(s, GS_GLITCH, 0.6); }
    if (t == MF_RIFT) { play(s, SND_THUNDER, 0.55); play_c(s, GS_GLITCH, 0.45); }
    if (t == MF_MOON) { play(s, SND_MAGIC3, 0.5); play_c(s, GS_CRASH, 0.55); camera_shake(2); }
    if (t == MF_MOON + 20 || t == MF_MOON + 38) play(s, SND_THUNDER, 0.4);
    if (t == MF_ASC) play(s, SND_WOOSH3, 0.45);
    if (t == MF_FALL) play(s, SND_BALL_CHARGE, 0.45);
    if (t == MF_HIT) { play(s, SND_EXPLOSION_MEGA, 0.45); play(s, SND_DARKEXPLOSION, 0.4); }
    if (t == MF_HIT + 26) play(s, SND_WINLOSE_IMPACT, 0.55);
    if (t == MF_AFTER) play(s, SND_DARKEXPLOSION, 0.35);
    /* on the ground: the sky tears where the Moon will come through */
    float mx, my, mr;
    if (t >= MF_RIFT && t < MF_ASC) mf_sky_moon_at(s, &mx, &my, &mr);
    else mx = my = mr = 0;
    if (t >= MF_RIFT && t < MF_MOON + 6 && t % 2 == 0) {
        float h = mr * (0.3f + 1.4f * lin01(t, MF_RIFT, MF_MOON));
        float ry = my + frand(-h, h), rx = mx + frand(-0.2f, 0.2f) * mr;
        bolt(j, rx, ry - frand(10, 30), rx + frand(-mr * 0.3f, mr * 0.3f), ry + frand(10, 40), 5, 2.0f, (t / 2) % 4 ? C_CYAN : C_MAG);
    }
    /* the Moon is overhead, ten thousand km up: the tides it raises in the crust are kilometres high.
       The ground convulses - earthquakes, dust shaken up, rocks jumping */
    if (t >= MF_MOON && t < MF_ASC) {
        float vx, vy, vw, vh;
        mf_view(s, &vx, &vy, &vw, &vh);
        if (t % 9 == 0) camera_shake(t < MF_MOON + 20 ? 2 : 1);
        if (t % 3 == 0) {
            float gx = vx + frand(0, vw);
            part(j, PK_SMOKE, gx, y - 2, frand(-0.5f, 0.5f), -frand(0.3f, 0.9f), 46, frand(6, 10), RGB(126, 116, 108));
            Part *q = part(j, PK_SHARD, gx, y - 2, frand(-1.2f, 1.2f), -frand(2.5f, 5.0f), 34, frand(1.6f, 3.0f), RGB(96, 88, 82));
            if (q) q->g = 0.32f;
        }
    }
    /* space: the Roche stream - the near side of the broken Moon falls ahead of it, the far side lags */
    if (t >= MF_FALL - 20 && t < MF_HIT && t % 2 == 0) {
        V3 mv, c = mf_moon_c(t, &mv);
        V3 e = v3n(c);                                       /* from the Earth through the Moon */
        float u = lin01(t, MF_FALL - 20, MF_HIT);
        int n = 1 + (int)(u * 3);
        for (int k = 0; k < n; k++) {
            float side = (k % 2) ? 1.0f : -1.0f;               /* -1: the Earth-facing side */
            V3 off = v3s(v3s(v3k(e, side * MF_RM * 0.95f), MF_T1, frand(-0.08f, 0.08f)), MF_H, frand(-0.08f, 0.08f));
            V3 dv = v3k(e, side * frand(0.0008f, 0.0022f) * (1 + u));   /* tidal: near side inwards, far side out */
            gp_new(j, (rnd() % 3) ? GQ_DUST : GQ_ROCK, v3s(c, off, 1), v3s(mv, dv, 1), 150, frand(0.005f, 0.014f));
        }
    }
    /* the last seconds before contact: whole chunks break off the Earth-facing side (Roche fragments). They
       are nearer the planet, so they fall faster and strike first, splashing just ahead of the Moon */
    if (t >= MF_HIT - 26 && t < MF_HIT - 4 && t % 4 == 0) {
        V3 mv, c = mf_moon_c(t, &mv);
        V3 e = v3n(c);
        V3 off = v3s(v3s(v3k(e, -MF_RM * 0.92f), MF_T1, frand(-0.09f, 0.09f)), MF_H, frand(-0.07f, 0.07f));
        V3 dv = v3k(e, -frand(0.0025f, 0.0045f));
        gp_new(j, GQ_ROCK, v3s(c, off, 1), v3s(mv, dv, 1), 150, frand(0.034f, 0.058f));
    }
    if (t >= MF_HIT && t < MF_HIT + 50) {
        int k = t - MF_HIT, n = k < 14 ? 8 : 3;
        for (int i = 0; i < n; i++) {                         /* molten ejecta: a curtain, mostly downrange */
            V3 d = mf_cone(1.05f, 0.55f);
            float sp = (rnd() % 7 == 0) ? frand(0.036f, 0.047f) : frand(0.010f, 0.031f);   /* a few escape */
            V3 base = v3n(v3s(v3s(MF_N, MF_T1, frand(-0.12f, 0.12f)), MF_T2, frand(-0.12f, 0.12f)));
            gp_new(j, GQ_EJECTA, v3k(base, 1.01f), v3k(d, sp), 170 + (int)(rnd() % 90), frand(0.007f, 0.02f));
        }
        if (k > 6 && k % 2 == 0) {                            /* the Moon comes apart */
            V3 mv, c = mf_moon_c(t, &mv);
            V3 d = mf_cone(1.5f, 0.3f);
            float sp = frand(0.006f, 0.02f);
            gp_new(j, GQ_ROCK, v3s(c, d, MF_RM * 0.85f), v3s(v3k(mv, 0.4f), d, sp), 170, frand(0.016f, 0.036f));
        }
    }
    if (t >= MF_FALL - 20 && t < MF_LAND) gp_step(j, t);
    if (t == MF_FLASH) camera_shake(3);
    /* back on the ground: the world has burned, and the blow lands */
    if (t == MF_LAND && !j->hit_done) {
        j->hit_done = 1;
        target_frozen(s, j, false);
        lava_activate(s, j);
        CInstance *c = j->tgt_id >= 0 ? YYGML_FindInstance(j->tgt_id) : 0;
        float cx = c ? (float)sget(c, &g_VAR_x) : j->tgt_x, cy = c ? (float)sget(c, &g_VAR_y) : j->tgt_y;
        Hit h = { my_dmg(s) * 10.0, j->dir * 7.0, -12.0, 40, 6, 2.2, 2.2, SPR_MASK64, 1, 1, 0, 1, SPR_HIT_3, C_FIRE, 2 };
        spawn_hit(s, cx, cy - 28, &h);
        fx_kind(j, GF_FIREBURST, cx, cy - 20, 2.2f, j->dir);
        fx_at(j, GR_RING, cx, cy - 1, 1.4f, 1.4f, 0, 2, 1, C_FIRE);
        fx_at(j, GR_RING, cx, cy - 1, 2.6f, 2.6f, 0, 3, 1, RGB(255, 190, 90));
        fx_at(j, GR_STAR, cx, cy - 30, 2.6f, 2.6f, 0, 2, 1, C_WHITE);
        burst(j, PK_EMBER, cx, cy - 20, 40, 6.0f, 60, 3.0f, C_FIRE);
        burst(j, PK_SHARD, cx, cy - 10, 26, 7.0f, 50, 3.0f, RGB(120, 110, 100));
        burst(j, PK_SPARK, cx, cy - 20, 24, 9.0f, 16, 2.0f, RGB(255, 230, 170));
        for (int k = 0; k < 10; k++) part(j, PK_SMOKE, cx + frand(-40, 40), cy - frand(0, 30), frand(-1.2f, 1.2f), -frand(0.4f, 1.4f), 90, 14, RGB(60, 48, 42));
        mark(j, 0, cx, cy, 110, 400);
        camera_shake(3);
        play(s, SND_WINLOSE_IMPACT, 0.9); play(s, SND_STRONG2, 0.6); play(s, SND_EXPLOSION_MEGA, 0.75);
        play_c(s, GS_CRASH, 0.7);
    }
    if (t > MF_LAND && t < MF_LAND + 64 && t % 5 == 0) {      /* the Moon's fragments still raining down, burning */
        float mx2 = j->tgt_x + frand(-260, 260), my2 = y - frand(180, 240), sp = frand(5, 8), ang = frand(1.25f, 1.6f);
        for (int k = 0; k < 6; k++)
            part(j, PK_STREAK, mx2 + cosf_(ang) * k * 6, my2 + sinf_(ang) * k * 6, cosf_(ang) * sp, sinf_(ang) * sp, 34, 2.2f, k ? C_FIRE : RGB(255, 235, 190));
        if (t % 10 == 0) {
            float gx = j->tgt_x + frand(-200, 200);
            fx_kind(j, GF_FIREBURST, gx, y - 10, 0.9f, j->dir);
            burst(j, PK_EMBER, gx, y - 6, 10, 3.0f, 40, 2.4f, C_FIRE);
        }
    }
    if (t >= SPC_DUR) {
        special_end(s, j);
        bset(s, &g_VAR_image_speed, 0.25);
        bset_i(s, &g_VAR_alarm, 2, 1);
    }
}

/* ------------------------------------------------------------------------------------------ */
/* MOONFALL, drawn                                                                              */
/* ------------------------------------------------------------------------------------------ */
static int bb_col(float T) {                         /* blackbody: dull red -> orange -> yellow -> white-hot */
    static const float st[7] = { 0.0f, 0.25f, 0.55f, 0.9f, 1.3f, 1.8f, 2.4f };
    static const unsigned char c[7][3] = { { 0, 0, 0 }, { 110, 10, 0 }, { 200, 45, 5 }, { 255, 110, 20 },
                                           { 255, 175, 70 }, { 255, 225, 150 }, { 255, 250, 235 } };
    if (!(T > 0)) return 0;
    if (T >= st[6]) return RGB(c[6][0], c[6][1], c[6][2]);
    int i = 0;
    while (i < 5 && T >= st[i + 1]) i++;
    float u = (T - st[i]) / (st[i + 1] - st[i]);
    int r = (int)(c[i][0] + (c[i + 1][0] - c[i][0]) * u), g = (int)(c[i][1] + (c[i + 1][1] - c[i][1]) * u);
    int b = (int)(c[i][2] + (c[i + 1][2] - c[i][2]) * u);
    return RGB(r, g, b);
}
static void rect(float x0, float y0, float x1, float y1, int col, float a) {
    if (a <= 0.003f) return;
    YYGML_draw_set_colour(col);
    YYGML_draw_set_alpha(a > 1 ? 1 : a);
    YYGML_draw_rectangle(x0, y0, x1, y1, false);
}
static void stretched(CInstance *s, int a, float img, float x, float y, float w, float h, int col, float alpha) {
    if (a < 0 || a >= GR_COUNT || g_grey_spr[a] < 0 || alpha <= 0.003f) return;
    if (!finite_(x) || !finite_(y) || !finite_(w) || !finite_(h)) return;
    RValue r = rv_undef();
    RValue v[8] = { rv_real(g_grey_spr[a]), rv_real(img), rv_real(x), rv_real(y), rv_real(w), rv_real(h), rv_real(col),
                    rv_real(alpha > 1 ? 1 : alpha) };
    F_DrawSpriteStretchedExt(&r, s, s, 8, v);
    rv_free(&r);
}
/* a soft streak: the glow sprite stretched along a motion (a camera shutter's blur) */
static void glow_streak(CInstance *s, float x0, float y0, float x1, float y1, float w, int col, float a) {
    float dx = x1 - x0, dy = y1 - y0, len = sqrtf_(dx * dx + dy * dy);
    if (len < w) { spr(s, GR_GLOW, 0, x1, y1, w / 32.0f, w / 32.0f, 0, col, a); return; }
    spr(s, GR_GLOW, 0, (x0 + x1) * 0.5f, (y0 + y1) * 0.5f, (len + w) / 32.0f, w / 32.0f, -atan2f_(dy, dx) * 57.29578f, col, a);
}

/* the space camera: on the +z axis looking at the Earth (so the pre-lit sprites stay true), dollying out.
   Keyframed by what the eye sees: the Earth's apparent radius R (GUI heights, log-interpolated = a steady
   zoom), where its centre sits across the screen and how high its top edge is. Cubic Hermite through the
   keys with time-aware tangents: the camera never stops dead between shots. */
typedef struct { float F, D, ox, oy, R; } MCam;
typedef struct { short t; float lnR, cx, ytop; } MKey;      /* lnR: log of the apparent radius (GUI heights) */
static const MKey MF_KEYS[] = {
    { MF_ASC + 8, 1.386294f, 0.50f, 1.10f },  /* R 4.0: the limb, still below the frame as we climb */
    { MF_SPACE, 1.163151f, 0.50f, 0.70f },    /* R 3.2: clear of the atmosphere: the horizon */
    { 136, 0.048790f, 0.47f, 0.52f },         /* R 1.05: pulling back: the curve of the planet */
    { MF_FALL, -1.203973f, 0.40f, 0.32f },    /* R 0.3: the whole system: the Moon swinging in from the right */
    { MF_HIT, -0.776529f, 0.34f, 0.24f },     /* R 0.46: pushing in for contact */
    { MF_HOLD, -0.733969f, 0.335f, 0.235f },  /* R 0.48: holding on the impact, still creeping in */
    { MF_AFTER, -1.021651f, 0.40f, 0.26f },   /* R 0.36 */
    { MF_FLASH, -1.309333f, 0.46f, 0.29f },   /* R 0.27: back off: the debris disc */
};
#define MF_NKEY ((int)(sizeof(MF_KEYS) / sizeof(MF_KEYS[0])))
static float mf_key(int i, int ch) {
    const MKey *k = &MF_KEYS[i];
    return ch == 0 ? k->lnR : ch == 1 ? k->cx : k->ytop;
}
static float mf_channel(float t, int ch) {
    if (t <= MF_KEYS[0].t) return mf_key(0, ch);
    if (t >= MF_KEYS[MF_NKEY - 1].t) return mf_key(MF_NKEY - 1, ch);
    int i = 0;
    while (i < MF_NKEY - 2 && t > MF_KEYS[i + 1].t) i++;
    float t0 = MF_KEYS[i].t, t1 = MF_KEYS[i + 1].t, h = t1 - t0, u = (t - t0) / h;
    float p0 = mf_key(i, ch), p1 = mf_key(i + 1, ch);
    float m0 = i > 0 ? (p1 - mf_key(i - 1, ch)) / (t1 - MF_KEYS[i - 1].t) : 0;
    float m1 = i + 2 < MF_NKEY ? (mf_key(i + 2, ch) - p0) / (MF_KEYS[i + 2].t - t0) : 0;
    float u2 = u * u, u3 = u2 * u;
    return (2 * u3 - 3 * u2 + 1) * p0 + (u3 - 2 * u2 + u) * h * m0 + (-2 * u3 + 3 * u2) * p1 + (u3 - u2) * h * m1;
}
static void mf_cam(float t, float gw, float gh, MCam *c) {
    float R = expf_(mf_channel(t, 0));
    if (R < 0.05f) R = 0.05f;
    c->F = MF_F * gh;
    c->R = R * gh;
    c->D = sqrtf_(1 + (MF_F / R) * (MF_F / R));              /* the distance at which the Earth looks that big */
    c->ox = mf_channel(t, 1) * gw;
    c->oy = (mf_channel(t, 2) + R) * gh;
}
static int mf_proj(const MCam *c, V3 p, float *sx, float *sy, float *k) {
    float d = c->D - p.z;
    if (d < 0.08f) return 0;
    *k = c->F / d; *sx = c->ox + p.x * *k; *sy = c->oy + p.y * *k;
    return finite_(*sx) && finite_(*sy);
}
static int mf_hidden(const MCam *c, V3 p) {          /* behind the Earth? (the ray from the camera meets it first) */
    V3 d = v3(p.x, p.y, p.z - c->D);
    float a = v3dot(d, d), b = 2 * c->D * d.z, cc = c->D * c->D - 1;
    float disc = b * b - 4 * a * cc;
    if (disc <= 0 || a < 1e-9f) return 0;
    float t1 = (-b - sqrtf_(disc)) / (2 * a);
    return t1 > 0 && t1 < 0.999f;
}

/* the planet: the day side until contact, then the melt sweeping over it (two frames cross-faded) */
static void mf_draw_earth(CInstance *s, const MCam *c, int t, float alpha) {
    float sc = c->R / 236.0f;                                 /* EARTH_R in the 512 px renders */
    float top_a = clampf((c->R / c->F * MF_F - 1.35f) / 0.4f, 0, 1);   /* the detailed horizon crop up close */
    if (top_a < 1) {
        float th = mf_melt(t);
        if (th <= 0) spr(s, GR_EARTH, 0, c->ox, c->oy, sc, sc, 0, C_WHITE, alpha);
        else {
            int k = 0;
            while (k < MELT_N - 1 && th >= MELT_TH[k + 1]) k++;
            if (th < MELT_TH[0]) {
                spr(s, GR_EARTH, 0, c->ox, c->oy, sc, sc, 0, C_WHITE, alpha);
                spr(s, GR_EARTH_MELT, 0, c->ox, c->oy, sc, sc, 0, C_WHITE, alpha * th / MELT_TH[0]);
            } else {
                spr(s, GR_EARTH_MELT, (float)k, c->ox, c->oy, sc, sc, 0, C_WHITE, alpha);
                if (k < MELT_N - 1)
                    spr(s, GR_EARTH_MELT, (float)(k + 1), c->ox, c->oy, sc, sc, 0, C_WHITE,
                        alpha * (th - MELT_TH[k]) / (MELT_TH[k + 1] - MELT_TH[k]));
            }
        }
    }
    if (top_a > 0) {
        float k = c->R / 1024.0f;                             /* TOP_R */
        spr(s, GR_EARTH_TOP, 0, c->ox, c->oy, k, k, 0, C_WHITE, alpha * top_a);
    }
}
/* the Moon: tidally stretched toward the Earth as it falls inside the Roche limit, cracking, then
   flattening and sinking as it ploughs in, its underside glowing */
static void mf_draw_moon(CInstance *s, const MCam *c, int t, int glow_pass) {   /* glow_pass: the caller set additive */
    if (t < MF_MOON || t > MF_HIT + 90) return;
    V3 p = mf_moon_c(t, 0);
    float sx, sy, k;
    if (!mf_proj(c, p, &sx, &sy, &k)) return;
    float rpx = MF_RM * k;
    if (sx < -rpx * 2 || sx > c->ox * 4 + 4000 || rpx < 0.5f) return;
    float r = v3len(p), pen = mf_pen(t), pu = pen / 0.52f;
    float tide = 1 + 0.25f * (1.4f / r) * (1.4f / r) * (1.4f / r);   /* tidal elongation ~ 1/r^3 */
    if (tide > 1.4f) tide = 1.4f;
    float a = tide, b = 1 / sqrtf_(tide);                    /* a prolate spheroid, volume kept */
    V3 e = v3n(p);
    float sin2 = 1 - e.z * e.z;                               /* its axis, foreshortened */
    float along = sqrtf_(a * a * sin2 + b * b * (1 - sin2)), across = b;
    along *= 1 - 0.55f * pu; across *= 1 + 0.3f * pu;          /* ploughing in: it flattens and spreads */
    float sc = rpx / 124.0f;                                  /* MOON_R */
    float al = 1 - ease_io(lin01f(pen, 0.18f, 0.48f));
    float crack = ease_io(lin01f(2.2f - r, 0, 0.6f));         /* breaking up deep inside the Roche limit */
    const int lunar = RGB(178, 172, 166);                     /* the Moon is darker than the Earth */
    float ex = -cosf_(MF_ROT * DEG), ey = sinf_(MF_ROT * DEG);   /* screen direction towards the Earth */
    float cx = sx + ex * rpx * (1 - along), cy = sy + ey * rpx * (1 - along);   /* the far side stays put */
    if (!glow_pass) {
        spr(s, GR_MOON_BIG, 0, cx, cy, sc * along, sc * across, MF_ROT, lunar, al * (1 - crack));
        if (crack > 0) spr(s, GR_MOON_BIG, 1, cx, cy, sc * along, sc * across, MF_ROT, lunar, al);
    } else if (t >= MF_HIT - 3) {                             /* lit from below by the impact (additive pass) */
        float hot = clampf(1 - (float)(t - MF_HIT) / 80.0f, 0, 1) * (t < MF_HIT ? 0.4f : 1);
        spr(s, GR_GLOW, 0, cx + ex * rpx * 0.75f, cy + ey * rpx * 0.75f, rpx * 2.6f / 32.0f, rpx * 1.6f / 32.0f, MF_ROT,
            RGB(255, 150, 60), 0.85f * hot * (0.4f + 0.6f * al));
    }
}
/* the melt textures' front is ragged (fBm noise on the globe, art/grey/moonfall.py): how far behind the
   circle of radius th it runs at ring vertex i, from the table moonfall.py exports (radians) */
static float mf_front_lag(float th, int i) {
    float f = th / MF_FRONT_STEP;
    if (!(f > 0)) return 0;
    if (f >= MF_FRONT_TH - 1) f = MF_FRONT_TH - 1.001f;
    int a = (int)f;
    float u = f - a;
    return (k_mf_front[a][i] * (1 - u) + k_mf_front[a + 1][i] * u) * 0.001f;
}
static void mf_draw_ring_on_globe(CInstance *s, const MCam *c, float th, float w, int col, float a, int ragged) {
    if (th <= 0.01f || th >= 3.1f || a <= 0.01f) return;
    float px = 0, py = 0;
    int have = 0;
    for (int i = 0; i <= 64; i++) {
        float ph = i * (6.2832f / 64), r = ragged ? th - mf_front_lag(th, i) : th;
        if (r < 0.005f) r = 0.005f;
        float ct = cosf_(r), st = sinf_(r);
        V3 q = v3s(v3k(MF_N, ct), v3s(v3k(MF_T1, cosf_(ph)), MF_T2, sinf_(ph)), st);
        float x = 0, y = 0, k;
        int vis = q.z > 1 / c->D + 0.02f && mf_proj(c, q, &x, &y, &k);   /* on the near side */
        if (vis && have) {
            float lim = q.z < 0.3f ? q.z / 0.3f : 1;               /* fading towards the limb */
            seg(s, px, py, x, y, w, col, a * lim);
        }
        px = x; py = y; have = vis;
    }
}
/* airglow: once the melt front reaches the limb, the atmosphere over it glows orange - a thin band just
   outside the planet's edge, over the arc of the limb that has melted (the textures' halo test: the
   angle between the limb direction and the impact's direction on screen, = moonfall.py hot_rim) */
static void mf_draw_airglow(CInstance *s, const MCam *c, float th, float gh) {
    if (th < 0.9f) return;
    float n2 = sqrtf_(MF_N.x * MF_N.x + MF_N.y * MF_N.y), nx = MF_N.x / n2, ny = MF_N.y / n2;
    float rise = clampf((th - 0.9f) / 0.8f, 0, 1);
    /* soft glows laid along the limb, each twice as long as the gap between them, so additively they sum to
       an even band (line segments would double up at every joint) */
    float rr = c->R * 1.02f, across = (c->R * 0.05f + gh * 0.004f) / 32.0f, along = (c->R * 6.2832f / 48 * 2.2f) / 32.0f;
    for (int i = 0; i < 48; i++) {
        float ph = (i + 0.5f) * (6.2832f / 48), dx = cosf_(ph), dy = sinf_(ph);
        float cosang = clampf(dx * nx + dy * ny, -1, 1);
        float ang = atan2f_(sqrtf_(1 - cosang * cosang), cosang);   /* along the limb from the impact side */
        float edge = clampf((th - 0.55f - ang) / 0.35f, 0, 1); /* the melted arc, with soft ends */
        float al = 0.26f * rise * edge;
        if (al < 0.004f) continue;
        /* tangent direction on screen: GameMaker angles are counter-clockwise with y down */
        spr(s, GR_GLOW, 0, c->ox + dx * rr, c->oy + dy * rr, along, across, -atan2f_(dx, -dy) * 57.29578f,
            RGB(255, 120, 40), al);
    }
}
/* the debris disc: what the impact threw into orbit, spreading round the planet from the impact side and
   shearing out (inner orbits faster: Kepler) */
static void mf_draw_disc(CInstance *s, const MCam *c, int t, int front) {
    if (t < MF_HIT + 20) return;
    float age = (float)(t - MF_HIT - 20);
    float spread = clampf(age / 60.0f, 0, 1) * 6.2832f;
    float fade = ease_io(age / 36.0f);
    for (int pass = 0; pass < 2; pass++) {                   /* lit dust, then the clumps still glowing */
        blend(s, pass);
        for (int i = 0; i < 300; i++) {
            unsigned hsh = (unsigned)i * 2654435761u;
            int hot = (hsh >> 7) % 3 == 0;                     /* still glowing from the impact */
            if (hot != pass) continue;
            float f0 = (float)(hsh & 1023) / 1023.0f, f1 = (float)((hsh >> 10) & 1023) / 1023.0f, f2 = (float)((hsh >> 20) & 1023) / 1023.0f;
            float r = 1.7f + 0.55f * f0 * f0;
            float ph0 = f1 * 6.2832f;
            if (ph0 > spread) continue;
            float w = sqrtf_(MF_GM / (r * r * r));             /* Kepler angular speed (rad/frame) */
            float ph = ph0 + w * age;
            V3 q = v3s(v3s(v3k(MF_N, r * cosf_(ph)), MF_TO, r * sinf_(ph)), MF_H, (f2 - 0.5f) * 0.05f);
            if ((q.z > 0) != front) continue;
            float x, y, k;
            if (mf_hidden(c, q) || !mf_proj(c, q, &x, &y, &k)) continue;
            float sz = (0.016f + 0.026f * f2) * k;
            if (sz < 1.5f) sz = 1.5f;
            if (hot) spr(s, GR_GLOW, 0, x, y, sz * 2.6f / 32.0f, sz * 2.6f / 32.0f, 0, bb_col(1.25f - age / 220.0f), 0.8f * fade);
            else spr(s, GR_GLOW, 0, x, y, sz * 1.8f / 32.0f, sz * 1.8f / 32.0f, 0, RGB(190, 160, 130), 0.7f * fade);
        }
    }
    blend(s, 0);
}
/* passes p0..p1-1 of: 0 dust, 1 rocks (lit), 2 everything glowing (additive: the caller sets the blend mode,
   so the glowing pass shares one additive block with the other glows of the shot) */
static void mf_draw_gp(CInstance *s, Grey *j, const MCam *c, int t, int p0, int p1) {
    for (int pass = p0; pass < p1; pass++) {
        for (int i = 0; i < N_GP; i++) {
            GPt *q = &j->gp[i];
            if (!q->on) continue;
            V3 p = v3(q->x, q->y, q->z);
            if (mf_hidden(c, p)) continue;
            float x, y, k;
            if (!mf_proj(c, p, &x, &y, &k)) continue;
            float sz = q->size * k, life = (float)q->t / q->life;
            if (pass == 0 && q->kind == GQ_DUST) {
                if (sz < 1.0f) sz = 1.0f;
                spr(s, GR_GLOW, 0, x, y, sz * 2 / 32.0f, sz * 2 / 32.0f, 0, RGB(150, 138, 126), 0.5f * (1 - life));
            } else if (pass == 1 && q->kind == GQ_ROCK) {
                float rs = sz * 2 / 20.0f;
                if (rs < 0.06f) rs = 0.06f;
                spr(s, GR_ROCKS, (float)q->frame, x, y, rs, rs, 0, C_WHITE, 1 - life * life);
            } else if (pass == 2 && (q->kind == GQ_EJECTA || q->kind == GQ_SPLASH || (q->kind == GQ_ROCK && q->t < 60 && t > MF_HIT))) {
                if (q->kind == GQ_SPLASH) {
                    float g = sz * (0.6f + 2.4f * life);
                    spr(s, GR_GLOW, 0, x, y, g / 32.0f, g / 32.0f, 0, bb_col(2.0f - 1.6f * life), 0.9f * (1 - life));
                } else if (q->kind == GQ_ROCK) {
                    spr(s, GR_GLOW, 0, x, y, sz * 3 / 32.0f, sz * 3 / 32.0f, 0, RGB(255, 110, 30), 0.5f * (1 - q->t / 60.0f));
                } else {
                    float T = 1.95f * expf_(-q->t / 70.0f) + 0.25f;   /* cooling as it flies */
                    if (sz < 1.2f) sz = 1.2f;
                    float x0, y0, k0;                                 /* where it was 2 frames ago: the blur */
                    V3 pp = v3(q->x - q->vx * 2.5f, q->y - q->vy * 2.5f, q->z - q->vz * 2.5f);
                    if (!mf_proj(c, pp, &x0, &y0, &k0)) { x0 = x; y0 = y; }
                    glow_streak(s, x0, y0, x, y, sz * 2.6f, bb_col(T), clampf(T * 0.6f, 0.15f, 0.95f) * (1 - life * life));
                }
            }
        }
    }
}

/* the whole space shot, on the GUI layer */
static void mf_draw_space(CInstance *s, Grey *j, float gw, float gh) {
    int t = j->sp_t;
    MCam c;
    float shake = t >= MF_HIT && t < MF_HIT + 40 ? gh * 0.008f * (1 - (t - MF_HIT) / 40.0f) : 0;
    mf_cam((float)t, gw, gh, &c);
    if (shake > 0) { c.ox += frand(-shake, shake); c.oy += frand(-shake, shake); }
    float cover = ease_io(lin01(t, MF_ASC, MF_ASC + 12));      /* the world drops away below us */
    float alt = lin01(t, MF_ASC, MF_SPACE + 4);
    /* the sky as we climb: blue, then indigo, then black - brightest towards the horizon below */
    for (int b = 0; b < 32; b++) {
        float f0 = b / 32.0f, f1 = (b + 1) / 32.0f, f = (f0 + f1) * 0.5f;
        float dark = ease_io(clampf(alt * 1.6f - f * f * 0.7f, 0, 1));
        int r = (int)((105 + 80 * f) * (1 - dark) + 2 * dark), g = (int)((150 + 60 * f) * (1 - dark) + 3 * dark);
        int bl = (int)((225 + 25 * f) * (1 - dark) + 8 * dark);
        rect(0, gh * f0, gw, gh * f1 + 1, RGB(r, g, bl), cover);
    }
    stretched(s, GR_STARS, 0, 0, 0, gw, gh, C_WHITE, cover * ease_io(lin01f(alt, 0.45f, 1.0f)));
    if (alt < 1 && t < MF_SPACE) {                           /* the air rushing past: cloud, then thin haze */
        blend(s, 1);
        /* the camera rolls a little as it climbs, so the streaks lean and bend (they are the paths of the air
           past a turning lens: the lateral offset grows along each streak) */
        float roll = 0.20f * sinf_((t - MF_ASC) * 0.11f + 0.6f), L = gh * 0.22f;
        for (int i = 0; i < 16; i++) {
            float px = (float)((i * 389 + 61) % 1000) / 1000.0f * gw;
            float py = (float)(((t - MF_ASC) * (24 + (i % 5) * 9) + i * 211) % (int)(gh * 1.6f)) - gh * 0.3f;
            float lean = roll * (0.8f + 0.4f * ((px / gw) - 0.5f));   /* the far side of the frame turns more */
            float xm = px + lean * L * 0.5f + lean * L * 0.12f, xe = px + lean * L + lean * L * 0.48f;
            float a = 0.22f * (1 - alt) * cover;
            seg(s, px, py, xm, py + L * 0.5f, 1.4f, C_WHITE, a);
            seg(s, xm, py + L * 0.5f, xe, py + L, 1.4f, C_WHITE, a * 0.8f);
        }
        blend(s, 0);
        float deck = 1 - fabsf_((float)(t - MF_ASC - 6) / 4.0f);      /* through the cloud deck */
        if (deck > 0) rect(0, 0, gw, gh, RGB(238, 242, 248), 0.85f * deck * deck);
    }
    if (t < MF_ASC + 8) return;
    /* the bodies. Blend modes are batched: every additive glow of one layer goes into one block, so the
       shot switches blend mode only a handful of times per frame (each switch flushes the sprite batch). */
    mf_draw_disc(s, &c, t, 0);                                /* the far half of the debris disc */
    mf_draw_earth(s, &c, t, 1);
    float th = mf_melt(t);
    float x = 0, y = 0, E = 0;                                /* the impact point on screen; E: px per Earth radius */
    int k = t - MF_HIT, contact = t >= MF_HIT - 1 && mf_proj(&c, MF_N, &x, &y, &E);
    float heat = clampf(1 - k / 110.0f, 0, 1);
    if (th > 0 || contact) {
        blend(s, 1);                                          /* -- additive: the planet's own light -- */
        if (contact)                                          /* the ground glowing at the impact, under the plume */
            spr(s, GR_GLOW, 0, x, y, E * 0.75f / 32.0f, E * 0.75f / 32.0f, 0, bb_col(0.8f + 1.6f * heat), 0.65f * heat);
    }
    if (th > 0) {
        float hot = clampf(th / 2.5f, 0, 1);                  /* the hot side lights the atmosphere orange */
        spr(s, GR_GLOW, 0, c.ox, c.oy, c.R * 2.9f / 32.0f, c.R * 2.9f / 32.0f, 0, RGB(255, 110, 30), 0.22f * hot);
        mf_draw_airglow(s, &c, th, gh);                       /* the limb glowing where the melt has reached it */
        /* the shock front (following the ragged melt front of the textures), and the air blast ahead of it */
        mf_draw_ring_on_globe(s, &c, th, gh * 0.0015f + c.R * 0.004f, RGB(255, 215, 150), 0.45f * (1 - th / 3.6f), 1);
        if (th > 0.2f && th < 2.4f)                           /* the air blast, racing ahead through the clouds */
            mf_draw_ring_on_globe(s, &c, th * 1.12f + 0.08f, gh * 0.0015f + c.R * 0.003f, RGB(205, 225, 255), 0.16f * (1 - th / 2.4f), 0);
    }
    blend(s, 0);                                              /* -- normal: the Moon, its debris, the plume -- */
    mf_draw_moon(s, &c, t, 0);
    mf_draw_gp(s, j, &c, t, 0, 2);
    /* contact: the jetting flash - vaporised rock squirting out of the contact ring at many km/s - then the
       plume of rock vapour rising and cooling, white-hot to orange to smoke */
    int pfr = 0; float psc = 0, pfade = 0, fore = sqrtf_(1 - MF_N.z * MF_N.z);   /* a dome along MF_N, at an angle */
    if (contact && k >= 1 && k < 120) {
        float u = (k - 1) / 84.0f;
        pfr = (int)(u * 9.99f); if (pfr > 9) pfr = 9;
        psc = E * 1.25f / 170.0f;                             /* the vapour plume rises ~1.25 Earth radii */
        pfade = k < 88 ? 1 : 1 - (k - 88) / 32.0f;
        spr(s, GR_PLUME, (float)pfr, x, y, psc, psc * fore, MF_ROT - 90, C_WHITE, pfade);
    }
    blend(s, 1);                                              /* -- additive: everything that burns -- */
    mf_draw_moon(s, &c, t, 1);                                /* the Moon's underside, lit by the impact */
    mf_draw_gp(s, j, &c, t, 2, 3);                            /* molten ejecta, splashes, glowing fragments */
    if (contact) {
        if (k < 10) {
            float u = k / 10.0f, f2 = (1 - u) * (1 - u);
            spr(s, GR_GLOW, 0, x, y, E * (0.35f + 0.9f * u) / 32.0f, E * (0.35f + 0.9f * u) / 32.0f, 0, RGB(255, 252, 245), f2);
        }
        if (pfade > 0)
            spr(s, GR_PLUME, (float)pfr, x, y, psc, psc * fore, MF_ROT - 90, RGB(255, 150, 70), 0.18f * pfade * heat);
    }
    blend(s, 0);
    mf_draw_disc(s, &c, t, 1);                                /* the near half */
}
/* on the ground, before the climb: the sky tears and the Moon is in it, huge (world space, in Draw) */
static void mf_draw_sky(CInstance *s, Grey *j) {
    int t = j->sp_t;
    if (t < MF_RIFT || t >= MF_ASC + 14) return;
    float mx, my, mr;
    mf_sky_moon_at(s, &mx, &my, &mr);
    float sc = mr / 124.0f;
    if (t < MF_MOON + 6) {                                    /* the rift: a glitching tear in the sky */
        float u = lin01(t, MF_RIFT, MF_MOON), h = mr * (0.25f + 1.3f * u);
        blend(s, 1);
        for (int k = 0; k < 7; k++) {
            float yy = my - h + (2 * h) * (k + 0.5f) / 7.0f, w = mr * (0.05f + 0.25f * u) * (1 - fabsf_((yy - my) / h));
            spr(s, GR_SHAPE, 0, mx + frand(-3, 3), yy, (w + 2) / 32.0f, (2 * h / 7.0f) / 32.0f, 0, k % 2 ? C_CYAN : C_MAG, 0.5f);
        }
        spr(s, GR_GLOW, 0, mx, my, mr * 0.9f * u / 32.0f, h / 32.0f, 0, RGB(180, 220, 255), 0.6f * u);
        blend(s, 0);
        for (int k = 0; k < 3; k++)
            spr(s, GR_GLITCH, (float)((t + k * 3) % 8), mx + frand(-mr * 0.2f, mr * 0.2f), my + frand(-h, h), 0.6f + u, 0.6f + u, 0, C_WHITE, 0.9f);
    }
    if (t < MF_MOON) return;
    int age = t - MF_MOON;
    /* seen through the daytime sky: the air in front of it scatters blue light over it, so it is never
       quite opaque - its dark limb shows the sky (alpha), and it sits a little bluer than in space */
    float al = 0.9f;
    if (age < 14) {                                           /* glitching in */
        float u = age / 14.0f;
        float jx = (age % 3 == 0) ? frand(-mr * 0.1f, mr * 0.1f) : 0;
        blend(s, 1);
        spr(s, GR_MOON_BIG, 0, mx - mr * 0.12f * (1 - u), my, sc, sc, MF_ROT, C_CYAN, 0.7f * (1 - u));
        spr(s, GR_MOON_BIG, 0, mx + mr * 0.12f * (1 - u), my, sc, sc, MF_ROT, C_MAG, 0.7f * (1 - u));
        blend(s, 0);
        spr(s, GR_MOON_BIG, 0, mx + jx, my, sc, sc, MF_ROT, RGB(225, 235, 255), al * (age % 4 == 1 ? 0.3f : u));
        for (int k = 0; k < 2; k++)
            spr(s, GR_GLITCH, (float)((age + k * 4) % 8), mx + frand(-mr, mr), my + frand(-mr, mr), 1.4f, 1.4f, 0, C_WHITE, 1 - u);
    } else {
        float fade = 1 - lin01(t, MF_ASC + 4, MF_ASC + 14);
        spr(s, GR_MOON_BIG, 0, mx, my, sc, sc, MF_ROT, RGB(225, 235, 255), al * fade);
    }
}

/* ------------------------------------------------------------------------------------------ */
/* INFERNO ARROW                                                                               */
/*   In the bow stance, shield + skill: fire gathers at his bow hand, then a close-up - a giant  */
/*   bow of fire forms in his hand, embers peeling off it, and he draws it to the cheek while   */
/*   the flame at the arrowhead swells. Release: a burst at the nock, the camera whips after the */
/*   arrow through white speed rings; it streaks low over the plain, strikes - a yellow flash   */
/*   with ink focus lines - and from straight above the crater rips open and rocks fly at the   */
/*   camera. White-out: a black spike of earth thrown up. A mushroom cloud rises over the plain, */
/*   then back down to the fight, and one huge unblockable blow lands.                          */
/* ------------------------------------------------------------------------------------------ */
#define INK_C RGB(24, 16, 14)
static float fmodf_(float a, float m) {              /* a mod m, in [0, m) */
    if (!(m > 0) || !finite_(a)) return 0;
    float r = a - m * (float)(int)(a / m);
    return r < 0 ? r + m : r;
}
static unsigned hsh(unsigned i) { i ^= i >> 16; i *= 0x7feb352du; i ^= i >> 15; i *= 0x846ca68bu; i ^= i >> 16; return i; }
static float h01(unsigned i) { return (float)(hsh(i) & 0xffff) / 65535.0f; }

/* Grey's pose through the cinematic, from the frame alone (the close-up must not lag behind a cross-fade) */
static void ia_pose(int t, GPose *p) {
    GPose a, b;
    if (t < IA_CUT) { base_pose(GPZ_STAND, &a); base_pose(GPZ_BOW_AIM, &b); lerp_pose(&a, &b, ease_io(lin01(t, 2, 20)), p); }
    else if (t < IA_LOOSE) {
        base_pose(GPZ_BOW_AIM, &a); base_pose(GPZ_BOW_DRAW, &b);
        lerp_pose(&a, &b, ease(2, lin01(t, IA_CUT + 22, IA_LOOSE - 20)), p);   /* the draw: slow, heavy, then held */
    } else if (t < IA_LAND) {
        base_pose(GPZ_BOW_DRAW, &a); base_pose(GPZ_BOW_LOOSE, &b);
        lerp_pose(&a, &b, ease(6, lin01(t, IA_LOOSE, IA_LOOSE + 5)), p);       /* the string hand flies back */
    } else { base_pose(GPZ_BOW_LOOSE, &a); base_pose(GPZ_POSE_COOL, &b); lerp_pose(&a, &b, ease_io(lin01(t, IA_LAND, IA_LAND + 22)), p); }
    p->flags = (p->flags & 1) | (GW_BOW << 2);
    p->a[GA_W] = -90;
}

static void ia_step(CInstance *s, Grey *j, GPose *pose) {
    int t = ++j->sp_t;
    bset(s, &g_VAR_hspeed, 0); bset(s, &g_VAR_vspeed, 0);
    if (!j->hit_done) target_frozen(s, j, true);
    float x = sx_(s), y = sy_(s), f = j->dir;
    ia_pose(t, pose);
    if (t < IA_CUT) {                                         /* fire spiralling into his bow hand */
        V2 J[12]; fk(pose, x, y, f, J);
        if (j->cust) { J[7].x = x + f * 8; J[7].y = y - 26; }
        float c = lin01(t, 0, IA_CUT);
        for (int k = 0; k < 2; k++) {
            float a = frand(0, 6.2832f), r = 26 + frand(0, 18) * (1 - c);
            Part *q = part(j, PK_EMBER, J[7].x + cosf_(a) * r, J[7].y + sinf_(a) * r * 0.7f, -cosf_(a) * r / 10, -sinf_(a) * r / 14,
                           11, frand(1.8f, 3.2f), (rnd() & 1) ? C_FIRE : RGB(255, 214, 120));
            if (q) { q->g = 0; q->drag = 1; }
        }
        if (t % 6 == 0) j->glitch_t = 2;
    }
    /* sound: the bow catching fire, the draw creaking with heat, the release, the strike, the cloud */
    if (t == 2) { play(s, SND_MAGIC3, 0.9); play_c(s, GS_GLITCH, 0.9); }
    if (t == IA_CUT) { play(s, SND_BALL_CHARGE, 0.7); play(s, SND_THUNDER, 1.3); }
    if (t == IA_CUT + 40) play(s, SND_BALL_CHARGE, 0.9);
    if (t == IA_LOOSE) { play(s, SND_WOOSH3, 0.7); play(s, SND_STRONG2, 0.8); camera_shake(2); }
    if (t == IA_FLY + 2) play(s, SND_WOOSH3, 0.55);
    if (t == IA_FLASH) { play(s, SND_EXPLOSION_MEGA, 0.55); play(s, SND_DARKEXPLOSION, 0.5); camera_shake(3); }
    if (t == IA_TOP + 8) play(s, SND_WINLOSE_IMPACT, 0.6);
    if (t == IA_SPIKE) play(s, SND_EXPLOSION_MEGA, 0.4);
    if (t == IA_CLOUD + 6) play(s, SND_DARKEXPLOSION, 0.35);
    if (t == IA_LAND && !j->hit_done) {                      /* back down: the arrow's blow lands */
        j->hit_done = 1;
        target_frozen(s, j, false);
        CInstance *c = j->tgt_id >= 0 ? YYGML_FindInstance(j->tgt_id) : 0;
        float cx = c ? (float)sget(c, &g_VAR_x) : j->tgt_x, cy = c ? (float)sget(c, &g_VAR_y) : j->tgt_y;
        j->tgt_x = cx; j->tgt_y = cy;
        Hit h = { my_dmg(s) * 9.0, f * 9.0, -11.0, 40, 6, 2.2, 2.2, SPR_MASK64, 1, 1, 0, 1, SPR_HIT_3, C_FIRE, 2 };
        spawn_hit(s, cx, cy - 28, &h);                        /* unblockable (defend 0), knocks down, hits the fallen */
        fx_kind(j, GF_FIREBURST, cx, cy - 20, 2.4f, f);
        fx_at(j, GR_RING, cx, cy - 1, 1.6f, 1.6f, 0, 2, 1, C_FIRE);
        fx_at(j, GR_RING, cx, cy - 1, 2.8f, 2.8f, 0, 3, 1, RGB(255, 200, 110));
        fx_at(j, GR_STAR, cx, cy - 30, 2.4f, 2.4f, 0, 2, 1, C_WHITE);
        burst(j, PK_EMBER, cx, cy - 20, 40, 6.5f, 60, 3.0f, C_FIRE);
        burst(j, PK_SHARD, cx, cy - 10, 24, 7.0f, 50, 3.0f, RGB(130, 100, 80));
        for (int k = 0; k < 10; k++) part(j, PK_SMOKE, cx + frand(-40, 40), cy - frand(0, 30), frand(-1.2f, 1.2f), -frand(0.4f, 1.4f), 90, 14, RGB(92, 70, 56));
        mark(j, 0, cx, cy, 120, 420);
        camera_shake(3);
        play(s, SND_WINLOSE_IMPACT, 0.9); play(s, SND_STRONG2, 0.6); play(s, SND_EXPLOSION_MEGA, 0.8);
        play_c(s, GS_CRASH, 0.7);
    }
    if (t > IA_LAND && t < IA_LAND + 44 && t % 6 == 0) {     /* burning debris still coming down round him */
        float gx = j->tgt_x + frand(-160, 160), gy = y - frand(160, 220), ang = frand(1.3f, 1.8f), sp = frand(5, 8);
        for (int k = 0; k < 5; k++)
            part(j, PK_STREAK, gx + cosf_(ang) * k * 6, gy + sinf_(ang) * k * 6, cosf_(ang) * sp, sinf_(ang) * sp, 30, 2.0f, k ? C_FIRE : RGB(255, 235, 190));
    }
    if (t >= IA_DUR) {
        special_end(s, j);
        bset(s, &g_VAR_image_speed, 0.25);
        bset_i(s, &g_VAR_alarm, 2, 1);
    }
}

/* in the world (Draw): the fire gathering at his hand before the cut; the cloud over the plain after */
static void ia_draw_world(CInstance *s, Grey *j) {
    int t = j->sp_t;
    float x = sx_(s), y = sy_(s), f = j->dir;
    if (t < IA_CUT) {
        GPose p; V2 J[12];
        ia_pose(t, &p); fk(&p, x, y, f, J);
        if (j->cust) { J[7].x = x + f * 8; J[7].y = y - 26; }
        float c = lin01(t, 0, IA_CUT);
        spr(s, GR_FIRE, (float)((t / 2) % 8), J[7].x + f * 4, J[7].y, f * (0.3f + 0.5f * c), 0.3f + 0.5f * c, 0, C_WHITE, 0.4f + 0.6f * c);
        blend(s, 1);
        spr(s, GR_GLOW, 0, J[7].x, J[7].y, (10 + 34 * c) / 32.0f, (10 + 34 * c) / 32.0f, 0, RGB(255, 140, 50), 0.7f * c);
        blend(s, 0);
    }
    if (t >= IA_LAND) {                                       /* far behind him: the cloud still standing */
        float u = lin01(t, IA_LAND, IA_DUR);
        spr(s, GR_IA_CLOUD, 4 + u * 3.99f, j->tgt_x + f * 110, j->tgt_y + 2, 0.5f + 0.1f * u, 0.5f + 0.1f * u, 0, C_WHITE,
            0.85f * (1 - ease_io(lin01(t, IA_DUR - 30, IA_DUR))));
    }
}

/* Grey himself, huge, for the close-up: the same skeleton scaled k times (mode 0: the neon glow silhouette,
   the caller sets additive; mode 1: outlined and filled like draw_stick) */
static void ia_big(CInstance *s, const V2 *J, float k, int mode, int col, float al, float glow_w) {
    static const int BK[4][2] = { { 2, 4 }, { 4, 5 }, { 0, 8 }, { 8, 9 } };
    static const int FR[4][2] = { { 0, 10 }, { 10, 11 }, { 2, 6 }, { 6, 7 } };
    float o2 = 2 * G_W_OUT * k, wl = G_W_LIMB * k, wt = G_W_TORSO * k, hr = G_HEAD_R * k;
    if (mode == 0) {
        float e = glow_w * k;
        for (int i = 0; i < 4; i++) bone(s, J[BK[i][0]], J[BK[i][1]], wl + e, col, al, 1);
        for (int i = 0; i < 4; i++) bone(s, J[FR[i][0]], J[FR[i][1]], wl + e, col, al, 1);
        bone(s, J[0], J[1], wt + e, col, al, 1);
        spr(s, GR_SHAPE, 1, J[3].x, J[3].y, (hr + e * 0.5f) / 16.0f, (hr + e * 0.5f) / 16.0f, 0, col, al);
        return;
    }
    for (int i = 0; i < 4; i++) bone(s, J[BK[i][0]], J[BK[i][1]], wl + o2, C_LINE, al, 1);
    for (int i = 0; i < 4; i++) bone(s, J[BK[i][0]], J[BK[i][1]], wl, C_BACK, al, 1);
    for (int i = 0; i < 4; i++) bone(s, J[FR[i][0]], J[FR[i][1]], wl + o2, C_LINE, al, 1);
    bone(s, J[0], J[1], wt + o2, C_LINE, al, 1);
    spr(s, GR_SHAPE, 1, J[3].x, J[3].y, (hr + G_W_OUT * k) / 16.0f, (hr + G_W_OUT * k) / 16.0f, 0, C_LINE, al);
    for (int i = 0; i < 4; i++) bone(s, J[FR[i][0]], J[FR[i][1]], wl, C_FILL, al, 1);
    bone(s, J[0], J[1], wt, C_FILL, al, 1);
    spr(s, GR_SHAPE, 1, J[3].x, J[3].y, hr / 16.0f, hr / 16.0f, 0, C_FILL, al);
}

/* the close-up: the bow drawn, then released and the camera whipping after the arrow */
/* A character from the game's own creator, drawn huge for the close-up: the same layers, in the same order and
   colours, as the creator's preview (scr_customchar_draw_stand), standing pose. Its own little bow is left out:
   the bow of fire is in its hand instead. Lit from the fire (an orange rim on the bow side). */
#define CUST_SPR_BODY 1343
static void cust_layer(CInstance *s, int spr_id, YYVAR *img_v, YYVAR *col_v, float ox, float oy, float k, float dir) {
    double img = img_v ? sget(s, img_v) : 0, col = sget(s, col_v);
    if (!(img >= 0) || img > 400) return;
    int cc = (col >= 0 && col <= 0xFFFFFF) ? (int)col : C_WHITE;
    YYGML_draw_sprite_ext(s, spr_id, (float)img, ox, oy, dir * k, k, 0, cc, 1);
}
static void cust_draw_big(CInstance *s, float ox, float oy, float k, float dir, float fire) {
    if (!finite_(ox) || !finite_(oy) || !finite_(k)) return;
    /* (calls, not a table of pointers: the blob has no absolute relocations) */
    cust_layer(s, 1327, &g_VAR_img_back, &g_VAR_col_back, ox, oy, k, dir);
    cust_layer(s, CUST_SPR_BODY, 0, &g_VAR_col_body, ox, oy, k, dir);
    cust_layer(s, 1336, &g_VAR_img_head, &g_VAR_col_head, ox, oy, k, dir);
    cust_layer(s, 1333, &g_VAR_img_feet, &g_VAR_col_feet, ox, oy, k, dir);
    cust_layer(s, 1329, &g_VAR_img_bottom, &g_VAR_col_bottom, ox, oy, k, dir);
    cust_layer(s, 1341, &g_VAR_img_top, &g_VAR_col_top, ox, oy, k, dir);
    cust_layer(s, 1331, &g_VAR_img_design, &g_VAR_col_design, ox, oy, k, dir);
    cust_layer(s, 1339, &g_VAR_img_overtop, &g_VAR_col_overtop, ox, oy, k, dir);
    cust_layer(s, 1328, &g_VAR_img_belt, &g_VAR_col_belt, ox, oy, k, dir);
    cust_layer(s, 1326, &g_VAR_img_arms, &g_VAR_col_arms, ox, oy, k, dir);
    cust_layer(s, 1326, &g_VAR_img_arms2, &g_VAR_col_arms2, ox, oy, k, dir);
    cust_layer(s, 1338, &g_VAR_img_overall, &g_VAR_col_overall, ox, oy, k, dir);
    cust_layer(s, 1332, &g_VAR_img_face, &g_VAR_col_face, ox, oy, k, dir);
    cust_layer(s, 1340, &g_VAR_img_face, &g_VAR_col_pup, ox, oy, k, dir);
    cust_layer(s, 1337, &g_VAR_img_mask, &g_VAR_col_mask, ox, oy, k, dir);
    cust_layer(s, 1334, &g_VAR_img_hair, &g_VAR_col_hair, ox, oy, k, dir);
    cust_layer(s, 1335, &g_VAR_img_hat, &g_VAR_col_hat, ox, oy, k, dir);
    blend(s, 1);                                               /* the firelight on the bow side */
    spr(s, GR_GLOW, 0, ox + dir * 10 * k, oy - 28 * k, 26 * k / 32.0f, 34 * k / 32.0f, 0, RGB(255, 110, 30), 0.35f * fire);
    blend(s, 0);
}
static void ia_draw_closeup(CInstance *s, Grey *j, float gw, float gh) {
    int t = j->sp_t;
    float dir = j->dir;
    float u = lin01(t, IA_CUT, IA_LOOSE), push = 1 + 0.07f * ease_io(u);
    float whip = ease(1, lin01(t, IA_LOOSE + 4, IA_FLY));    /* the camera whips after the arrow */
    float shx = 0, shy = 0;
    if (t > IA_LOOSE - 26 && t < IA_LOOSE) { float a = gh * 0.004f * lin01(t, IA_LOOSE - 26, IA_LOOSE); shx = frand(-a, a); shy = frand(-a, a); }
    float camx = -dir * whip * gw * 1.4f + shx;
    /* the dusty sunset behind him, drifting */
    stretched(s, GR_IA_SKY, 0, -gw * 0.1f - dir * gw * 0.06f * u + camx * 0.35f, -gh * 0.04f + shy, gw * 1.3f, gh * 1.1f, C_WHITE, 1);
    float k = gh / 56.0f * push;                               /* knees down out of frame, his head clear of the bars */
    float ox = gw * 0.5f - dir * gh * 0.26f + camx, oy = gh * 1.08f + shy;
    GPose p; V2 J[12];
    ia_pose(t, &p); fk(&p, 0, 0, dir, J);
    for (int i = 0; i < 12; i++) { J[i].x = ox + J[i].x * k; J[i].y = oy + J[i].y * k; if (!finite_(J[i].x) || !finite_(J[i].y)) return; }
    float kc = gh / 62.0f * push;                              /* a custom character: 64 px sprite, head clear of the bars */
    if (j->cust) {                                             /* the grip in front of the chest, the draw hand behind */
        J[7].x = ox + dir * 9 * kc; J[7].y = oy - 27 * kc;
        J[5].x = ox - dir * 5 * kc; J[5].y = oy - 27 * kc;
    }
    /* the bow of fire: grows out from the grip */
    float grow = ease_io(lin01(t, IA_CUT, IA_CUT + 22)), fb = gh * 0.58f / 210.0f;
    float bx = J[7].x, by = J[7].y;
    V2 tA = { bx - dir * 80 * fb, by - 210 * fb * grow }, tB = { bx - dir * 80 * fb, by + 210 * fb * grow };
    V2 nk;                                                     /* where the string is pulled to */
    if (t < IA_LOOSE) nk = J[5];
    else {
        float a = (float)(t - IA_LOOSE);
        nk.x = tA.x + dir * gh * 0.05f * sinf_(a * 1.7f) * expf_(-a / 5.0f); nk.y = by;
    }
    float charge = ease_io(lin01(t, IA_CUT + 8, IA_LOOSE));
    V2 hd = { bx + dir * gh * 0.16f, by };                     /* the arrowhead, resting past the grip */
    float gone = t >= IA_LOOSE ? (float)(t - IA_LOOSE) : -1;   /* after the release: the arrow is away */
    /* additive: the bow's light on everything behind, and his neon glow */
    blend(s, 1);
    spr(s, GR_GLOW, 0, bx, by, gh * 0.75f / 32.0f, gh * 0.95f / 32.0f, 0, RGB(255, 120, 40), 0.45f * grow);
    if (!j->cust) ia_big(s, J, k, 0, C_CYAN, 0.16f, 5);
    if (!j->cust && t % 23 < 2) {                                          /* now and then he glitches, even here: an RGB split */
        V2 Jc[12], Jm[12];                                     /* (behind him, so only the fringes show) */
        for (int i = 0; i < 12; i++) { Jc[i] = J[i]; Jc[i].x -= gh * 0.01f; Jm[i] = J[i]; Jm[i].x += gh * 0.01f; }
        ia_big(s, Jc, k, 0, C_CYAN, 0.8f, 2); ia_big(s, Jm, k, 0, C_MAG, 0.8f, 2);
    }
    blend(s, 0);
    if (j->cust) cust_draw_big(s, ox, oy, kc, dir, grow);
    else ia_big(s, J, k, 1, 0, 1, 0);
    spr(s, GR_FIREBOW, (float)((t / 3) % 6), bx, by, dir * fb, fb * grow, 0, C_WHITE, clampf(grow * 1.6f, 0, 1));
    float sw = gh * 0.0045f;                                   /* the string: white-hot */
    seg(s, tA.x, tA.y, nk.x, nk.y, sw, RGB(255, 236, 200), grow);
    seg(s, nk.x, nk.y, tB.x, tB.y, sw, RGB(255, 236, 200), grow);
    if (gone < 0) {                                           /* the arrow on the string: a dark shaft, its head on fire */
        seg(s, nk.x, nk.y, hd.x, hd.y, gh * 0.011f, C_LINE, 1);
        float fs = (0.6f + 2.2f * charge) * gh / 600.0f;
        spr(s, GR_FIRE, (float)((t / 2) % 8), hd.x, hd.y, dir * fs, fs, 0, C_WHITE, 1);
    }
    /* additive: the burning string and shaft, the knot of fire, embers peeling off the bow, the release */
    blend(s, 1);
    seg(s, tA.x, tA.y, nk.x, nk.y, sw * 4, RGB(255, 120, 40), 0.35f * grow);
    seg(s, nk.x, nk.y, tB.x, tB.y, sw * 4, RGB(255, 120, 40), 0.35f * grow);
    if (gone < 0) {
        seg(s, nk.x, nk.y, hd.x, hd.y, gh * 0.006f, RGB(255, 170, 60), 0.5f * charge);
        float r = gh * (0.04f + 0.16f * charge) * (1 + 0.08f * sinf_(t * 0.9f));
        spr(s, GR_GLOW, 0, hd.x, hd.y, r / 32.0f, r / 32.0f, 0, RGB(255, 200, 90), 0.5f + 0.4f * charge);
        spr(s, GR_GLOW, 0, hd.x, hd.y, r * 0.4f / 32.0f, r * 0.4f / 32.0f, 0, C_WHITE, 0.6f * charge);
    }
    for (int i = 0; i < 44; i++) {                            /* embers: born on the limbs, drifting back and up */
        float ph = (float)((t * 3 + (int)(h01(i * 7 + 1) * 150)) % 150) / 150.0f;
        float v = h01(i * 7 + 2) * 2 - 1, av = fabsf_(v);
        float ex = bx - dir * 80 * fb * av * sqrtf_(av) - dir * ph * gh * (0.25f + 0.2f * h01(i * 7 + 3));
        float ey = by + v * 210 * fb * grow - ph * gh * (0.10f + 0.14f * h01(i * 7 + 4)) + sinf_(ph * 9 + i) * gh * 0.01f;
        float sz = gh * (0.004f + 0.007f * h01(i * 7 + 5)) * (1 - ph);
        if (grow > 0.3f) spr(s, GR_GLOW, 0, ex, ey, sz / 32.0f * 3, sz / 32.0f * 3, 0, bb_col(1.9f - 1.5f * ph), 0.9f * (1 - ph));
    }
    if (gone >= 0 && gone < 12) {                             /* the release: a burst of flame at the nock */
        float g = 1 - gone / 12.0f;
        spr(s, GR_GLOW, 0, hd.x, hd.y, gh * 0.55f * (1 + gone * 0.08f) / 32.0f, gh * 0.4f / 32.0f, 0, RGB(255, 220, 120), g);
        spr(s, GR_GLOW, 0, hd.x, hd.y, gh * 0.2f / 32.0f, gh * 0.2f / 32.0f, 0, C_WHITE, g);
        for (int i = 0; i < 14; i++) {
            float a = h01(i + 900) * 6.2832f, r0 = gh * 0.08f, r1 = gh * (0.25f + 0.35f * h01(i + 950)) * (0.5f + gone / 8.0f);
            glow_streak(s, hd.x + cosf_(a) * r0, hd.y + sinf_(a) * r0, hd.x + cosf_(a) * r1, hd.y + sinf_(a) * r1, gh * 0.012f, RGB(255, 190, 90), g * 0.8f);
        }
        float ax = hd.x + dir * gone * gone * gw * 0.02f;     /* the arrow leaving, a streak of fire */
        spr(s, GR_FIRETRAIL, (float)(t % 6), ax, hd.y, gh * 1.1f / 256.0f, gh * 0.09f / 48.0f, dir > 0 ? 0 : 180, C_WHITE, g);
    }
    blend(s, 0);
    if (whip > 0) {                                           /* the whip: the picture smears into speed */
        rect(0, 0, gw, gh, RGB(118, 94, 76), 0.85f * whip);
        for (int i = 0; i < 18; i++) {
            float yy = h01(i + 300) * gh, len = gw * (0.2f + 0.5f * h01(i + 330));
            float xx = (float)fmodf_(h01(i + 360) * gw * 3 - dir * (t - IA_LOOSE) * gw * 0.18f, gw * 1.6f) - gw * 0.3f;
            seg(s, xx, yy, xx + len, yy, gh * (0.002f + 0.004f * h01(i + 390)), RGB(200, 180, 160), 0.5f * whip);
        }
    }
}

/* a speed ring the arrow punched through (white, expanding, fading) */
static void ia_ring(CInstance *s, float x, float y, float age, float gh, float dir) {
    if (age < 0 || age > 1) return;
    float sc = gh * (0.26f + 0.2f * age) / 112.0f;
    spr(s, GR_SPEEDRING, (float)((int)fabsf_(x) % 4), x, y, sc * (1.0f + 0.6f * age), sc, 0, C_WHITE, 1 - age * age);
}

static void ia_draw_flight(CInstance *s, Grey *j, float gw, float gh) {
    int t = j->sp_t;
    float dir = j->dir, u = lin01(t, IA_FLY, IA_FLASH);
    float sh = gh * 0.004f;
    float shx = frand(-sh, sh), shy = frand(-sh, sh);
    stretched(s, GR_IA_SKY, 0, -gw * 0.15f - dir * u * gw * 0.12f + shx, -gh * 0.12f + shy, gw * 1.35f, gh * 1.1f, C_WHITE, 1);
    /* the plain racing past underneath */
    float tw = gw * 0.8f, th = gh * 0.34f, scroll = fmodf_(u * gw * 3.2f, tw);
    for (int i = -1; i < (int)(gw / tw) + 2; i++) {
        float x0 = i * tw + (dir > 0 ? -scroll : scroll);
        stretched(s, GR_IA_HILLS, 0, x0 + shx, gh * 0.70f + shy, tw + 1, th, C_WHITE, 1);
    }
    /* the arrow: across the frame, dipping toward the target */
    float ax = gw * 0.5f - dir * gw * 0.7f + dir * u * gw * 1.55f, ay = gh * (0.36f + 0.16f * u * u);
    float vx = dir * gw * 1.55f, vy = gh * 0.32f * u, ang = -atan2f_(vy, vx) * 57.29578f;
    for (int i = 0; i < 9; i++) {                             /* the speed rings it punched through, behind it */
        int ti = IA_FLY + 2 + i * 5;
        if (t < ti) continue;
        float ui = lin01(ti, IA_FLY, IA_FLASH);
        ia_ring(s, gw * 0.5f - dir * gw * 0.7f + dir * ui * gw * 1.55f, gh * (0.36f + 0.16f * ui * ui), (t - ti) / 18.0f, gh, dir);
        if (t - ti < 30) {                                    /* the ground under it torn up into dust */
            float dx = gw * 0.5f - dir * gw * 0.7f + dir * ui * gw * 1.55f, a = (t - ti) / 30.0f;
            spr(s, GR_SMOKE, (float)(i % 8), dx, gh * 0.74f - a * gh * 0.08f, gh * (0.012f + 0.02f * a), gh * (0.01f + 0.016f * a), 0,
                RGB(255, 226, 190), 0.75f * (1 - a));
        }
    }
    spr(s, GR_FIRETRAIL, (float)(t % 6), ax, ay, gw * 0.75f / 256.0f, gh * 0.12f / 48.0f, ang, C_WHITE, 1);
    blend(s, 1);
    spr(s, GR_GLOW, 0, ax, ay, gh * 0.22f / 32.0f, gh * 0.16f / 32.0f, ang, RGB(255, 170, 70), 0.8f);
    spr(s, GR_GLOW, 0, ax, ay, gh * 0.06f / 32.0f, gh * 0.06f / 32.0f, 0, C_WHITE, 0.9f);
    for (int i = 0; i < 10; i++) {                            /* sparks shed into its wake */
        float ph = h01(i + 40 + t / 3 * 13);
        float px = ax - dir * ph * gw * 0.4f, py = ay + (h01(i + 70 + t) - 0.5f) * gh * 0.08f;
        spr(s, GR_GLOW, 0, px, py, gh * 0.01f / 32.0f * 3, gh * 0.01f / 32.0f * 3, 0, bb_col(1.8f - ph), 0.8f * (1 - ph));
    }
    blend(s, 0);
}

static void ia_draw_flash(CInstance *s, Grey *j, float gw, float gh) {
    int k = j->sp_t - IA_FLASH;
    float cx = gw * 0.5f, cy = gh * 0.58f;
    if (k < 3) {                                              /* the strike: orange fire, a dark red dome swelling */
        rect(0, 0, gw, gh, RGB(255, 130, 30), 1);
        spr(s, GR_SHAPE, 1, cx, gh * 0.9f, gh * (0.22f + 0.06f * k) / 16.0f, gh * (0.18f + 0.05f * k) / 16.0f, 0, RGB(176, 40, 20), 1);
        blend(s, 1);
        for (int i = 0; i < 12; i++) {
            float a = h01(i + 1200) * 6.2832f, r = gh * (0.4f + 0.5f * h01(i + 1230));
            glow_streak(s, cx, cy, cx + cosf_(a) * r, cy + sinf_(a) * r * 0.7f, gh * 0.03f, RGB(255, 230, 90), 0.9f);
        }
        spr(s, GR_GLOW, 0, cx, cy, gh * 0.4f / 32.0f, gh * 0.3f / 32.0f, 0, RGB(255, 240, 160), 1);
        blend(s, 0);
        return;
    }
    rect(0, 0, gw, gh * 0.5f, RGB(255, 196, 0), 1);            /* the yellow card, ink focus lines on it */
    rect(0, gh * 0.5f, gw, gh, RGB(255, 226, 40), 1);
    for (int i = 0; i < 34; i++) {
        float a = h01(i + 1300) * 6.2832f, r0 = gh * (0.16f + 0.22f * h01(i + 1330)), r1 = gw;
        seg(s, cx + cosf_(a) * r0, cy + sinf_(a) * r0, cx + cosf_(a) * r1, cy + sinf_(a) * r1, gh * (0.002f + 0.005f * h01(i + 1360)), INK_C, 1);
    }
    for (int i = 0; i < 8; i++) {                              /* splatter flung toward the camera */
        float a = h01(i + 1400) * 6.2832f, r = gh * (0.06f + 0.12f * h01(i + 1430));
        spr(s, GR_SHAPE, 0, cx + cosf_(a) * r, cy + sinf_(a) * r, gh * 0.03f / 32.0f, gh * 0.008f / 32.0f, -a * 57.29578f, INK_C, 1);
    }
}

static void ia_draw_top(CInstance *s, Grey *j, float gw, float gh) {
    int t = j->sp_t;
    float u = lin01(t, IA_TOP, IA_SPIKE), dir = j->dir;
    float sh = gh * 0.012f * (1 - u);
    float shx = frand(-sh, sh), shy = frand(-sh, sh);
    float cx = gw * 0.5f + shx, cy = gh * 0.52f + shy;
    float zoom = 1.3f - 0.22f * ease_io(u), W = gw * zoom * 1.05f, H = W * 180.0f / 320.0f;
    if (H < gh * zoom) { H = gh * zoom; W = H * 320.0f / 180.0f; }
    stretched(s, GR_IA_TOP, 0, cx - W / 2, cy - H / 2, W, H, C_WHITE, 1);
    float sc = gh * (0.42f + 1.0f * ease(2, u)) / 192.0f;
    spr(s, GR_IA_CRATER, u * 7.99f, cx, cy, sc, sc, 0, C_WHITE, 1);
    blend(s, 1);
    float hot = 1 - u;
    spr(s, GR_GLOW, 0, cx, cy, gh * (0.18f + 0.3f * u) / 32.0f, gh * (0.18f + 0.3f * u) / 32.0f, 0, bb_col(0.6f + 1.8f * hot), 0.9f * hot);
    if (t - IA_TOP < 8) {                                     /* the arrow plunging in, from the way it flew */
        float a = (t - IA_TOP) / 8.0f, L = gh * 0.7f * (1 - a);
        glow_streak(s, cx - dir * L, cy - L * 0.55f, cx, cy, gh * 0.05f * (1 - a) + 2, RGB(255, 160, 50), 1 - a);
    }
    blend(s, 0);
    for (int i = 0; i < 18; i++) {                            /* rocks blasted up at the camera: flying out, growing */
        float a = h01(i + 2000) * 6.2832f, sp = 0.4f + 0.8f * h01(i + 2030), t0 = h01(i + 2060) * 0.25f;
        float q = lin01f(u, t0, t0 + 0.75f);
        if (q <= 0 || q >= 1) continue;
        float r = gh * (0.08f + 0.9f * sp * q), z = 0.5f + 3.5f * q * q * sp;
        spr(s, GR_ROCKS, (float)(i % 8), cx + cosf_(a) * r, cy + sinf_(a) * r * 0.8f, z * gh / 600.0f, z * gh / 600.0f,
            a * 57.29578f + q * 200, RGB(255, 222, 190), 1);
    }
}

static void ia_draw_cloud(CInstance *s, Grey *j, float gw, float gh) {
    int t = j->sp_t;
    float u = lin01(t, IA_CLOUD, IA_LAND), gy = gh * 0.8f, cx = gw * 0.5f;
    for (int b = 0; b < 8; b++) {                              /* a pale, washed-out sky */
        float f0 = b / 8.0f, f1 = (b + 1) / 8.0f;
        int c = (int)(238 - 22 * (1 - f0));
        rect(0, gh * f0, gw, gh * f1 + 1, RGB(c, c, c - 2), 1);
    }
    for (int i = 0; i < 7; i++) {                              /* soft grey clouds, drifting */
        float x = fmodf_(h01(i + 3000) * gw * 1.4f + u * gw * 0.06f * (i % 2 ? 1 : -1), gw * 1.4f) - gw * 0.2f;
        float y = gh * (0.12f + 0.4f * h01(i + 3030)), r = gh * (0.14f + 0.16f * h01(i + 3060));
        spr(s, GR_GLOW, 0, x, y, r * 2.2f / 32.0f, r / 32.0f, 0, RGB(250, 250, 250), 0.85f);
        spr(s, GR_GLOW, 0, x + r * 0.3f, y + r * 0.25f, r * 1.6f / 32.0f, r * 0.6f / 32.0f, 0, RGB(196, 196, 198), 0.5f);
    }
    stretched(s, GR_IA_HILLS, 0, -gw * 0.05f, gy - gh * 0.12f, gw * 1.1f, gh * 0.22f, RGB(214, 200, 190), 1);   /* far ridges */
    float sc = gh * 0.6f / 224.0f * (0.86f + 0.22f * u);
    spr(s, GR_IA_CLOUD, clampf(u * 9.0f, 0, 7.99f), cx, gy, sc, sc, 0, C_WHITE, 1);
    blend(s, 1);                                              /* the fireball still burning inside its base */
    spr(s, GR_GLOW, 0, cx, gy - gh * 0.06f, gh * 0.2f / 32.0f, gh * 0.12f / 32.0f, 0, RGB(255, 150, 60), 0.55f * (1 - u));
    blend(s, 0);
    float rr = 1.5f + 13.0f * ease(2, u);                     /* the shock ring racing out along the ground */
    spr(s, GR_RING, 3, cx, gy, rr * gw / 1200.0f, rr * gw / 1200.0f * 0.5f, 0, RGB(250, 246, 240), 0.8f * (1 - u));
    for (int i = 0; i < 12; i++) {                             /* a wall of dust along the ground */
        float a = (i - 5.5f) / 5.5f, ex = ease(2, u);
        spr(s, GR_SMOKE, (float)(i % 8), cx + a * gw * 0.55f * ex, gy - gh * 0.01f, gh * (0.012f + 0.02f * ex), gh * (0.01f + 0.014f * ex), 0,
            RGB(255, 240, 222), 0.7f * (1 - u * 0.6f));
    }
    for (int i = 0; i < 16; i++) {                             /* rocks thrown on arcs, some right past the camera */
        float vx = (h01(i + 3100) - 0.5f) * 2.2f, vy = 0.8f + 0.9f * h01(i + 3130), t0 = h01(i + 3160) * 0.3f;
        float q = lin01f(u, t0, 1);
        if (q <= 0) continue;
        float x = cx + vx * q * gw * 0.5f, y = gy - (vy * q - 1.1f * q * q) * gh * 0.7f;
        float z = (0.9f + 2.4f * h01(i + 3190)) * (1 + q * (i % 3 == 0 ? 2.5f : 0.3f));
        spr(s, GR_ROCKS, (float)(i % 8), x, y, z * gh / 600.0f, z * gh / 600.0f, q * 300 * (vx > 0 ? 1 : -1), RGB(255, 214, 180), 1);
    }
    stretched(s, GR_IA_HILLS, 0, -gw * 0.1f, gy - gh * 0.02f, gw * 1.2f, gh * 0.3f, RGB(160, 128, 108), 1);  /* foreground rocks */
}

/* the cinematic layer (Draw GUI) */
static void ia_draw_gui(CInstance *s, Grey *j, float gw, float gh) {
    int t = j->sp_t;
    if (t >= IA_CUT && t < IA_FLY) ia_draw_closeup(s, j, gw, gh);
    else if (t >= IA_FLY && t < IA_FLASH) ia_draw_flight(s, j, gw, gh);
    else if (t >= IA_FLASH && t < IA_TOP) ia_draw_flash(s, j, gw, gh);
    else if (t >= IA_TOP && t < IA_SPIKE) ia_draw_top(s, j, gw, gh);
    else if (t >= IA_SPIKE && t < IA_CLOUD) {                 /* white-out: the black spike of earth */
        rect(0, 0, gw, gh, C_WHITE, 1);
        float pop = 1 + 0.1f * (1 - lin01(t, IA_SPIKE, IA_SPIKE + 4)), sc = gw * 0.62f / 224.0f * pop;
        spr(s, GR_IA_SPLASH, 0, gw * 0.5f, gh * 0.86f, sc, sc * (0.8f + 0.25f * lin01(t, IA_SPIKE, IA_CLOUD)), 0, C_WHITE, 1);
        rect(0, gh * 0.86f, gw, gh * 0.87f, INK_C, 1);
    } else if (t >= IA_CLOUD && t < IA_LAND) ia_draw_cloud(s, j, gw, gh);
    /* white cuts: into the close-up, and out of the cloud back down to the fight */
    float white = 0;
    if (t >= IA_CUT - 4 && t < IA_CUT + 4) white = 1 - fabsf_((float)(t - IA_CUT)) / 4.0f;
    if (t >= IA_LAND - 14 && t < IA_LAND) white = ease_io(lin01(t, IA_LAND - 14, IA_LAND));
    if (t >= IA_LAND) white = 1 - ease_io(lin01(t, IA_LAND, IA_LAND + 18));
    if (white > 0) rect(0, 0, gw, gh, RGB(255, 248, 236), white);
}

/* ------------------------------------------------------------------------------------------ */
/* the lava world: what is left after MOONFALL. Like Scyther's void: the stage's own backdrop is hidden    */
/* (layers behind the fighters without instances: backgrounds, tiles; scenery instances made invisible)  */
/* and Draw Begin paints a burning sky (the Moon's debris ring arcing over it), two ranges of volcanoes   */
/* with lava rivers, and a crust of cooled basalt with glowing cracks on every solid you can stand on.   */
/* ------------------------------------------------------------------------------------------ */
static int inst_count_all(CInstance *s, int obj) {
    RValue n = rv_undef(); RValue a = rv_real(obj);
    F_InstanceNumber(&n, s, s, 1, &a);
    int c = (int)rv_num(&n); rv_free(&n);
    return c < 0 ? 0 : (c > 400 ? 400 : c);
}
static double arr_len(CInstance *s, RValue *arr) {
    RValue r = rv_undef();
    RValue *args[1] = { arr };
    YYGML_CallLegacyFunction(s, s, &r, 1, g_FUNC_array_length_1d.id, args);
    double d = rv_num(&r);
    rv_free(&r);
    return d;
}
static double fighters_depth(CInstance *s) {              /* the deepest fighter: deeper than this is scenery */
    double dmax = sget(s, &g_VAR_depth);
    if (dmax < -1000) dmax = 0;                              /* (during the special we sit at -15000) */
    int cnt = inst_count(s, OBJ_PARENT_CHARACTER), id;
    for (int i = 0; i < cnt && i < 16; i++) {
        CInstance *c = inst_nth(s, OBJ_PARENT_CHARACTER, i, &id);
        if (!c || c == s) continue;
        double d = sget(c, &g_VAR_depth);
        if (d > dmax) dmax = d;
    }
    return dmax;
}
static void hide_scenery(CInstance *s, double dmax) {
    int id;
    for (int k = 0; k < N_STAGE_DECOR; k++) {
        int obj = k_stage_decor[k];
        int n = inst_count_all(s, obj);
        for (int i = 0; i < n; i++) {
            CInstance *c = inst_nth(s, obj, i, &id);
            if (c && sget(c, &g_VAR_depth) > dmax) bset(c, &g_VAR_visible, 0);
        }
    }
}
static void hide_layers(CInstance *s, double dmax) {
    RValue *xx = var_slot_w(s, g_VAR_xx.id);
    rv_free(xx);
    RValue none = rv_undef();
    F_LayerGetAll(xx, s, s, 0, &none);
    if ((xx->kind & KIND_MASK) != VALUE_ARRAY) { rv_free(xx); *xx = rv_real(0); return; }
    int n = (int)arr_len(s, xx);
    RValue self = rv_inst(s);
    for (int i = 0; i < n && i < 64; i++) {
        RValue layer = rv_undef();
        YYGML_Variable_GetValue(&self, g_VAR_xx.id, i, &layer, false, false);
        if (fcall1(s, F_LayerGetDepth, layer) <= dmax) { rv_free(&layer); continue; }
        RValue *yy = var_slot_w(s, g_VAR_yy.id);
        rv_free(yy);
        F_LayerGetAllElements(yy, s, s, 1, &layer);
        int has_inst = 0;
        if ((yy->kind & KIND_MASK) == VALUE_ARRAY) {
            int m = (int)arr_len(s, yy);
            for (int k = 0; k < m && k < 512 && !has_inst; k++) {
                RValue el = rv_undef();
                YYGML_Variable_GetValue(&self, g_VAR_yy.id, k, &el, false, false);
                if (fcall1(s, F_LayerGetElementType, el) == 2) has_inst = 1;     /* layerelementtype_instance */
                rv_free(&el);
            }
        }
        yy = var_slot_w(s, g_VAR_yy.id); rv_free(yy); *yy = rv_real(0);
        if (!has_inst) {
            RValue r = rv_undef();
            RValue a[2] = { layer, rv_bool(false) };
            F_LayerSetVisible(&r, s, s, 2, a);
            rv_free(&r);
        }
        rv_free(&layer);
    }
    xx = var_slot_w(s, g_VAR_xx.id); rv_free(xx); *xx = rv_real(0);
}
static void lava_activate(CInstance *s, Grey *j) {
    if (j->lava_on) return;
    j->lava_on = 1; j->lava_t = 0; j->lava_gy = sy_(s);
    double dmax = fighters_depth(s);
    hide_scenery(s, dmax);
    if (!j->lava_hidden) { j->lava_hidden = 1; hide_layers(s, dmax); }
}
static void spr_part(CInstance *s, int a, float img, float l, float t, float w, float h, float x, float y, int col, float alpha) {
    if (a < 0 || a >= GR_COUNT || g_grey_spr[a] < 0 || !finite_(x) || !finite_(y)) return;
    RValue r = rv_undef();
    RValue v[12] = { rv_real(g_grey_spr[a]), rv_real(img), rv_real(l), rv_real(t), rv_real(w), rv_real(h), rv_real(x), rv_real(y),
                     rv_real(1), rv_real(1), rv_real(col), rv_real(alpha) };
    F_DrawSpritePartExt(&r, s, s, 12, v);
    rv_free(&r);
}
/* a 1024 px strip, tiled across the view with parallax p, its base on the line `base` */
static void lava_range(CInstance *s, int a, float vx, float vw, float base, float p, int col, float alpha) {
    float off = -vx * p;
    off -= 1024.0f * (float)(int)(off / 1024.0f);
    if (off > 0) off -= 1024.0f;
    for (float x = vx + off; x < vx + vw; x += 1024.0f) spr(s, a, 0, x, base, 1, 1, 0, col, alpha);
}
static void lava_floor(CInstance *s, Grey *j, float vx, float vy, float vw, float vh, float fade) {
    typedef struct { float l, r, t; } Slab;
    Slab sl[32]; int n = 0, id;
    int cnt = inst_count_all(s, OBJ_PARENT_SOLID);
    for (int i = 0; i < cnt && i < 128 && n < 32; i++) {
        CInstance *c = inst_nth(s, OBJ_PARENT_SOLID, i, &id);
        if (!c) continue;
        float l = (float)sget(c, &g_VAR_bbox_left), r = (float)sget(c, &g_VAR_bbox_right) + 1, t = (float)sget(c, &g_VAR_bbox_top);
        if (!finite_(l) || !finite_(r) || !finite_(t)) continue;
        if (r - l < 24 || r < vx - 80 || l > vx + vw + 80 || t > vy + vh + 20 || t < vy - 80) continue;
        int k = n++;
        while (k > 0 && (sl[k - 1].t > t || (sl[k - 1].t == t && sl[k - 1].l > l))) { sl[k] = sl[k - 1]; k--; }
        sl[k].l = l; sl[k].r = r; sl[k].t = t;
    }
    int m = 0;
    for (int i = 0; i < n; i++) {
        if (m > 0 && fabsf_(sl[m - 1].t - sl[i].t) < 2 && sl[i].l <= sl[m - 1].r + 2) {
            if (sl[i].r > sl[m - 1].r) sl[m - 1].r = sl[i].r;
        } else sl[m++] = sl[i];
    }
    if (m == 0 && j->lava_gy > 0) { sl[0].l = vx - 100; sl[0].r = vx + vw + 100; sl[0].t = j->lava_gy; m = 1; }
    for (int i = 0; i < m; i++) {
        float x0 = sl[i].l > vx - 80 ? sl[i].l : vx - 80, x1 = sl[i].r < vx + vw + 80 ? sl[i].r : vx + vw + 80, T = sl[i].t;
        if (x1 - x0 < 1 || x1 - x0 > 4000) continue;
        float bottom = vy + vh + 4;
        if (bottom > T + 48) rect(x0, T + 47, x1, bottom, RGB(10, 7, 6), fade);   /* rock, down out of sight */
        for (float x = x0; x < x1;) {                           /* the crust, tiled along the world */
            int u = (int)x % 256; if (u < 0) u += 256;
            float w = 256.0f - u;
            if (x + w > x1) w = x1 - x;
            spr_part(s, GR_LAVA_CRUST, 0, (float)u, 0, w, 48, x, T, C_WHITE, fade);
            x += w;
        }
    }
    YYGML_draw_set_colour(C_WHITE); YYGML_draw_set_alpha(1);
}
static void draw_lava(CInstance *s, Grey *j) {
    j->lava_drawn = j->aura_t;
    g_blend_cur = -1;
    float vx, vy, vw, vh;
    mf_view(s, &vx, &vy, &vw, &vh);
    float fade = j->lava_t < 10 ? 0.4f + 0.06f * j->lava_t : 1.0f;
    stretched(s, GR_LAVA_SKY, 0, vx, vy, vw, vh, C_WHITE, fade);
    int lt = j->lava_t % 233;                                 /* volcanic lightning in the ash */
    if (lt < 4 && j->lava_t > 30) {
        blend(s, 1);
        float k = lt == 0 ? 0.5f : (lt == 2 ? 0.35f : 0.15f);
        rect(vx, vy, vx + vw, vy + vh * 0.55f, RGB(150, 110, 170), k * fade);
        blend(s, 0);
    }
    float gy = j->lava_gy > 0 ? j->lava_gy : vy + vh * 0.8f;
    lava_range(s, GR_LAVA_FAR, vx, vw, gy - 18, 0.12f, C_WHITE, fade);
    lava_range(s, GR_LAVA_MID, vx, vw, gy + 6, 0.35f, C_WHITE, fade);
    float pulse = 0.5f + 0.5f * sinf_(j->lava_t * 0.045f);   /* the rivers' glow breathing */
    blend(s, 1);
    lava_range(s, GR_LAVA_MID, vx, vw, gy + 6, 0.35f, RGB(255, 120, 40), 0.18f * pulse * fade);
    blend(s, 0);
    lava_floor(s, j, vx, vy, vw, vh, fade);
    YYGML_draw_set_colour(C_WHITE); YYGML_draw_set_alpha(1);
}
/* embers rising off the lava, ash drifting down, now and then thunder in the ash clouds */
static void lava_ambient(CInstance *s, Grey *j) {
    if (j->lava_t % 233 == 1 && j->lava_t > 30) play(s, SND_THUNDER, 0.3);
    if (j->lava_t % 3 != 0) return;
    float vx, vy, vw, vh;
    mf_view(s, &vx, &vy, &vw, &vh);
    float gy = j->lava_gy > 0 ? j->lava_gy : vy + vh * 0.8f;
    Part *q = part(j, PK_EMBER, vx + frand(0, vw), gy + frand(-4, 10), frand(-0.4f, 0.4f), -frand(0.4f, 1.3f),
                   80 + (int)(rnd() % 60), frand(1.2f, 2.4f), (rnd() & 1) ? C_FIRE : RGB(255, 190, 90));
    if (q) { q->g = -0.012f; q->drag = 0.99f; }
    if (j->lava_t % 6 == 0) {
        Part *a = part(j, PK_PIXEL, vx + frand(0, vw), vy - 4, frand(-0.3f, 0.3f), frand(0.3f, 0.7f), 260, frand(1.0f, 1.8f), RGB(46, 40, 38));
        if (a) { a->g = 0.002f; a->drag = 1; a->vr = frand(-3, 3); }
    }
}

/* ------------------------------------------------------------------------------------------ */
/* events                                                                                      */
/* ------------------------------------------------------------------------------------------ */
void gml_Object_o_grey_Create_0(CInstance *s, CInstance *o) {
    grey_load_assets(s);
    gml_Object_o_parent_character_Create_0(s, o);        /* event_inherited() */
    grey_reset(slot(s, true), s);
    slot(s, true)->entry_t = ENTRY_T;
    slot(s, true)->glitch_t = 10;
    iset(s, &g_VAR_parent, 0);
    iset_b(s, &g_VAR_local_runleft, false);
    iset(s, &g_VAR_combo_next, -1);
    iset_b(s, &g_VAR_combo_nextcombo, false);
    iset_b(s, &g_VAR_has_voice, false);
    iset_b(s, &g_VAR_is_speaking, false);
    iset(s, &g_VAR_current_voice_audio, -1);
    iset(s, &g_VAR_img_voice, 0);
    iset_str(s, &g_VAR_char_name, "Grey");
    iset(s, &g_VAR_stats_hp, 2200);
    iset(s, &g_VAR_stats_dmg, 47);
    iset(s, &g_VAR_stats_walkspd, 3.6);
    iset(s, &g_VAR_stats_airdashspd, 9.4);
    iset(s, &g_VAR_stats_runspd, 8.4);
    iset(s, &g_VAR_stats_jumpforce, -7.2);
    iset(s, &g_VAR_snd_jump, SND_JUMP);
    iset(s, &g_VAR_snd_transform, SND_JUMP);
    iset(s, &g_VAR_hp_draw_y, 68);
    iset(s, &g_VAR_hp_width, 40);
    iset(s, &g_VAR_hp_height, 5);
    iset(s, &g_VAR_energy_skill1_cost, 55);
    iset(s, &g_VAR_energy_skill2_cost, 50);
    iset(s, &g_VAR_spr_stand, g_grey_spr[GR_M_STAND]);
    iset(s, &g_VAR_spr_crouch, g_grey_spr[GR_M_CROUCH]);
    iset(s, &g_VAR_spr_charge, g_grey_spr[GR_M_CHARGE]);
    iset(s, &g_VAR_spr_run, g_grey_spr[GR_M_RUN]);
    iset(s, &g_VAR_spr_walk, g_grey_spr[GR_M_WALK]);
    iset(s, &g_VAR_spr_jump, g_grey_spr[GR_M_JUMP]);
    iset(s, &g_VAR_spr_fall, g_grey_spr[GR_M_FALL]);
    iset(s, &g_VAR_spr_defend, g_grey_spr[GR_M_DEFEND]);
    iset(s, &g_VAR_spr_fallen, g_grey_spr[GR_M_FALLEN]);
    iset(s, &g_VAR_spr_hurt, g_grey_spr[GR_M_HURT]);
    iset(s, &g_VAR_spr_hurtup, g_grey_spr[GR_M_HURTUP]);
    iset(s, &g_VAR_spr_hurtdown, g_grey_spr[GR_M_HURTDOWN]);
    iset(s, &g_VAR_spr_transform, -1);
    iset(s, &g_VAR_spr_mask_stand, SPR_MASK_STAND);
    iset(s, &g_VAR_spr_mask_crouch, SPR_MASK_CROUCH);
    bset(s, &g_VAR_sprite_index, g_grey_spr[GR_M_STAND]);
    bset(s, &g_VAR_mask_index, SPR_MASK_STAND);
    bset(s, &g_VAR_image_speed, 0.25);
    bset_i(s, &g_VAR_alarm, 0, 1);
    iset(s, &g_VAR_imgindex_aura, 0);
    iset(s, &g_VAR_img_index_aura, 8);
    iset(s, &g_VAR_ef_img_aura, 2);
}
void gml_Object_o_grey_Alarm_0(CInstance *s, CInstance *o) {
    (void)o;
    if (!parent_ok(s) || g_grey_spr[GR_FACE] < 0) return;
    pset(s, &g_VAR_spr_face, g_grey_spr[GR_FACE]);
}
void gml_Object_o_grey_Destroy_0(CInstance *s, CInstance *o) {
    Grey *j = slot(s, false);
    if (j) { if (j->sp_on) special_end(s, j); j->inst = 0; }
    gml_Object_o_parent_character_Destroy_0(s, o);
}

/* not attacks: once every opponent is down he does his victory (and holds its last pose); now and
   then at rest he spins up a glitch sword. Both only while he stands still; anything else cancels. */
#define WIN_DELAY 40
#define IDLE_EVERY 420
static int pose_override(CInstance *s, Grey *j, int src, GPose *target) {
    bool calm = src == 10;                                  /* standing still on the ground */
    if (calm && enemies_beaten(s)) {
        if (j->pz_tl != GT_WIN && ++j->win_wait >= WIN_DELAY) { j->pz_tl = GT_WIN; j->pz_t = 0; j->pz_ev = 0; }
    } else {
        j->win_wait = 0;
        if (j->pz_tl == GT_WIN) j->pz_tl = -1;              /* a new round, or he moved */
    }
    if (calm && j->pz_tl < 0 && j->idle_t % IDLE_EVERY == IDLE_EVERY - 120) { j->pz_tl = GT_IDLE; j->pz_t = 0; j->pz_ev = 0; }
    if (j->pz_tl < 0) return src;
    if (!calm) { j->pz_tl = -1; return src; }
    int dur = k_gtl[j->pz_tl].dur;
    j->pz_t++;
    tl_sample(j->pz_tl, (float)(j->pz_t < dur ? j->pz_t : dur), target);
    run_events(s, j, j->pz_tl, j->pz_t, &j->pz_ev, sx_(s), sy_(s), facing(s));
    int out = 300 + j->pz_tl;
    if (j->pz_t >= dur && j->pz_tl == GT_IDLE) j->pz_tl = -1;   /* (the victory pose holds) */
    return out;
}

void gml_Object_o_grey_Step_0(CInstance *s, CInstance *o) {
    Grey *j = slot(s, true);
    g_grey_tick++;
    j->aura_t++;
    if (j->fail_t > 0) j->fail_t--;
    if (j->glitch_t > 0) j->glitch_t--;
    bool pok = parent_ok(s);
    GPose target; int src;
    if (j->lava_on) {                                          /* the burning world goes on */
        j->lava_t++;
        if (j->lava_t % 30 == 0 && pok) hide_scenery(s, fighters_depth(s));   /* (new scenery) */
        lava_ambient(s, j);
    }

    if (j->sp_on) {
        if (!pok) { special_end(s, j); base_pose(GPZ_STAND, &target); src = 0; }
        else if (j->sp_kind == SPK_ARROW) { ia_step(s, j, &target); src = 200 + (j->sp_t >= IA_LAND); }
        else { special_step(s, j, &target); src = 200 + (j->sp_t >= MF_LAND); }
    } else {
        if (pok && !is_cpu(s)) bow_input(s, j);                /* double-tap shield: the bow stance */
        if (pok && j->move == MOVE_NONE && (special_pressed(s) || cpu_wants_special(s))) {
            if (is_cpu(s)) j->bow = (int)(rnd() & 1);         /* the CPU picks either ultimate */
            start_special(s, j);
        }
        if (j->sp_on) { base_pose(GPZ_CHARGE, &target); src = 200; }
        else {
            RValue ret = rv_undef();
            gml_Script_scr_plr_step(s, o, &ret, 0, 0);       /* the game's movement / input framework */
            rv_free(&ret);
            if (pok && j->move != MOVE_NONE && (pget(s, &g_VAR_is_hurt) > 0.5 || pget(s, &g_VAR_is_fallen) > 0.5))
                end_move(s, j);                               /* interrupted */
            if (j->move != MOVE_NONE) move_step(s, j);
            if ((j->move == GT_AA || j->move == GT_AA2) && j->t > 4 && pok && pget(s, &g_VAR_keyp_action1) > 0.5)
                iset_b(s, &g_VAR_combo_nextcombo, true);      /* attack again in the air: the chain goes on */
            if (j->move != MOVE_NONE) { tl_sample(j->move, (float)j->t, &target); src = 100 + j->move; }
            else src = loco_pose(s, j, &target);
            if (j->move == MOVE_NONE) src = pose_override(s, j, src, &target);
            if (j->bow && src < 100 && ((target.flags >> 2) & 7) == 0) {   /* the bow stance: the bow in his hand */
                target.flags = (target.flags & 3) | (GW_BOW << 2);
                target.a[GA_W] = -90;
            }
        }
    }
    if (src != j->src && !(src >= 100 && src < 200 && j->src == src)) {
        if (!(src >= 100 && src < 200)) crossfade(j, BLEND_N);   /* (moves set their own, shorter blend) */
        j->src = src;
    }
    if (j->blend_t > 0) {
        float u = 1 - (float)j->blend_t / (BLEND_N + 1);
        lerp_pose(&j->from, &target, ease(2, u), &j->drawn);
        j->drawn.flags = target.flags;
        j->blend_t--;
    } else j->drawn = target;

    /* motion trails: every 2nd frame while a move asks for them, every 4th while running */
    float x = sx_(s), y = sy_(s), f = facing(s);
    if (((j->drawn.flags & 2) && g_grey_tick % 2 == 0) || (src == 8 && g_grey_tick % 4 == 0))
        ghost_push(j, &j->drawn, x, y, f, (g_grey_tick / 2) % 2 ? C_CYAN : C_MAG);

    trails_push(j, &j->drawn, x, y, f);
    if (j->entry_t > 0) {                                      /* materialising: pixels rush in to build him */
        if (j->entry_t == ENTRY_T) {
            fx_at(j, GR_RING, x, y - 1, 0.8f, 0.8f, 0, 2, 1, C_CYAN);
            fx_kind(j, GF_SPAWN, x, y, 1.2f, f);
        }
        for (int k = 0; k < 3; k++) {
            float ox = frand(-34, 34), oy = frand(-70, 10);
            Part *q = part(j, PK_PIXEL, x + ox, y - 30 + oy, -ox / 9.0f, -oy / 9.0f, 9, frand(1.5f, 3), glitch_col());
            if (q) { q->g = 0; q->drag = 1; }
        }
        if (j->entry_t % 8 == 0) j->glitch_t = 4;
        j->entry_t--;
    }
    if (src == 2 && j->prev_loco != 2) {                        /* hit: he glitches and sheds pixels */
        if (j->glitch_t < 8) j->glitch_t = 8;
        burst(j, PK_PIXEL, x, y - 34, 10, 3.2f, 24, 2.2f, glitch_col());
        fx_kind(j, GF_GLITCH, x, y - 34, 0.7f, f);
    }
    if (src == 1 && j->prev_loco != 1) {                        /* knocked down: a bigger crash */
        if (j->glitch_t < 12) j->glitch_t = 12;
        burst(j, PK_PIXEL, x, y - 14, 18, 4.0f, 30, 2.4f, glitch_col());
        burst(j, PK_BIT, x, y - 14, 6, 1.5f, 36, 1, C_CYAN);
        fx_at(j, GR_RING, x, y - 1, 0.6f, 0.6f, 0, 2, 1, C_MAG);
        for (int k = 0; k < 3; k++) part(j, PK_SMOKE, x + frand(-12, 12), y - 2, frand(-1.2f, 1.2f), -0.4f, 26, 6, RGB(150, 150, 160));
    }
    if (src == 11) {                                           /* air dash: he blinks, then streaks */
        if (j->prev_loco != 11) {
            if (j->glitch_t < 6) j->glitch_t = 6;
            fx_kind(j, GF_GLITCH, x - f * 10, y - 30, 0.8f, f);
            burst(j, PK_PIXEL, x - f * 6, y - 30, 12, 3.0f, 20, 2.0f, glitch_col());
        }
        if (g_grey_tick % 2 == 0) ghost_push(j, &j->drawn, x, y, f, (g_grey_tick / 2) % 2 ? C_CYAN : C_MAG);
        part(j, PK_STREAK, x - f * 8, y - frand(14, 46), -f * 6, 0, 8, 1.4f, C_WHITE);
        part(j, PK_PIXEL, x - f * 6, y - frand(10, 50), -f * frand(0.5f, 2), frand(-0.5f, 0.5f), 16, 2, glitch_col());
    } else if (j->prev_loco == 11)                             /* and lands out of it in a puff of pixels */
        burst(j, PK_PIXEL, x, y - 30, 8, 2.0f, 16, 1.8f, glitch_col());
    if (j->prev_loco == 1 && src != 1 && src != 2) {           /* up from a knockdown: he reboots */
        if (j->glitch_t < 8) j->glitch_t = 8;
        for (int k = 0; k < 18; k++) {
            float ox = frand(-30, 30), oy = frand(-60, 0);
            Part *q = part(j, PK_PIXEL, x + ox, y - 26 + oy, -ox / 6.0f, -oy / 6.0f, 7, frand(1.5f, 3), glitch_col());
            if (q) { q->g = 0; q->drag = 1; }
        }
        fx_kind(j, GF_SPAWN, x, y, 0.8f, f);
    }
    if (src == 8 && j->prev_loco != 8) {                       /* breaking into a run: a glitch kick-off */
        fx_kind(j, GF_GLITCH, x - f * 8, y - 28, 0.6f, f);
        for (int k = 0; k < 4; k++) part(j, PK_STREAK, x - f * 6, y - frand(12, 48), -f * 7, 0, 8, 1.4f, k & 1 ? C_CYAN : C_MAG);
        part(j, PK_SMOKE, x - f * 8, y - 2, -f * 1.2f, -0.3f, 18, 5, RGB(150, 150, 160));
    }
    j->prev_loco = src;
    if (pok && pget(s, &g_VAR_is_dead) > 0.5) {                /* KO: deleted, pixel by pixel */
        if (j->dead_t < 10000) j->dead_t++;
        if (j->dead_t <= DEAD_FADE) {
            for (int k = 0; k < 2; k++)
                part(j, PK_PIXEL, x + frand(-14, 14), y - frand(0, 30), frand(-0.4f, 0.4f), -frand(0.8f, 2.0f), 34, frand(1.5f, 2.6f), glitch_col());
            if (j->dead_t % 4 == 0) part(j, PK_BIT, x + frand(-12, 12), y - frand(0, 24), 0, -1.2f, 40, 1, C_CYAN);
            if (j->dead_t % 10 == 1) j->glitch_t = 4;
        }
    } else j->dead_t = 0;
    bool air = on_air(s);
    if (!j->sp_on) {
        if (j->was_air && !air) {                              /* landing: dust and a ring */
            for (int k = 0; k < 5; k++) part(j, PK_SMOKE, x + frand(-10, 10), y - 2, frand(-1.6f, 1.6f), -frand(0.2f, 0.6f), 26, 6, RGB(150, 150, 160));
            fx_at(j, GR_RING, x, y - 1, 0.5f, 0.5f, 0, 2, 1, RGB(120, 190, 235));
        }
        if (!j->was_air && air && sget(s, &g_VAR_vspeed) < -2)  /* take-off */
            for (int k = 0; k < 3; k++) part(j, PK_SMOKE, x + frand(-6, 6), y - 1, frand(-1, 1), -0.3f, 20, 5, RGB(150, 150, 160));
    }
    j->was_air = air;
    if (src == 8 && g_grey_tick % 2 == 0)                      /* running: speed lines */
        part(j, PK_STREAK, x - f * 10 + frand(-4, 4), y - frand(10, 50), -f * 4, 0, 8, 1.2f, (rnd() & 1) ? C_CYAN : C_MAG);
    if ((j->drawn.flags & 2) && g_grey_tick % 2 == 0)
        part(j, PK_STREAK, x + frand(-8, 8), y - frand(8, 56), -f * 5, 0, 7, 1.4f, C_WHITE);
    if (src == 7) {                                            /* charging: data pouring off him */
        if (g_grey_tick % 2 == 0) part(j, PK_BIT, x + frand(-14, 14), y - frand(0, 40), 0, -frand(0.8f, 1.8f), 30, 1, (rnd() & 1) ? C_CYAN : C_MAG);
        if (g_grey_tick % 9 == 0) bolt(j, x + frand(-20, 20), y - frand(40, 70), x + frand(-20, 20), y - frand(0, 30), 4, 1.5f, C_CYAN);
        if (g_grey_tick % 16 == 0) fx_at(j, GR_RING, x, y - 1, 0.55f, 0.55f, 0, 2, 1, C_CYAN);   /* pulses at his feet */
        if (g_grey_tick % 3 == 0) {                            /* and data raining down round him */
            Part *q = part(j, PK_BIT, x + (float)((int)(rnd() % 7) - 3) * 7, y - frand(60, 80), 0, frand(1.5f, 2.5f), 26, 1, RGB(120, 255, 180));
            if (q) { q->g = 0; q->drag = 1; }
        }
    }
    if (j->glitch_t > 0 && g_grey_tick % 2 == 0)
        part(j, PK_PIXEL, x + frand(-12, 12), y - frand(6, 58), frand(-2, 2), frand(-1, 1), 14, frand(1.5f, 3), glitch_col());
    if (src == 10 && g_grey_tick % 23 == 0)                    /* idle: a stray bit now and then */
        part(j, PK_BIT, x + frand(-10, 10), y - frand(20, 50), 0, -0.5f, 40, 1, C_CYAN);
    clones_step(s, j);
    proj_step(s, j);
    spikes_step(s, j);
    fx_step(j);
    parts_step(j); bolts_step(j); marks_step(j);
    if (j->scr_t > 0) j->scr_t--;
    if (!j->sp_on) {
        RValue v[2] = { rv_real(0.6), rv_real(1) };
        RValue *args[2] = { &v[0], &v[1] };
        RValue r2 = rv_undef();
        gml_Script_scr_char_charge_effect(s, o, &r2, 2, args);
        rv_free(&r2);
    }
}

void gml_Object_o_grey_Draw_0(CInstance *s, CInstance *o) {
    (void)o;
    Grey *j = slot(s, true);
    g_blend_cur = -1;
    float x = sx_(s), y = sy_(s), f = facing(s);
    float al = (float)sget(s, &g_VAR_image_alpha);
    if (!(al > 0.01f) || al > 1) al = 1;
    float vis = 1;                                           /* materialising / dissolving */
    if (j->entry_t > 0) vis = (1 - (float)j->entry_t / ENTRY_T) * ((g_grey_tick & 2) ? 1.0f : 0.6f);
    if (j->dead_t > 0) { float d = 1 - (float)j->dead_t / DEAD_FADE; vis *= d < 0.35f ? 0.35f : d; }
    if (j->lava_on && j->lava_drawn != j->aura_t) draw_lava(s, j);   /* Draw Begin didn't run: draw it here */
    if (j->sp_on) { if (j->sp_kind == SPK_ARROW) ia_draw_world(s, j); else mf_draw_sky(s, j); }   /* the rift and Moon / the arrow's fire */
    marks_draw(s, j);                                        /* scorch and frost on the floor */
    if (!on_air(s) && !j->sp_on)                            /* a soft shadow */
        spr(s, GR_SHAPE, 1, x, y + 1, 0.55f, 0.1f, 0, 0, 0.25f * al * vis);
    for (int i = 0; i < N_SPIKE; i++) {                      /* ice spikes behind */
        Spike *k = &j->sp[i];
        if (k->on) spr(s, GR_SPIKE, (float)(k->t / 3), k->x, k->y + 1, k->f * k->size, k->size, 0, C_WHITE, 1);
    }
    blend(s, 1);
    for (int i = 0; i < N_GHOST; i++) {                      /* afterimages */
        Ghost *g = &j->gh[i];
        if (g->on) draw_stick(s, &g->p, g->x, g->y, g->f, g->col, g->col, g->col, 0.32f * (1 - g->t / 12.0f), 0);
    }
    trails_draw(s, j, (j->move != MOVE_NONE || j->sp_on) ? 1.0f : 0.7f);   /* ribbons where limbs swept */
    blend(s, 0);
    /* clones: holograms. Drawn layer by layer across all of them, so the blend mode changes only a
       few times a frame instead of several times per clone */
    GPose cp[N_CLONE]; float cxs[N_CLONE], cas[N_CLONE]; const Clone *cls[N_CLONE]; int nc = 0;
    for (int i = 0; i < N_CLONE; i++) {
        const Clone *c = &j->cl[i];
        if (!c->on) continue;
        tl_sample(c->tl, (float)c->t, &cp[nc]);
        float ca = c->fade ? 0.85f * (1 - c->fade / 8.0f) : (c->t < 4 ? 0.85f * c->t / 4.0f : 0.85f);
        ca *= 0.8f + 0.2f * (float)((g_grey_tick + i) % 4 != 0);           /* flicker */
        float jit = (c->fade || c->t < 4) ? frand(-2, 2) : 0;
        cxs[nc] = c->x + c->f * cp[nc].mx + jit; cas[nc] = ca; cls[nc] = c; nc++;
    }
    if (nc) {
        blend(s, 1);
        g_extra_w = 7.0f;                                     /* their glow */
        for (int k = 0; k < nc; k++) draw_stick(s, &cp[k], cxs[k], cls[k]->y, cls[k]->f, C_CYAN, C_CYAN, C_CYAN, 0.3f * cas[k], 0);
        g_extra_w = 0;
        for (int k = 0; k < nc; k++) {                       /* the RGB split */
            draw_stick(s, &cp[k], cxs[k] - 1.6f, cls[k]->y, cls[k]->f, C_CYAN, C_CYAN, C_CYAN, cas[k] * 0.45f, 0);
            draw_stick(s, &cp[k], cxs[k] + 1.6f, cls[k]->y, cls[k]->f, C_MAG, C_MAG, C_MAG, cas[k] * 0.45f, 0);
        }
        blend(s, 0);
        for (int k = 0; k < nc; k++) draw_stick(s, &cp[k], cxs[k], cls[k]->y, cls[k]->f, C_CLONE, C_CLONEB, C_CLONEL, cas[k], 1);
        blend(s, 1);
        for (int k = 0; k < nc; k++)                          /* scanlines running down them */
            for (int l = 0; l < 3; l++) {
                float sy = cls[k]->y - 62 + (float)(((g_grey_tick * 2 + l * 21) % 66));
                spr(s, GR_SHAPE, 0, cxs[k], sy, 30 / 32.0f, 1 / 32.0f, 0, C_CYAN, 0.35f * cas[k]);
            }
        blend(s, 0);
    }
    /* Grey: a neon glow round him, then the stickman, then the glitch */
    float split = j->glitch_t > 0 ? 1.5f + frand(0, 3.0f) : (vis < 0.99f ? 2.0f : 0);
    al *= vis;
    float jit = j->glitch_t > 0 && (g_grey_tick % 3 == 0) ? frand(-2.5f, 2.5f) : 0;
    if (j->hitstop > 0) jit = frand(-1.5f, 1.5f);
    float glow = j->sp_on ? 0.5f : j->src == 7 ? 0.36f + 0.12f * sinf_(g_grey_tick * 0.4f)
               : (j->move != MOVE_NONE ? 0.3f : 0.1f + 0.04f * sinf_(j->aura_t * 0.055f));
    int gcol = (g_grey_tick % 40 < 3 || (j->glitch_t > 0 && (g_grey_tick & 1))) ? C_MAG : C_CYAN;
    blend(s, 1);
    g_extra_w = 9.0f;                                        /* a wide faint halo */
    draw_stick(s, &j->drawn, x + jit, y, f, gcol, gcol, gcol, glow * 0.4f * al, 0);
    g_extra_w = 4.5f;                                        /* and a tighter, brighter rim */
    draw_stick(s, &j->drawn, x + jit, y, f, gcol, gcol, gcol, glow * al, 0);
    g_extra_w = 0;
    blend(s, 0);
    if (j->src == 6) {                                      /* guarding: the hex barrier */
        V2 J[12]; fk(&j->drawn, x, y, f, J);
        spr(s, GR_HEX, (float)((g_grey_tick / 4) % 4), J[7].x + f * 4, y + 2, f * 0.8f, 0.9f, 0, C_WHITE, 0.75f * al);
        blend(s, 1);
        spr(s, GR_HEX, (float)((g_grey_tick / 4) % 4), J[7].x + f * 4, y + 2, f * 0.9f, 1.0f, 0, C_CYAN, 0.25f * al);
        blend(s, 0);
    }
    if (j->src == 7 && g_grey_tick % 3 == 0)                /* charging: bits of glitch fly off */
        fx_at(j, GR_GLITCH, x + frand(-14, 14), y - frand(10, 60), 0.35f, 0.35f, 0, 2, 0, C_WHITE);
    draw_glitched(s, &j->drawn, x + jit, y, f, C_FILL, C_BACK, C_LINE, al, split);
    if (j->glitch_t > 0) {                                  /* tear bars and glitch blocks across him */
        blend(s, 1);
        for (int k = 0; k < 3; k++)
            spr(s, GR_SHAPE, 0, x + frand(-6, 6), y - frand(8, 58), frand(24, 54) / 32.0f, frand(1, 2.4f) / 32.0f, 0, glitch_col(), 0.8f);
        blend(s, 0);
        if (g_grey_tick % 2 == 0)
            spr(s, GR_GLITCH, (float)(g_grey_tick % 8), x + frand(-10, 10), y - frand(12, 56), 0.4f, 0.4f, 0, C_WHITE, 0.9f);
    }
    /* projectiles: all their glows first (additive), then the projectiles */
    for (int i = 0; i < N_PROJ; i++) {
        Proj *p = &j->pr[i];
        if (!p->on) continue;
        blend(s, 1);
        spr(s, GR_SHAPE, 1, p->x, p->y, 0.7f, 0.7f, 0, p->kind == GP_FIRE ? C_FIRE : p->kind == GP_SHARD ? C_ICE : C_CYAN, 0.35f);
    }
    for (int i = 0; i < N_PROJ; i++) {
        Proj *p = &j->pr[i];
        if (p->on && p->kind != GP_FIRE && p->kind != GP_SHARD) spr(s, GR_SPAWN, 2, p->x, p->y + 30, 0.5f, 0.4f, 0, C_CYAN, 0.4f);
    }
    blend(s, 0);
    for (int i = 0; i < N_PROJ; i++) {
        Proj *p = &j->pr[i];
        if (!p->on) continue;
        float ang = -atan2f_(p->vy, p->vx) * 57.29578f;
        if (p->kind == GP_FIRE) spr(s, GR_FIRE, (float)((p->t / 2) % 8), p->x, p->y, 0.5f, 0.5f, ang, C_WHITE, 1);
        else if (p->kind == GP_SHARD) spr(s, GR_SHARD, (float)((p->t / 2) % 4), p->x, p->y, 1, 1, 0, C_WHITE, 1);
        else spr(s, GR_SPEAR, (float)((p->t / 2) % 4), p->x, p->y, 1, 1, ang, C_WHITE, 1);
    }
    blend(s, 1);
    bolts_draw(s, j);                                        /* lightning */
    parts_draw(s, j, 1);                                     /* sparks, embers, frost, streaks, bits */
    blend(s, 0);
    parts_draw(s, j, 0);                                     /* pixels, smoke, ice chips */
    for (int add = 0; add < 2; add++)                        /* one-shot effects: normal, then additive on top */
        for (int i = 0; i < N_FX; i++) {
            Fx *e = &j->fx[i];
            if (!e->on || (e->add != 0) != add) continue;
            blend(s, add);
            spr(s, e->a, (float)(e->t / e->tpf), e->x, e->y, e->xs, e->ys, e->rot, e->col, 1);
        }
    blend(s, 0);
    if (j->fail_t > 0)
        spr(s, GR_ERROR, (float)(j->fail_t % 4), x, y - 76, 0.6f, 0.6f, 0, 0x5555FF, j->fail_t / 24.0f);
}

/* Draw Begin: runs before any layer or instance draws, i.e. behind everything */
void gml_Object_o_grey_Draw_72(CInstance *s, CInstance *o) {
    (void)o;
    Grey *j = slot(s, false);
    if (!j || !j->lava_on) return;
    draw_lava(s, j);
}

/* GUI layer: screen tears on his heaviest blows, and the MOONFALL cinematic */
void gml_Object_o_grey_Draw_64(CInstance *s, CInstance *o) {
    (void)o;
    Grey *j = slot(s, false);
    if (!j || (!j->sp_on && j->scr_t <= 0)) return;
    g_blend_cur = -1;
    float gw = (float)legacy0(s, &g_FUNC_display_get_gui_width);
    float gh = (float)legacy0(s, &g_FUNC_display_get_gui_height);
    if (!(gw >= 16) || !(gh >= 16) || gw > 20000 || gh > 20000) return;
    if (!j->sp_on) {                                         /* a heavy blow: the picture tears for a moment */
        float k = j->scr_t / 5.0f;
        blend(s, 1);
        for (int b = 0; b < 4; b++) {
            float yy = frand(0, gh - 10), hh = frand(2, 12);
            rect(frand(-30, 0), yy, gw + frand(0, 30), yy + hh, b % 2 ? C_CYAN : C_MAG, 0.16f * k);
        }
        blend(s, 0);
        if (j->scr_t >= 4) rect(0, 0, gw, gh, C_WHITE, 0.14f);
        YYGML_draw_set_colour(C_WHITE); YYGML_draw_set_alpha(1);
        return;
    }
    int t = j->sp_t;
    int dur = j->sp_kind == SPK_ARROW ? IA_DUR : SPC_DUR;
    if (j->sp_kind == SPK_ARROW) ia_draw_gui(s, j, gw, gh);
    else {
    /* the white-out between space and the ground: it builds as the planet's glow fills the frame */
    float white = t < MF_FLASH - 12 ? 0 : t < MF_FLASH + 6 ? ease_io(lin01(t, MF_FLASH - 12, MF_FLASH + 6))
                : t < MF_LAND ? 1 : 1 - ease_io(lin01(t, MF_LAND, MF_LAND + 18));
    if (t >= MF_ASC && t < MF_LAND && white < 0.999f) mf_draw_space(s, j, gw, gh);
    if (t >= MF_RIFT && t < MF_MOON + 14) {                  /* the tear in the sky jolts the picture */
        blend(s, 1);
        for (int b = 0; b < 3; b++) {
            float yy = frand(0, gh - 12), hh = frand(2, 10);
            rect(frand(-30, 0), yy, gw + frand(0, 30), yy + hh, b == 1 ? C_MAG : C_CYAN, t >= MF_MOON ? 0.2f : 0.1f);
        }
        blend(s, 0);
    }
    if (white > 0) rect(0, 0, gw, gh, t < MF_LAND ? RGB(255, 246, 232) : RGB(255, 236, 205), white);
    }
    float in = ease_io(lin01(t, 0, 16)) * (1 - ease_io(lin01(t, dur - 24, dur)));
    float bar = gh * 0.1f * in;                              /* letterbox */
    rect(0, 0, gw, bar, 0, in);
    rect(0, gh - bar, gw, gh, 0, in);
    YYGML_draw_set_colour(C_WHITE);
    YYGML_draw_set_alpha(1);
}

/* ------------------------------------------------------------------------------------------ */
/* INFERNO ARROW for the game's own custom characters                                          */
/*   Any fighter made in the game's Character Creation that holds the bow (weapon 62, the last  */
/*   one in the creator's list) fires INFERNO ARROW with shield + skill on a full bar, instead  */
/*   of its usual special. build/droidpatch.py points o_plr_custom's Step and Draw events at the */
/*   functions below, which run the game's original events except while the cinematic holds    */
/*   the fighter, and gives it a Draw GUI event (Grey's, which draws the cinematic).            */
/* ------------------------------------------------------------------------------------------ */
#define CUST_BOW 62
void gml_Object_o_plr_custom_Step_0(CInstance *, CInstance *);
void gml_Object_o_plr_custom_Draw_0(CInstance *, CInstance *);

static Grey *cust_find(CInstance *s) {
    for (int i = 0; i < 2; i++) if (g_cust[i].inst == s) return &g_cust[i];
    return 0;
}
static bool cust_has_bow(CInstance *s) {
    double w = sget(s, &g_VAR_img_wp);
    return w > CUST_BOW - 0.5 && w < CUST_BOW + 0.5;
}
static Grey *cust_new(CInstance *s) {
    for (int i = 0; i < 2; i++) if (g_cust[i].inst == s || !g_cust[i].inst || !g_cust[i].sp_on) { grey_reset(&g_cust[i], s); return &g_cust[i]; }
    return 0;
}
/* online / LAN (global.game_gm == 2): each phone simulates the fight from the button presses and the netcode
   compares checksums, so a phone without this mod would play the normal special, disagree, and drop the match
   for both players. Until both phones can tell each other they have the mod, online keeps the game's own move. */
static bool cust_online(void) {
    RValue *gm = g_pGlobal ? var_slot_r(g_pGlobal, g_VAR_game_gm.id) : 0;
    return gm && (int)rv_num(gm) == 2;
}
static bool cust_try_arrow(CInstance *s) {
    if (cust_online()) return false;
    if (!parent_ok(s) || !cust_has_bow(s)) return false;
    bool human = pget(s, &g_VAR_keyp_special) > 0.5 && pget(s, &g_VAR_key_defend) > 0.5;
    bool cpu = is_cpu(s) && pget(s, &g_VAR_keyp_special) > 0.5;
    if (!(human || cpu) || !special_ready(s)) return false;
    double e = pget(s, &g_VAR_plr_energy), emax = pget(s, &g_VAR_plr_maxenergy);
    double need = emax > 0 ? (emax < 100 ? emax : 100) : 100;
    if (e + 0.001 < need) return false;                      /* not a full bar: the game's own controls */
    int tid = -1;
    CInstance *t = nearest_enemy(s, &tid, 2000, 800);
    if (!t) return false;
    grey_load_assets(s);                                     /* (once per run) */
    Grey *j = cust_new(s);
    if (!j) return false;
    j->cust = 1;
    pset_b(s, &g_VAR_keyp_special, false);
    pset(s, &g_VAR_plr_energy, e - need);
    j->sp_on = 1; j->sp_kind = SPK_ARROW; j->sp_t = 0; j->hit_done = 0; j->move = MOVE_NONE;
    j->tgt_id = tid; j->tgt_x = (float)sget(t, &g_VAR_x); j->tgt_y = (float)sget(t, &g_VAR_y);
    j->dir = j->tgt_x >= sx_(s) ? 1.0f : -1.0f;
    bset(s, &g_VAR_image_xscale, j->dir);
    pset_b(s, &g_VAR_is_attacking, true);
    pset_b(s, &g_VAR_can_gethurt, false);
    j->old_depth = sget(s, &g_VAR_depth); j->depth_saved = 1;
    bset(s, &g_VAR_depth, -15000);                          /* its GUI draws over the HUD */
    bset(s, &g_VAR_hspeed, 0); bset(s, &g_VAR_vspeed, 0);
    double ch = iget(s, &g_VAR_spr_charge);
    if (ch > 0) bset(s, &g_VAR_sprite_index, ch);           /* the charging pose while the fire gathers */
    return true;
}
static void cust_fx_step(Grey *j) { fx_step(j); parts_step(j); bolts_step(j); marks_step(j); }

void cust_step(CInstance *s, CInstance *o) {
    Grey *j = cust_find(s);
    if (j && j->sp_on) {
        g_grey_tick++; j->aura_t++;
        if (j->glitch_t > 0) j->glitch_t--;
        if (!parent_ok(s)) special_end(s, j);
        else { GPose pose; ia_step(s, j, &pose); }
        cust_fx_step(j);
        if (j->sp_on) return;                                 /* the cinematic holds the fighter */
    } else if (j) cust_fx_step(j);                           /* (its embers and smoke settle) */
    if (cust_try_arrow(s)) return;
    gml_Object_o_plr_custom_Step_0(s, o);
}
void cust_draw(CInstance *s, CInstance *o) {
    gml_Object_o_plr_custom_Draw_0(s, o);
    Grey *j = cust_find(s);
    if (!j) return;
    g_blend_cur = -1;
    marks_draw(s, j);
    if (j->sp_on) ia_draw_world(s, j);
    blend(s, 1);
    bolts_draw(s, j);
    parts_draw(s, j, 1);
    blend(s, 0);
    parts_draw(s, j, 0);
    for (int add = 0; add < 2; add++)
        for (int i = 0; i < N_FX; i++) {
            Fx *e = &j->fx[i];
            if (!e->on || (e->add != 0) != add) continue;
            blend(s, add);
            spr(s, e->a, (float)(e->t / e->tpf), e->x, e->y, e->xs, e->ys, e->rot, e->col, 1);
        }
    blend(s, 0);
}
void cust_draw_gui(CInstance *s, CInstance *o) {
    Grey *j = cust_find(s);
    if (j && (j->sp_on || j->scr_t > 0)) gml_Object_o_grey_Draw_64(s, o);
}
