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
 *  special (shield + skill, full bar): SYSTEM CRASH - the screen glitches, clones dash through him
 *            from every side, then Grey brings down a giant glitch blade (huge unblockable hit)
 *
 * Same framework as the other fighters: scr_plr_step drives movement / input, combos run through
 * alarm[3] / alarm[2], hits are o_mask_hit hitboxes.  The framework's sprite_index values are tiny
 * invisible marker strips, one per state, so the game's logic sees normal sprites.
 */
#include "yyc.h"
#include "grey_assets.h"
#include "grey_moves.h"

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
#define BSOD_BLUE RGB(16, 44, 178)

#define PI_F 3.14159265f
#define DEG (PI_F / 180.0f)
#define N_CLONE 8
#define N_PROJ 16
#define N_SPIKE 14
#define N_FX 28
#define N_GHOST 8
#define MOVE_NONE (-1)
#define BLEND_N 6
#define SPC_DUR 176            /* SYSTEM CRASH length */
#define ENTRY_T 40             /* frames he takes to materialise when the match starts */
#define DEAD_FADE 90           /* frames a KO takes to dissolve him (down to a faint ghost) */

typedef struct { float hx, hy, rot, mx; float a[GA_N]; int flags; } GPose;
typedef struct { float x, y; } V2;
typedef struct { int on, tl, t, ev, tint, fade; float x, y, f; } Clone;
typedef struct { int on, kind, t; float x, y, vx, vy, dmg, f, floor_y; } Proj;
typedef struct { int on, t, hit; float x, y, size, vf, dmg, f; } Spike;
typedef struct { int on, t, a, tpf, n, add, col; float x, y, xs, ys, rot; } Fx;
typedef struct { int on, t, col; GPose p; float x, y, f; } Ghost;
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
    /* SYSTEM CRASH */
    int sp_on, sp_t, tgt_id, depth_saved, hit_done; float tgt_x, tgt_y; double old_depth;
} Grey;

static Grey g_grey[4];
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
/* the weapon in his front hand: sword, spear or the giant blade (SYSTEM CRASH) */
static void draw_weapon(CInstance *s, const GPose *p, const V2 *J, float f, float al, int col) {
    int wk = (p->flags >> 2) & 3;
    if (!wk) return;
    V2 d = dir_of(p->a[GA_W], p->rot, f);
    float ang = -atan2f_(d.y, d.x) * 57.29578f;
    int a = wk == 2 ? GR_SPEAR : GR_SWORD;
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
    int wk = (p->flags >> 2) & 3;
    t->on[4] = wk != 0;
    if (wk) {
        V2 d = dir_of(p->a[GA_W], p->rot, f);
        float len = wk == 2 ? 50 : wk == 3 ? 141 : 44;          /* the sprites' tips: spear 50, sword 44 (x3.2 giant) */
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
/* SYSTEM CRASH                                                                                */
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
static void start_special(CInstance *s, Grey *j) {
    pset_b(s, &g_VAR_keyp_special, false);
    double e = pget(s, &g_VAR_plr_energy), emax = pget(s, &g_VAR_plr_maxenergy);
    double need = emax > 0 ? (emax < 100 ? emax : 100) : 100;
    int tid = -1;
    CInstance *t = nearest_enemy(s, &tid, 320, 160);
    if (e + 0.001 < need || !t) { j->fail_t = 24; play(s, SND_WOOSH3, 0.6); return; }
    pset(s, &g_VAR_plr_energy, e - need);
    j->sp_on = 1; j->sp_t = 0; j->hit_done = 0; j->move = MOVE_NONE;
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
#define SPC_STRIKE0 16          /* the clones' strikes: twelve, one every 6 frames */
#define SPC_TELE 98             /* he blinks above him */
#define SPC_SLAM (SPC_TELE + 30)
static void special_step(CInstance *s, Grey *j, GPose *pose) {
    int t = ++j->sp_t;
    bset(s, &g_VAR_hspeed, 0); bset(s, &g_VAR_vspeed, 0);
    if (!j->hit_done) target_frozen(s, j, true);
    float tx = j->tgt_x, ty = j->tgt_y;
    static const float HY[3] = { 0, -42, -20 };
    for (int i = 0; i < 12; i++) {
        float side = (i % 2 ? 1.0f : -1.0f) * j->dir, dy = HY[i % 3], dist = 64 + 10 * (i % 3);
        if (t == SPC_STRIKE0 + i * 6) {                     /* from both sides, high and low */
            spawn_clone(j, GT_CL_SC_STRIKE, tx + side * dist, ty + dy, -side, GC_GLITCH);
            if (i % 3 == 0) play_c(s, GS_CLONE, 0.85 + 0.04 * i);
        }
        if (t == SPC_STRIKE0 + i * 6 + 8) {                 /* each strike brings an element */
            float hx = tx, hy = ty - 30 + dy * 0.4f;
            bolt(j, tx + side * dist, ty + dy - 30, hx, hy, 6, 2.5f, C_CYAN);
            j->scr_t = 2;
            switch (i % 4) {
            case 0: fx_kind(j, GF_FIREBURST, hx, hy, 0.8f, j->dir); burst(j, PK_EMBER, hx, hy, 14, 3.5f, 36, 2.6f, C_FIRE); break;
            case 1: spawn_spike(j, tx - 12, ty, 1.0f, -1.0f, 0.12f, j->dir); spawn_spike(j, tx + 12, ty, 1.15f, -1.0f, 0.12f, j->dir); break;
            case 2: fx_kind(j, GF_BOLT, hx, ty, 1.0f, j->dir);
                    bolt(j, hx + frand(-10, 10), ty - 200, hx, ty - 6, 10, 4.5f, C_VOLT); burst(j, PK_SPARK, hx, ty - 10, 12, 6, 12, 1.6f, C_VOLT); break;
            case 3: fx_kind(j, GF_GLITCH, hx, hy, 1.5f, j->dir); burst(j, PK_PIXEL, hx, hy, 18, 4.0f, 30, 2.6f, glitch_col()); break;
            }
        }
    }
    if (t == SPC_TELE) {                                    /* up above him */
        float nx = tx - j->dir * 14;
        fx_kind(j, GF_GLITCH, sx_(s), sy_(s) - 30, 1.4f, j->dir);
        burst(j, PK_PIXEL, sx_(s), sy_(s) - 30, 24, 4, 30, 2.4f, C_CYAN);
        if (free_at(s, nx, sy_(s))) bset(s, &g_VAR_x, nx);
        fx_kind(j, GF_SPAWN, sx_(s), sy_(s), 1.6f, j->dir);
        trails_clear(j);
        j->glitch_t = 12;
    }
    if (t >= SPC_TELE) {
        int ft = t - SPC_TELE;
        tl_sample(GT_SP_FINALE, (float)ft, pose);
        if (ft == 10) play(s, SND_BALL_CHARGE, 0.8);
        if (ft == 29) play(s, SND_WOOSH3, 0.7);
        if (ft >= 8 && ft < 30) {                           /* the giant blade charges: energy pours up into it */
            float bx = sx_(s) + frand(-30, 30), by = sy_(s) - 96 - 60;
            if (ft % 2 == 0) part(j, PK_STREAK, sx_(s) + frand(-40, 40), sy_(s) - frand(0, 40), 0, -6, 8, 1.4f, C_CYAN);
            if (ft % 4 == 0) bolt(j, sx_(s), sy_(s) - 110, bx, by, 4, 2.0f, C_CYAN);
            if (ft % 3 == 0) part(j, PK_BIT, sx_(s) + frand(-20, 20), sy_(s) - frand(20, 80), 0, -1.6f, 26, 1, C_CYAN);
        }
    } else {
        base_pose(GPZ_CHARGE, pose);
        pose->hy += sinf_(t * 0.8f) * 0.8f;
        if (t % 5 == 0) j->glitch_t = 3;
        if (t % 2 == 0) part(j, PK_BIT, sx_(s) + frand(-16, 16), sy_(s) - frand(0, 50), 0, -1.2f, 30, 1, (t / 2) % 2 ? C_CYAN : C_MAG);
    }
    if (t == SPC_SLAM && !j->hit_done) {                    /* the giant blade comes down */
        j->hit_done = 1;
        target_frozen(s, j, false);
        CInstance *c = j->tgt_id >= 0 ? YYGML_FindInstance(j->tgt_id) : 0;
        float cx = c ? (float)sget(c, &g_VAR_x) : tx, cy = c ? (float)sget(c, &g_VAR_y) : ty;
        Hit h = { my_dmg(s) * 10.0, j->dir * 9.0, -9.0, 40, 6, 2.0, 2.0, SPR_MASK64, 1, 1, 0, 1, SPR_HIT_3, C_CYAN, 2 };
        spawn_hit(s, cx, cy - 28, &h);
        fx_kind(j, GF_SHATTER, cx, cy - 30, 1.8f, j->dir);
        fx_kind(j, GF_GLITCH, cx, cy - 34, 2.2f, j->dir);
        fx_at(j, GR_RING, cx, cy - 1, 1.2f, 1.2f, 0, 2, 1, C_CYAN);
        fx_at(j, GR_RING, cx, cy - 1, 2.0f, 2.0f, 0, 3, 1, C_MAG);
        fx_at(j, GR_RING, cx, cy - 1, 2.8f, 2.8f, 0, 4, 1, RGB(120, 190, 235));
        fx_kind(j, GF_PILLAR, cx, cy, 1.1f, j->dir);
        fx_at(j, GR_BEAM, cx, cy + 2, 2.6f, 4.0f, 0, 3, 1, C_WHITE);                 /* a pillar of light */
        fx_at(j, GR_STAR, cx, cy - 30, 3.0f, 3.0f, 0, 2, 1, C_WHITE);
        burst(j, PK_PIXEL, cx, cy - 30, 70, 7.5f, 46, 2.8f, C_CYAN);
        burst(j, PK_PIXEL, cx, cy - 30, 30, 6.0f, 40, 2.4f, C_MAG);
        burst(j, PK_SPARK, cx, cy - 30, 28, 9.0f, 16, 2.0f, C_WHITE);
        burst(j, PK_EMBER, cx, cy - 10, 20, 4.0f, 50, 2.8f, C_FIRE);
        burst(j, PK_FROST, cx, cy - 10, 16, 3.0f, 50, 3.2f, C_ICE);
        for (int k = 0; k < 6; k++) {                       /* lightning strikes all round, ice spikes in a ring */
            float ox = (k - 2.5f) * 26;
            bolt(j, cx + ox + frand(-10, 10), cy - 240, cx + ox, cy - 4, 12 + k, 4.0f, k % 2 ? C_VOLT : C_CYAN);
            spawn_spike(j, cx + ox * 1.2f, cy, 0.9f + 0.1f * (k % 3), -2.0f, 0.05f, j->dir);
        }
        for (int k = 0; k < 6; k++) part(j, PK_SMOKE, cx + frand(-20, 20), cy - frand(0, 20), frand(-0.8f, 0.8f), -frand(0.4f, 1.2f), 70, 12, RGB(70, 70, 78));
        mark(j, 0, cx, cy, 70, 240); mark(j, 1, cx, cy, 90, 240);
        camera_shake(3);
        play(s, SND_WINLOSE_IMPACT, 1.0); play(s, SND_STRONG2, 0.7); play(s, SND_EXPLOSION_MEGA, 0.9);
        play_c(s, GS_CRASH, 1.0);
        j->glitch_t = 18;
    }
    if (t > SPC_SLAM && t < SPC_SLAM + 30 && t % 3 == 0)     /* the crater keeps smoking and sparking */
        part(j, PK_SMOKE, tx + frand(-24, 24), ty - frand(0, 10), frand(-0.5f, 0.5f), -1.0f, 60, 10, RGB(70, 70, 78));
    if (t >= SPC_DUR) {
        special_end(s, j);
        bset(s, &g_VAR_image_speed, 0.25);
        bset_i(s, &g_VAR_alarm, 2, 1);
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

    if (j->sp_on) {
        if (!pok) { special_end(s, j); base_pose(GPZ_STAND, &target); src = 0; }
        else { special_step(s, j, &target); src = 200 + (j->sp_t >= SPC_TELE); }
    } else {
        if (pok && j->move == MOVE_NONE && (special_pressed(s) || cpu_wants_special(s))) start_special(s, j);
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

/* GUI layer: screen tears on his heaviest blows, and the SYSTEM CRASH screen */
void gml_Object_o_grey_Draw_64(CInstance *s, CInstance *o) {
    (void)o;
    Grey *j = slot(s, false);
    if (!j || (!j->sp_on && j->scr_t <= 0)) return;
    g_blend_cur = -1;
    float gw = (float)legacy0(s, &g_FUNC_display_get_gui_width);
    float gh = (float)legacy0(s, &g_FUNC_display_get_gui_height);
    if (gw < 16 || gh < 16) return;
    if (!j->sp_on) {                                         /* a heavy blow: the picture tears for a moment */
        float k = j->scr_t / 5.0f;
        blend(s, 1);
        for (int b = 0; b < 4; b++) {
            float yy = frand(0, gh - 10), hh = frand(2, 12);
            YYGML_draw_set_colour(b % 2 ? C_CYAN : C_MAG);
            YYGML_draw_set_alpha(0.16f * k);
            YYGML_draw_rectangle(frand(-30, 0), yy, gw + frand(0, 30), yy + hh, false);
        }
        blend(s, 0);
        if (j->scr_t >= 4) {
            YYGML_draw_set_colour(C_WHITE); YYGML_draw_set_alpha(0.14f);
            YYGML_draw_rectangle(0, 0, gw, gh, false);
        }
        YYGML_draw_set_colour(C_WHITE); YYGML_draw_set_alpha(1);
        return;
    }
    int t = j->sp_t;
    float in = t < 12 ? t / 12.0f : (t > SPC_DUR - 16 ? (SPC_DUR - t) / 16.0f : 1.0f);
    if (in < 0) in = 0;
    YYGML_draw_set_colour(0);
    YYGML_draw_set_alpha(0.16f * in);                       /* scanlines */
    for (float yy = (float)(t % 6); yy < gh; yy += 6) YYGML_draw_rectangle(0, yy, gw, yy + 2, false);
    float bar = gh * 0.09f * in;                             /* letterbox */
    YYGML_draw_set_alpha(in);
    YYGML_draw_rectangle(0, 0, gw, bar, false);
    YYGML_draw_rectangle(0, gh - bar, gw, gh, false);
    blend(s, 1);                                             /* torn colour bands, more and more of them */
    int nb = 3 + (t < SPC_SLAM ? t / 18 : 2);
    for (int k = 0; k < nb; k++) {
        float yy = frand(bar, gh - bar - 8), hh = frand(2, 12);
        YYGML_draw_set_colour(k % 3 == 0 ? C_WHITE : k % 2 ? C_CYAN : C_MAG);
        YYGML_draw_set_alpha(0.16f * in);
        YYGML_draw_rectangle(frand(-40, 0), yy, gw + frand(0, 40), yy + hh, false);
    }
    if (j->scr_t > 0)                                        /* each clone strike jolts the picture */
        for (int k = 0; k < 2; k++) {
            float yy = frand(bar, gh - bar - 20), hh = frand(10, 26);
            YYGML_draw_set_colour(k ? C_CYAN : C_WHITE);
            YYGML_draw_set_alpha(0.3f);
            YYGML_draw_rectangle(frand(-60, 0), yy, gw + frand(0, 60), yy + hh, false);
        }
    for (int k = 0; k < (t < SPC_SLAM ? t / 8 : 10); k++) {  /* dead pixels raining down the screen */
        float px = (float)((k * 73 + 17) % 97) / 97.0f * gw, py = (float)(((t * (5 + k % 4)) + k * 131) % (int)gh);
        float sz = 4 + (k % 3) * 3;
        YYGML_draw_set_colour(k % 3 == 0 ? C_WHITE : k % 2 ? C_CYAN : C_MAG);
        YYGML_draw_set_alpha(0.5f * in);
        YYGML_draw_rectangle(px, py, px + sz, py + sz, false);
    }
    blend(s, 0);
    int dt = t - SPC_SLAM;
    if (dt >= 1 && dt <= 10) {                               /* the blue screen of death, held */
        YYGML_draw_set_colour(BSOD_BLUE);
        YYGML_draw_set_alpha(0.94f);
        YYGML_draw_rectangle(0, 0, gw, gh, false);
        YYGML_draw_set_colour(C_WHITE);
        YYGML_draw_set_alpha(0.85f);
        YYGML_draw_rectangle(gw * 0.12f, gh * 0.44f, gw * 0.12f + gh * 0.05f, gh * 0.49f, false);   /* a cursor block */
        for (int l = 0; l < 7; l++) {                        /* lines of crash text, typed out */
            float ly = gh * 0.52f + l * gh * 0.045f, lw = gw * (0.25f + 0.08f * ((l * 37) % 5));
            float typed = clampf((dt - l * 0.8f) / 3.0f, 0, 1);
            if (typed > 0) YYGML_draw_rectangle(gw * 0.12f, ly, gw * 0.12f + lw * typed, ly + gh * 0.018f, false);
        }
    } else if (dt > 10 && dt <= 18) {                        /* ... and it breaks up, slice by slice */
        static const unsigned char ORDER[10] = { 3, 7, 1, 9, 5, 0, 8, 2, 6, 4 };
        YYGML_draw_set_colour(BSOD_BLUE);
        for (int k = 0; k < 10; k++) {
            if (dt - 10 > ORDER[k] * 8 / 10) continue;       /* this slice is gone */
            float y0 = gh * k / 10.0f, sh = frand(-gw * 0.06f, gw * 0.06f);
            YYGML_draw_set_alpha(0.9f);
            YYGML_draw_rectangle(sh, y0, gw + sh, y0 + gh / 10.0f + 1, false);
        }
    }
    if (dt >= 0 && dt < 3) {                                 /* the flash */
        YYGML_draw_set_colour(C_WHITE);
        YYGML_draw_set_alpha(1 - dt / 3.0f);
        YYGML_draw_rectangle(0, 0, gw, gh, false);
    }
    if (t >= SPC_SLAM && t < SPC_SLAM + 48) {                /* FATAL ERROR */
        float k = gw / 600.0f * 2.4f;
        float a = t < SPC_SLAM + 36 ? 1.0f : (SPC_SLAM + 48 - t) / 12.0f;
        spr(s, GR_FATAL, (float)((t / 3) % 4), gw * 0.5f + frand(-3, 3), gh * 0.3f, k, k, 0, C_WHITE, a);
    }
    YYGML_draw_set_colour(C_WHITE);
    YYGML_draw_set_alpha(1);
}
