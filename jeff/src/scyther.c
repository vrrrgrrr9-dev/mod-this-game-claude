/*
 * Black Holing Scyther - a cosmic gamecock with a double-bladed obsidian scythe.
 *
 *  combo A (attack A):  Rift Cleave -> Twin Crescent -> Comet Thrust -> Orbit Reap -> Event Horizon Cleave
 *  combo B (attack B):  Crescent Throw -> Spur Vault -> Phase Step -> Dimensional Stitch -> Singular Rend
 *  run + attack:        Meteor Dash (dashes straight through the opponent), then the rest of the combo
 *  down + attack A / B: Ground Reaper (trip) / Rising Moon (launcher)
 *  air attack A / B:    Falling Star, attack again -> Sky Splitter (dive) / Gravity Drop (plunge)
 *  defend:              crouches behind the scythe held upright
 *  skill 1:             Event Horizon - opens a black hole that drags the opponent in, then collapses
 *  skill 2 (down):      Void Lance - cuts an aperture in reality that fires a beam, ends in a nova
 *  special (shield + skill, full bar): SINGULARITY - X-cut on the opponent, cutscene (black hole,
 *                       the multiverse shatters), a huge unblockable hit (no instant K.O.), and the
 *                       stage is left as a void of floating rocks for the rest of the match
 *
 * Every cut tears a hole in reality (rift sprites).  Moves home in on the opponent (a short lunge
 * so the swing connects - for the CPU too).  3D in-engine: the scythe leaves blade trails rendered
 * from its real 3D pose each frame (triangle strips, split in front of / behind the body), shockwave
 * rings lie in a perspective ground plane (far half behind him, near half in front), debris flies
 * with depth (scaled and sorted by z), portals turn in 3D, the void's stone floor is drawn as
 * perspective slabs that parallax with the camera.  Swings also draw pre-rendered 3D arcs, and the
 * scythe sprite itself is pre-rendered in 3D (in-plane angle, tilted orbit, spinning disc).
 * Body and scythe are drawn from 2x-density sprites at half scale.
 *
 * Built on the game's own character framework like the original roster: scr_plr_step drives
 * movement/inputs, alarm[3]/alarm[2] run the combo chain, hits are o_mask_hit hitboxes.
 */
#include "yyc.h"
#include "scyther_assets.h"
#include "stage_decor.h"

#define SCY_CHAR_ID   1006
#define OBJ_SCYTHER   686
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
#define SND_WOOSH1 465
#define SND_WOOSH2 466
#define SND_WOOSH3 467
#define SND_MAGIC3 203
#define SND_MAGICSTUN_CAST 206
#define SND_BALL_CHARGE 266
#define SND_EXPLOSION_MEGA 100
#define SND_DARKEXPLOSION 82
#define SND_SUSPENSE 13
#define SND_STRONG1 162
#define SND_STRONG2 163
#define SND_WINLOSE_IMPACT 464
#define SND_THUNDER 177

#define C_WHITE  0xFFFFFF
#define RGB(r, g, b) ((int)((r) | ((g) << 8) | ((b) << 16)))   /* GameMaker colours are BGR */
#define C_VIOLET RGB(200, 110, 255)
#define C_GHOST  RGB(150, 90, 255)
#define C_RED    RGB(255, 70, 90)
#define C_CORE   RGB(246, 228, 255)
#define C_DEEP   RGB(110, 40, 210)
#define C_DUSK   RGB(150, 140, 190)

enum { MV_NONE, MV_COMBO, MV_SKILL1, MV_SKILL2, MV_SPECIAL };
enum { W_META, W_SPIN, W_ORBIT, W_HIDDEN };            /* how the scythe is drawn */

/* combo_next values: the game's (1 / 50 attack A / B, 10 / 60 crouching, 11 / 61 in the air,
   100 / 110 skills) plus the follow-ups of our own chains */
enum {
    ST_A1 = 1, ST_A2 = 2, ST_THRUST = 3, ST_ORBIT = 4, ST_CLEAVE = 5, ST_DASH_A = 7,
    ST_CROUCH_A = 10, ST_AIR_A = 11, ST_SKY = 12,
    ST_B1 = 50, ST_VAULT = 51, ST_PHASE = 52, ST_STITCH = 53, ST_REND = 54, ST_DASH_B = 57,
    ST_CROUCH_B = 60, ST_AIR_B = 61
};

#define N_RIFT 16
#define N_ARC 8
#define N_GHOST 10
#define N_FX 14
#define N_RING 10
#define N_DEB 28
#define N_TRAIL 10

#define SP_WIND 40            /* in-world X-cut before the cutscene */
#define SP_CUT  180           /* cutscene length */
#define SP_AFTER 40

#define PR_TRIANGLESTRIP 5
#define PI_F 3.14159265f
#define DEG (PI_F / 180.0f)

typedef struct { int on, t, big, life, spin, back; float x, y, ang, sc; } Rift;
typedef struct { int on, t, a; float x, y, xs; } ArcFx;
typedef struct { int on, t, spr, col; float img, x, y, xs, a0; } Ghost;
typedef struct { int on, t, a, tpf, n, add; float x, y, xs, ys, rot; } Fx;
typedef struct { int on, t, life, vert, col; float x, y, r0, r1, sq, w, a, dirx; } Ring;
typedef struct { int on, t, spr, frame; float x, y, z, vx, vy, vz, rot, vr, ground, sc; } Deb;
typedef struct { int on, mode; float gx, gy, ang, xs; } Tsmp;  /* weapon pose sample (blade trails) */

typedef struct {
    CInstance *inst;
    int move, step, t, dur;
    float dir;
    int anim; float frame;
    /* scythe */
    int wmode; float wang, wdraw; int wdraw_ok;
    float alpha;
    /* thrown scythe (Crescent Throw) */
    int th_on, th_t, th_hits; float th_x, th_y, th_vx, th_ang;
    Rift rifts[N_RIFT]; ArcFx arcs[N_ARC]; Ghost ghosts[N_GHOST]; Fx fx[N_FX];
    Ring rings[N_RING]; Deb deb[N_DEB];
    Tsmp trail[2][N_TRAIL]; int trail_head[2]; float trail_last;   /* [0] in hand, [1] thrown */
    int ghosting, smear; float sqx, sqy;
    int home_t; float home_v;
    int landed, land_t, blink;
    int pass; float gap;                 /* pass = may run through him; gap = distance to him in front */
    /* skill 1: black hole */
    int bh_on, bh_t; float bh_x, bh_y;
    /* skill 2: void lance */
    int eye_on, eye_t; float eye_x, eye_y;
    int beam_on, beam_t; float beam_x, beam_y, beam_len, beam_dir;
    /* special */
    int tgt_id; float tgt_x, tgt_y; int cut_t, hit_done, depth_saved; double old_depth; float shake;
    /* the void stage after SINGULARITY */
    int void_on, void_t, void_hidden, void_drawn; float ground_y;
    int aura_t, fail_t;
} Scy;

static Scy g_scy[4];
int g_scy_spr[SC_COUNT];
int g_scy_snd[SCS_COUNT];
int g_scy_loaded;

/* ------------------------------------------------------------------------------------------ */
/* runtime helpers (same idioms as jeff.c)                                                    */
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
static double pget(CInstance *s, YYVAR *v) { return get_rv(parent_of(s), v, ARRAY_INDEX_NONE); }
static void pset(CInstance *s, YYVAR *v, double d) { RValue r = rv_real(d); YYGML_Variable_SetValue(parent_of(s), v->id, ARRAY_INDEX_NONE, &r); }
static void pset_b(CInstance *s, YYVAR *v, bool b) { RValue r = rv_bool(b); YYGML_Variable_SetValue(parent_of(s), v->id, ARRAY_INDEX_NONE, &r); }

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

static unsigned g_rng = 0x51ed2701u;
static unsigned rnd(void) { g_rng ^= g_rng << 13; g_rng ^= g_rng >> 17; g_rng ^= g_rng << 5; return g_rng; }
static float frand(float a, float b) { return a + (b - a) * (float)(rnd() & 0xffff) / 65535.0f; }
static float fabsf_(float v) { return v < 0 ? -v : v; }
static float wrap360(float a) { while (a < 0) a += 360; while (a >= 360) a -= 360; return a; }
static float wrap180(float a) { a = wrap360(a); return a > 180 ? a - 360 : a; }
static float sinf_(float x) {                     /* small, freestanding sine (radians) */
    while (x > PI_F) x -= 2 * PI_F;
    while (x < -PI_F) x += 2 * PI_F;
    float x2 = x * x;
    return x * (1 - x2 / 6 * (1 - x2 / 20 * (1 - x2 / 42 * (1 - x2 / 72))));
}
static float cosf_(float x) { return sinf_(x + PI_F / 2); }
static float sqrtf_(float x) { return x > 0 ? __builtin_sqrtf(x) : 0; }

static void play(CInstance *s, int snd, double pitch) {
    if (snd < 0) return;
    RValue r = rv_undef();
    RValue a[3] = { rv_real(snd), rv_real(10), rv_real(0) };
    F_AudioPlaySound(&r, s, s, 3, a);
    if (pitch != 1.0 && (r.kind & KIND_MASK) != VALUE_UNDEFINED) {
        RValue r2 = rv_undef();
        RValue b[2] = { r, rv_real(pitch) };
        F_AudioSoundPitch(&r2, s, s, 2, b);
        rv_free(&r2);
    }
    rv_free(&r);
}
static void play_c(CInstance *s, int which, double pitch) { play(s, g_scy_snd[which], pitch); }

static void blend(CInstance *s, int mode) {
    RValue r = rv_undef(); RValue a = rv_real(mode);
    F_GPUSetBlendMode(&r, s, s, 1, &a);
    rv_free(&r);
}
/* draw one of our sprites; 2x-density sprites are drawn at half scale */
static void spr(CInstance *s, int a, float img, float x, float y, float xs, float ys, float rot, int col, float alpha) {
    int id = g_scy_spr[a];
    if (id < 0) return;
    float k = k_scy_sprites[a].half ? 0.5f : 1.0f;
    YYGML_draw_sprite_ext(s, id, img, x, y, xs * k, ys * k, rot, col, alpha);
}
/* a sprite stretched over any quad (top-left, top-right, bottom-right, bottom-left) */
static void spr_pos(CInstance *s, int a, float img, float x1, float y1, float x2, float y2, float x3, float y3,
                    float x4, float y4, float alpha) {
    int id = g_scy_spr[a];
    if (id < 0) return;
    RValue r = rv_undef();
    RValue v[11] = { rv_real(id), rv_real(img), rv_real(x1), rv_real(y1), rv_real(x2), rv_real(y2),
                     rv_real(x3), rv_real(y3), rv_real(x4), rv_real(y4), rv_real(alpha) };
    F_DrawSpritePos(&r, s, s, 11, v);
    rv_free(&r);
}
static void spr_part(CInstance *s, int a, float img, float l, float t, float w, float h, float x, float y, float alpha) {
    int id = g_scy_spr[a];
    if (id < 0) return;
    RValue r = rv_undef();
    RValue v[12] = { rv_real(id), rv_real(img), rv_real(l), rv_real(t), rv_real(w), rv_real(h), rv_real(x), rv_real(y),
                     rv_real(1), rv_real(1), rv_real(C_WHITE), rv_real(alpha) };
    F_DrawSpritePartExt(&r, s, s, 12, v);
    rv_free(&r);
}
/* immediate-mode triangle strips with per-vertex colour (the 3D trails and rings) */
static void prim_begin(CInstance *s) {
    RValue r = rv_undef(); RValue v = rv_real(PR_TRIANGLESTRIP);
    F_DrawPrimitiveBegin(&r, s, s, 1, &v);
    rv_free(&r);
}
static void prim_end(CInstance *s) {
    RValue r = rv_undef(); RValue v = rv_undef();
    F_DrawPrimitiveEnd(&r, s, s, 0, &v);
    rv_free(&r);
}
static void vtx(CInstance *s, float x, float y, int col, float a) {
    RValue r = rv_undef();
    RValue v[4] = { rv_real(x), rv_real(y), rv_real(col), rv_real(a < 0 ? 0 : (a > 1 ? 1 : a)) };
    F_DrawVertexColor(&r, s, s, 4, v);
    rv_free(&r);
}
static void camera_shake(double amount) {
    RValue cam = rv_real(OBJ_CAMERA);
    RValue v = rv_real(amount);
    YYGML_Variable_SetValue(&cam, g_VAR_camera_shake.id, ARRAY_INDEX_NONE, &v);
}
static double legacy0(CInstance *s, YYVAR *f) {
    RValue r = rv_undef();
    YYGML_CallLegacyFunction(s, s, &r, 0, f->id, 0);
    double d = rv_num(&r);
    rv_free(&r);
    return d;
}
static double fcall1(CInstance *s, void (*fn)(RValue *, CInstance *, CInstance *, int, RValue *), RValue a) {
    RValue r = rv_undef();
    fn(&r, s, s, 1, &a);
    double d = rv_num(&r);
    rv_free(&r);
    return d;
}
static int inst_count(CInstance *s, int obj) {
    RValue n = rv_undef(); RValue a = rv_real(obj);
    F_InstanceNumber(&n, s, s, 1, &a);
    int c = (int)rv_num(&n);
    rv_free(&n);
    return c;
}
static CInstance *inst_nth(CInstance *s, int obj, int i, int *out_id) {
    RValue id = rv_undef(); RValue fa[2] = { rv_real(obj), rv_real(i) };
    F_InstanceFind(&id, s, s, 2, fa);
    int iid = INT32_RValue(&id);
    rv_free(&id);
    if (out_id) *out_id = iid;
    return YYGML_FindInstance(iid);
}

/* ------------------------------------------------------------------------------------------ */
/* assets                                                                                      */
/* ------------------------------------------------------------------------------------------ */
void scyther_load_assets(CInstance *s) {
    if (g_scy_loaded) return;
    g_scy_loaded = 1;
    for (int i = 0; i < SC_COUNT; i++) {
        RValue r = rv_undef();
        RValue a[6];
        YYCreateString(&a[0], k_scy_sprites[i].file);
        a[1] = rv_real(k_scy_sprites[i].frames);
        a[2] = rv_bool(false);
        a[3] = rv_bool(false);
        a[4] = rv_real(k_scy_sprites[i].ox);
        a[5] = rv_real(k_scy_sprites[i].oy);
        F_SpriteAdd(&r, s, s, 6, a);
        g_scy_spr[i] = (r.kind & KIND_MASK) == VALUE_UNDEFINED ? -1 : (int)rv_num(&r);
        rv_free(&r);
        rv_free(&a[0]);
    }
    for (int i = 0; i < SCS_COUNT; i++) {
        RValue r = rv_undef();
        RValue a;
        YYCreateString(&a, k_scy_sounds[i]);
        F_AudioCreateStream(&r, s, s, 1, &a);
        g_scy_snd[i] = (r.kind & KIND_MASK) == VALUE_UNDEFINED ? -1 : (int)rv_num(&r);
        rv_free(&r);
        rv_free(&a);
    }
    if (g_scy_spr[SC_PREVIEW] >= 0) {               /* select-screen preview = the object's sprite */
        RValue r = rv_undef();
        RValue a[2] = { rv_real(OBJ_SCYTHER), rv_real(g_scy_spr[SC_PREVIEW]) };
        F_ObjectSetSprite(&r, s, s, 2, a);
        rv_free(&r);
    }
}

/* ------------------------------------------------------------------------------------------ */
/* per-instance state                                                                          */
/* ------------------------------------------------------------------------------------------ */
static void scy_reset(Scy *j, CInstance *s) {
    char *p = (char *)j; for (unsigned k = 0; k < sizeof(Scy); k++) p[k] = 0;
    j->inst = s; j->dir = 1; j->tgt_id = -1; j->anim = -1; j->alpha = 1; j->sqx = j->sqy = 1;
    j->void_drawn = -1;
}
static Scy *slot(CInstance *s, bool create) {
    for (int i = 0; i < 4; i++) if (g_scy[i].inst == s) return &g_scy[i];
    if (!create) return 0;
    for (int i = 0; i < 4; i++) if (!g_scy[i].inst) { scy_reset(&g_scy[i], s); return &g_scy[i]; }
    scy_reset(&g_scy[3], s);
    return &g_scy[3];
}

/* which of our body animations is showing (-1 = none) */
static int body_anim(CInstance *s) {
    int sp = (int)sget(s, &g_VAR_sprite_index);
    for (int a = 0; a < SC_COUNT; a++)
        if (k_scy_meta_first[a] >= 0 && g_scy_spr[a] == sp) return a;
    return -1;
}
static const ScyFrame *frame_meta(CInstance *s) {
    int a = body_anim(s);
    if (a < 0) return 0;
    int f = (int)sget(s, &g_VAR_image_index);
    int n = k_scy_sprites[a].frames;
    if (f < 0) f = 0;
    f %= n;
    return &k_scy_meta[k_scy_meta_first[a] + f];
}

/* ------------------------------------------------------------------------------------------ */
/* hitboxes                                                                                    */
/* ------------------------------------------------------------------------------------------ */
typedef struct { double dmg, hforce, vforce, stun, dur, xs, ys; int mask, hits, knock, defend, fallen, hit_spr, color, snd; } Hit;
static void spawn_hit(CInstance *s, double x, double y, const Hit *h) {
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

static double my_dmg(CInstance *s) { return parent_ok(s) ? pget(s, &g_VAR_plr_dmg) : 48; }
static float sx_(CInstance *s) { return (float)sget(s, &g_VAR_x); }
static float sy_(CInstance *s) { return (float)sget(s, &g_VAR_y); }

/* ------------------------------------------------------------------------------------------ */
/* effects: reality tears, 3D arcs, afterimages, one-shots, rings, debris                      */
/* ------------------------------------------------------------------------------------------ */
static Rift *rift_at(Scy *j, float x, float y, float ang, float sc, int big, int life) {
    int best = 0;
    for (int i = 0; i < N_RIFT; i++) { if (!j->rifts[i].on) { best = i; break; } if (j->rifts[i].t > j->rifts[best].t) best = i; }
    Rift *r = &j->rifts[best];
    r->on = 1; r->t = 0; r->big = big; r->life = life; r->spin = 0; r->back = 0;
    r->x = x; r->y = y; r->sc = sc;
    r->ang = j->dir > 0 ? ang : -ang;                   /* mirror for the facing */
    return r;
}
static void rift(CInstance *s, Scy *j, float dx, float dy, float ang, float sc, int big) {
    rift_at(j, sx_(s) + j->dir * dx, sy_(s) + dy, ang, sc, big, big ? 96 : 48);
}
/* a portal that turns in 3D: opens edge-on, swings round to face the camera, closes edge-on */
static void portal_at(Scy *j, float x, float y, float sc, int life) {
    rift_at(j, x, y, 90, sc, 1, life)->spin = 1;
}
static void arc(CInstance *s, Scy *j, int back_sprite, float dx, float dy) {
    int best = 0;
    for (int i = 0; i < N_ARC; i++) { if (!j->arcs[i].on) { best = i; break; } if (j->arcs[i].t > j->arcs[best].t) best = i; }
    ArcFx *a = &j->arcs[best];
    a->on = 1; a->t = 0; a->a = back_sprite;
    a->x = sx_(s) + j->dir * dx; a->y = sy_(s) + dy; a->xs = j->dir;
}
static void fx_at(Scy *j, int a, float x, float y, float xs, float ys, float rot, int tpf, int add) {
    int best = 0;
    for (int i = 0; i < N_FX; i++) { if (!j->fx[i].on) { best = i; break; } if (j->fx[i].t > j->fx[best].t) best = i; }
    Fx *f = &j->fx[best];
    f->on = 1; f->t = 0; f->a = a; f->tpf = tpf; f->n = k_scy_sprites[a].frames; f->add = add;
    f->x = x; f->y = y; f->xs = xs; f->ys = ys; f->rot = rot;
}
static void ghost_c(CInstance *s, Scy *j, int col, float a0) {
    int best = 0;
    for (int i = 0; i < N_GHOST; i++) { if (!j->ghosts[i].on) { best = i; break; } if (j->ghosts[i].t > j->ghosts[best].t) best = i; }
    Ghost *g = &j->ghosts[best];
    g->on = 1; g->t = 0; g->spr = (int)sget(s, &g_VAR_sprite_index); g->img = (float)sget(s, &g_VAR_image_index);
    g->x = sx_(s); g->y = sy_(s); g->xs = (float)sget(s, &g_VAR_image_xscale); g->col = col; g->a0 = a0;
}
static void ghost(CInstance *s, Scy *j) { ghost_c(s, j, C_GHOST, 0.45f); }
/* a shockwave ring: flat in the ground plane (vert = 0, sq = how flat the ellipse looks) or
   standing upright across the facing direction (vert = 1, e.g. around a thrust) */
static void ring(Scy *j, float x, float y, float r0, float r1, float sq, float w, int life, int col, float a, int vert) {
    int best = 0;
    for (int i = 0; i < N_RING; i++) { if (!j->rings[i].on) { best = i; break; } if (j->rings[i].t > j->rings[best].t) best = i; }
    Ring *r = &j->rings[best];
    r->on = 1; r->t = 0; r->life = life; r->vert = vert; r->col = col;
    r->x = x; r->y = y; r->r0 = r0; r->r1 = r1; r->sq = sq; r->w = w; r->a = a; r->dirx = j->dir;
}
/* rock chips and dust thrown up with depth (z > 0 = toward the camera) */
static void debris(Scy *j, float x, float y, int n, float pw) {
    for (int k = 0; k < n; k++) {
        int best = 0;
        for (int i = 0; i < N_DEB; i++) { if (!j->deb[i].on) { best = i; break; } if (j->deb[i].t > j->deb[best].t) best = i; }
        Deb *d = &j->deb[best];
        d->on = 1; d->t = 0;
        d->spr = (rnd() % 3 == 0) ? SC_VOID_DUST : SC_BH_DEBRIS;
        d->frame = (int)(rnd() % 8);
        d->x = x + frand(-6, 6); d->y = y - 2; d->z = frand(-8, 8);
        d->vx = frand(-3.2f, 3.2f) * pw; d->vy = frand(-6.5f, -2.5f) * pw; d->vz = frand(-3.0f, 3.0f) * pw;
        d->rot = frand(0, 360); d->vr = frand(-24, 24); d->ground = y; d->sc = frand(0.35f, 0.8f);
    }
}
static void squash(Scy *j, float xs, float ys) { j->sqx = xs; j->sqy = ys; }
static void effects_step(CInstance *s, Scy *j) {
    for (int i = 0; i < N_RIFT; i++) if (j->rifts[i].on && ++j->rifts[i].t >= j->rifts[i].life) j->rifts[i].on = 0;
    for (int i = 0; i < N_ARC; i++) if (j->arcs[i].on && ++j->arcs[i].t >= 18) j->arcs[i].on = 0;
    for (int i = 0; i < N_GHOST; i++) if (j->ghosts[i].on && ++j->ghosts[i].t >= 14) j->ghosts[i].on = 0;
    for (int i = 0; i < N_FX; i++) if (j->fx[i].on && ++j->fx[i].t >= j->fx[i].n * j->fx[i].tpf) j->fx[i].on = 0;
    for (int i = 0; i < N_RING; i++) if (j->rings[i].on && ++j->rings[i].t >= j->rings[i].life) j->rings[i].on = 0;
    for (int i = 0; i < N_DEB; i++) {
        Deb *d = &j->deb[i];
        if (!d->on) continue;
        d->vy += 0.42f; d->x += d->vx; d->y += d->vy; d->z += d->vz; d->rot += d->vr;
        if (d->y > d->ground) { d->y = d->ground; d->vy *= -0.38f; d->vx *= 0.6f; d->vz *= 0.6f; d->vr *= 0.5f; }
        if (++d->t >= 46) d->on = 0;
    }
    if (j->ghosting && (j->aura_t % 2) == 0) ghost(s, j);
    j->sqx += (1 - j->sqx) * 0.3f; j->sqy += (1 - j->sqy) * 0.3f;
    if (j->blink < 100) j->blink++;
}
static float rift_frame(const Rift *r) {
    if (r->t < 12) return r->t / 3.0f;                          /* opening */
    if (r->t < r->life - 12) return 4 + (float)((r->t / 4) % 8);  /* shimmering hold */
    return 12 + (r->t - (r->life - 12)) / 3.0f;                 /* sealing */
}

/* ------------------------------------------------------------------------------------------ */
/* the scythe's pose each frame + its blade trails                                            */
/* ------------------------------------------------------------------------------------------ */
/* points on the right-hand blade in the weapon's own plane (1x px, angle 0); the left blade is the
   point reflection.  From weapon.py: the middle of the outer curve and near the tip. */
static const float BL_MID[2] = { 29.1f, -18.3f };
static const float BL_OUT[2] = { 17.6f, -32.3f };
static const float TILT_C[3] = { 1.0f, 0.4384f, 0.2756f };   /* cos(0), cos(64), cos(74) */
static const float TILT_S[3] = { 0.0f, 0.8988f, 0.9613f };   /* sin(...) */

static void trail_push(Scy *j, int which, int on, int mode, float gx, float gy, float ang, float xs) {
    int h = (j->trail_head[which] + 1) % N_TRAIL;
    Tsmp *p = &j->trail[which][h];
    p->on = on; p->mode = mode; p->gx = gx; p->gy = gy; p->ang = ang; p->xs = xs;
    j->trail_head[which] = h;
}
/* blade point -> screen (x, y) and depth z (> 0 toward the camera) */
static void blade_pt(int mode, float gx, float gy, float ang, float xs, const float *lp, int sgn,
                     float *ox, float *oy, float *oz) {
    float a = ang * DEG, ca = cosf_(a), sa = sinf_(a);
    float lx = lp[0] * sgn, ly = lp[1] * sgn;
    float rx = lx * ca - ly * sa, ry = lx * sa + ly * ca;
    *ox = gx + xs * rx;
    *oy = gy + ry * TILT_C[mode];
    *oz = mode ? ry * TILT_S[mode] : 1.0f;
}
static void weapon_update(CInstance *s, Scy *j) {
    const ScyFrame *m = frame_meta(s);
    float x = sx_(s), y = sy_(s);
    float fxs = sget(s, &g_VAR_image_xscale) < 0 ? -1.0f : 1.0f;
    int on = 0, mode = 0; float gx = x, gy = y, ang = j->trail_last, xs = fxs;
    if (m && !(m->fl & 2) && j->wmode != W_HIDDEN && !j->th_on) {
        float wf = (m->fl & 4) ? -1.0f : 1.0f;
        gx = x + fxs * (m->gx / 2.0f); gy = y + m->gy / 2.0f; xs = fxs * wf;
        if (j->wmode == W_ORBIT) { mode = 1; ang = wrap360(j->wang); }
        else {
            float target = (float)m->ang;
            if (!j->wdraw_ok) { j->wdraw = target; j->wdraw_ok = 1; }
            float d = wrap180(target - j->wdraw);              /* shortest way round */
            j->wdraw = wrap360(j->wdraw + d * 0.55f);
            ang = j->wdraw;
        }
        on = j->move != MV_NONE && (mode == 1 || fabsf_(wrap180(ang - j->trail_last)) >= 7.0f);
    }
    trail_push(j, 0, on, mode, gx, gy, ang, xs);
    j->trail_last = ang;
    if (j->th_on) trail_push(j, 1, 1, 2, j->th_x, j->th_y, j->th_ang, 1);
    else trail_push(j, 1, 0, 2, 0, 0, 0, 1);
}
/* the blade trails: for each blade a ribbon from mid-blade (faint) to the tip (bright) across the
   last N_TRAIL poses, sub-sampled along the turn so fast spins stay round */
static void draw_trail(CInstance *s, Scy *j, int which, int front) {
    const Tsmp *buf = j->trail[which];
    int head = j->trail_head[which];
    const int SUB = 3;
    for (int b = 0; b < 2; b++) {
        int sgn = b ? -1 : 1;
        {
            int open = 0;
            for (int k = 0; k < N_TRAIL - 1; k++) {
                const Tsmp *p0 = &buf[(head - k + N_TRAIL) % N_TRAIL];
                const Tsmp *p1 = &buf[(head - k - 1 + N_TRAIL) % N_TRAIL];
                if (!p0->on || !p1->on || p0->mode != p1->mode) { if (open) { prim_end(s); open = 0; } continue; }
                float d = wrap180(p1->ang - p0->ang);
                for (int q = 0; q < SUB; q++) {
                    float u = (float)q / SUB;
                    float gx = p0->gx + (p1->gx - p0->gx) * u, gy = p0->gy + (p1->gy - p0->gy) * u;
                    float ang = p0->ang + d * u;
                    float age = (k + u) / (N_TRAIL - 1);
                    float al = (1 - age) * (1 - age) * (which ? 0.75f : 0.9f);
                    float ax, ay, az, bx, by, bz;
                    blade_pt(p0->mode, gx, gy, ang, p0->xs, BL_MID, sgn, &ax, &ay, &az);
                    blade_pt(p0->mode, gx, gy, ang, p0->xs, BL_OUT, sgn, &bx, &by, &bz);
                    if (((az + bz) >= 0) != (front != 0)) { if (open) { prim_end(s); open = 0; } continue; }
                    if (!open) { prim_begin(s); open = 1; }
                    vtx(s, ax, ay, C_DEEP, al * 0.12f);
                    vtx(s, bx, by, C_CORE, al);
                }
            }
            if (open) prim_end(s);
        }
    }
}
static void draw_ring(CInstance *s, const Ring *r, int front) {
    float k = (float)r->t / r->life;
    float e = 1 - (1 - k) * (1 - k);                        /* ease out */
    float R = r->r0 + (r->r1 - r->r0) * e;
    float a = r->a * (1 - k) * (k < 0.08f ? k / 0.08f : 1);
    float w = r->w * (1.15f - 0.65f * k);
    const int SEG = 18;
    for (int band = 0; band < 2; band++) {
        prim_begin(s);
        for (int i = 0; i <= SEG; i++) {
            float th = (front ? 0.0f : PI_F) + PI_F * i / SEG;   /* lower half = near half */
            float c = cosf_(th), sn = sinf_(th);
            float near = 1 + 0.4f * sn;
            float ww = w * near, aa = a * (0.5f + 0.5f * near);
            float px, py, nx, ny;
            if (!r->vert) { px = r->x + c * R; py = r->y + sn * R * r->sq; nx = c; ny = sn * r->sq; }
            else { px = r->x + sn * R * r->sq * r->dirx; py = r->y + c * R; nx = sn * r->sq * r->dirx; ny = c; }
            float L = sqrtf_(nx * nx + ny * ny);
            if (L < 1e-3f) L = 1;
            nx /= L; ny /= L;
            if (band == 0) { vtx(s, px - nx * ww, py - ny * ww, r->col, 0); vtx(s, px, py, C_CORE, aa); }
            else { vtx(s, px, py, C_CORE, aa); vtx(s, px + nx * ww * 0.7f, py + ny * ww * 0.7f, r->col, 0); }
        }
        prim_end(s);
    }
}
static void draw_debris(CInstance *s, Scy *j, int front) {
    for (int i = 0; i < N_DEB; i++) {
        Deb *d = &j->deb[i];
        if (!d->on || ((d->z >= 0) != (front != 0))) continue;
        float p = 220.0f / (220.0f - (d->z > 180 ? 180 : d->z));   /* perspective scale */
        float sc = d->sc * p;
        float a = d->t > 34 ? (46 - d->t) / 12.0f : 1.0f;
        spr(s, d->spr, (float)d->frame, d->x, d->y + d->z * 0.22f, sc, sc, d->rot, d->z < -6 ? C_DUSK : C_WHITE, a);
    }
}

/* ------------------------------------------------------------------------------------------ */
/* events                                                                                      */
/* ------------------------------------------------------------------------------------------ */
void gml_Object_o_scyther_Create_0(CInstance *s, CInstance *o) {
    scyther_load_assets(s);
    gml_Object_o_parent_character_Create_0(s, o);        /* event_inherited() */
    slot(s, true);
    iset(s, &g_VAR_parent, 0);
    iset_b(s, &g_VAR_local_runleft, false);
    iset(s, &g_VAR_combo_next, -1);
    iset_b(s, &g_VAR_combo_nextcombo, false);
    iset_b(s, &g_VAR_has_voice, false);
    iset_b(s, &g_VAR_is_speaking, false);
    iset(s, &g_VAR_current_voice_audio, -1);
    iset(s, &g_VAR_img_voice, 0);
    iset_str(s, &g_VAR_char_name, "Black Holing Scyther");
    iset(s, &g_VAR_stats_hp, 2250);
    iset(s, &g_VAR_stats_dmg, 48);
    iset(s, &g_VAR_stats_walkspd, 3.4);
    iset(s, &g_VAR_stats_airdashspd, 9.0);
    iset(s, &g_VAR_stats_runspd, 8.0);
    iset(s, &g_VAR_stats_jumpforce, -7.0);
    iset(s, &g_VAR_snd_jump, SND_JUMP);
    iset(s, &g_VAR_snd_transform, SND_JUMP);
    iset(s, &g_VAR_hp_draw_y, 66);
    iset(s, &g_VAR_hp_width, 40);
    iset(s, &g_VAR_hp_height, 5);
    iset(s, &g_VAR_energy_skill1_cost, 60);
    iset(s, &g_VAR_energy_skill2_cost, 45);
    iset(s, &g_VAR_spr_stand, g_scy_spr[SC_STAND]);
    iset(s, &g_VAR_spr_crouch, g_scy_spr[SC_CROUCH]);
    iset(s, &g_VAR_spr_charge, g_scy_spr[SC_CHARGE]);
    iset(s, &g_VAR_spr_run, g_scy_spr[SC_RUN]);
    iset(s, &g_VAR_spr_walk, g_scy_spr[SC_WALK]);
    iset(s, &g_VAR_spr_jump, g_scy_spr[SC_JUMP]);
    iset(s, &g_VAR_spr_fall, g_scy_spr[SC_FALL]);
    iset(s, &g_VAR_spr_defend, g_scy_spr[SC_DEFEND]);
    iset(s, &g_VAR_spr_fallen, g_scy_spr[SC_FALLEN]);
    iset(s, &g_VAR_spr_hurt, g_scy_spr[SC_HURT]);
    iset(s, &g_VAR_spr_hurtup, g_scy_spr[SC_HURTUP]);
    iset(s, &g_VAR_spr_hurtdown, g_scy_spr[SC_HURTDOWN]);
    iset(s, &g_VAR_spr_transform, -1);
    iset(s, &g_VAR_spr_mask_stand, SPR_MASK_STAND);
    iset(s, &g_VAR_spr_mask_crouch, SPR_MASK_CROUCH);
    bset(s, &g_VAR_sprite_index, g_scy_spr[SC_STAND]);
    bset(s, &g_VAR_mask_index, SPR_MASK_STAND);
    bset(s, &g_VAR_image_speed, 0.25);
    bset_i(s, &g_VAR_alarm, 0, 1);
    iset(s, &g_VAR_imgindex_aura, 0);
    iset(s, &g_VAR_img_index_aura, 8);
    iset(s, &g_VAR_ef_img_aura, 2);
}

void gml_Object_o_scyther_Alarm_0(CInstance *s, CInstance *o) {
    (void)o;
    if (!parent_ok(s) || g_scy_spr[SC_FACE] < 0) return;
    pset(s, &g_VAR_spr_face, g_scy_spr[SC_FACE]);
}

void gml_Object_o_scyther_Destroy_0(CInstance *s, CInstance *o) {
    Scy *j = slot(s, false);
    if (j) j->inst = 0;
    gml_Object_o_parent_character_Destroy_0(s, o);
}

/* ------------------------------------------------------------------------------------------ */
/* the choreography                                                                            */
/* ------------------------------------------------------------------------------------------ */
static float facing(CInstance *s) { return sget(s, &g_VAR_image_xscale) < 0 ? -1.0f : 1.0f; }

static void show(CInstance *s, Scy *j, int anim, float frame) {
    j->anim = anim; j->frame = frame;
    bset(s, &g_VAR_sprite_index, g_scy_spr[anim]);
    bset(s, &g_VAR_image_index, frame);
    bset(s, &g_VAR_image_speed, 0);
}
/* frame for time t given the start tick of each frame */
static int kf(int t, const int *starts, int n) {
    int f = 0;
    for (int i = 0; i < n; i++) if (t >= starts[i]) f = i;
    return f;
}
static void dash(CInstance *s, Scy *j, float spd) { bset(s, &g_VAR_hspeed, j->dir * spd); }
static void stop(CInstance *s) { bset(s, &g_VAR_hspeed, 0); }
static bool on_air(CInstance *s) { return parent_ok(s) && pget(s, &g_VAR_is_onair) > 0.5; }
static bool is_cpu(CInstance *s) { return parent_ok(s) && pget(s, &g_VAR_plr_controller) == 2; }
static bool running(CInstance *s) {
    if (parent_ok(s) && pget(s, &g_VAR_is_running) > 0.5) return true;
    double hs = sget(s, &g_VAR_hspeed);
    return (hs < 0 ? -hs : hs) > iget(s, &g_VAR_stats_walkspd) + 0.8;
}

static CInstance *nearest_enemy(CInstance *s, int *out_id, float maxdx, float maxdy);
static void start_skill1(CInstance *s, Scy *j);
static void start_skill2(CInstance *s, Scy *j);

/* a short homing lunge so the cut connects: turns to an opponent right behind him and covers the
   gap to `reach` over `frames` frames (applied on top of the move's own motion) */
static void home(CInstance *s, Scy *j, float reach, int frames) {
    int tid = -1;
    j->home_t = 0;
    CInstance *e = nearest_enemy(s, &tid, 190, 80);
    if (!e) return;
    float dx = (float)sget(e, &g_VAR_x) - sx_(s);
    if (dx * j->dir < 0) {
        if (fabsf_(dx) > 70) return;
        j->dir = -j->dir;
        bset(s, &g_VAR_image_xscale, j->dir);
    }
    float gap = fabsf_(dx) - reach;
    if (gap <= 1) return;
    if (gap > 140) gap = 140;
    j->home_v = gap / frames; j->home_t = frames;
}

/* a melee hit in front of (dx > 0) or behind (dx < 0) the rooster, with a flash on the cut */
static void melee(CInstance *s, Scy *j, float dx, float dy, int mask, float xs, float ys, double k, double hf, double vf,
                  double stun, int knock, int spr_hit) {
    Hit h = { my_dmg(s) * k, j->dir * hf * (dx < 0 ? -1 : 1), vf, stun, 7, xs, ys, mask, 1, knock, 1, knock, spr_hit, C_VIOLET, 1 };
    float x = sx_(s) + j->dir * dx, y = sy_(s) + dy;
    spawn_hit(s, x, y, &h);
    fx_at(j, SC_HITFX, x, y, 0.6f, 0.6f, frand(0, 90), 1, 1);
}

static void end_move(CInstance *s, Scy *j) {
    j->move = MV_NONE; j->anim = -1; j->wmode = W_META; j->ghosting = 0; j->smear = 0; j->alpha = 1; j->home_t = 0;
    bset(s, &g_VAR_image_speed, 0.25);
    if (sget_i(s, &g_VAR_alarm, 2) > 1) bset_i(s, &g_VAR_alarm, 2, 1);   /* finished early: chain now */
}

static void scy_start(CInstance *s, CInstance *o, int step) {
    Scy *j = slot(s, true);
    (void)o;
    iset_b(s, &g_VAR_combo_nextcombo, false);
    if (step == 100) { start_skill1(s, j); return; }
    if (step == 110) { start_skill2(s, j); return; }
    j->dir = facing(s);
    if ((step == ST_A1 || step == ST_B1) && running(s) && !on_air(s))
        step = step == ST_A1 ? ST_DASH_A : ST_DASH_B;              /* attacking out of a run */
    j->move = MV_COMBO; j->step = step; j->t = 0;
    j->wmode = W_META; j->ghosting = 0; j->smear = 0; j->alpha = 1; j->home_t = 0; j->landed = 0;
    j->pass = (step == ST_DASH_A || step == ST_DASH_B);
    int next = -1, dur = 20;
    switch (step) {
    case ST_A1: next = ST_A2; dur = 18; break;
    case ST_A2: next = ST_THRUST; dur = 22; break;
    case ST_THRUST: next = ST_ORBIT; dur = 24; break;
    case ST_ORBIT: next = ST_CLEAVE; dur = 28; break;
    case ST_CLEAVE: dur = 46; break;
    case ST_DASH_A: next = ST_A2; dur = 26; break;
    case ST_DASH_B: next = ST_VAULT; dur = 26; break;
    case ST_B1: next = ST_VAULT; dur = 40; break;
    case ST_VAULT: next = ST_PHASE; dur = 32; break;
    case ST_PHASE: next = ST_STITCH; dur = 34; break;
    case ST_STITCH: next = ST_REND; dur = 30; break;
    case ST_REND: dur = 44; break;
    case ST_CROUCH_A: dur = 16; break;
    case ST_CROUCH_B: dur = 26; break;
    case ST_AIR_A: next = ST_SKY; dur = 16; break;
    case ST_SKY: dur = 46; break;
    case ST_AIR_B: dur = 54; break;
    default: j->move = MV_NONE; iset(s, &g_VAR_combo_next, -1); bset_i(s, &g_VAR_alarm, 2, 1); return;
    }
    j->dur = dur;
    iset(s, &g_VAR_combo_next, next);
    bset_i(s, &g_VAR_alarm, 2, dur);
}

/* combo A ------------------------------------------------------------------------------------ */
static void step_a1(CInstance *s, Scy *j, int t) {           /* Rift Cleave: lunge + rising cut */
    static const int K[] = { 0, 3, 6, 10, 14 };
    show(s, j, SC_A1, (float)kf(t, K, 5));
    if (t == 1) home(s, j, 30, 5);
    if (t >= 3 && t <= 6) dash(s, j, 2.6f); else stop(s);
    if (t == 5) {
        melee(s, j, 26, -34, SPR_MASK32, 1.4f, 1.7f, 0.95, 3, -2, 16, 0, SPR_HIT_3);
        arc(s, j, SC_ARC_RISE_B, 8, -24);
        play_c(s, SCS_SLASH, 1.05);
    }
    if (t == 6) { rift(s, j, 36, -44, -55, 1.0f, 0); play_c(s, SCS_RIP, 1.1); }
}
static void step_a2(CInstance *s, Scy *j, int t) {           /* Twin Crescent: 3D twirl, two hits, X tear */
    static const int K[] = { 0, 3, 6, 15 };
    int f = kf(t, K, 4);
    if (f == 1 || f == 2) f = 1 + ((t / 3) % 2);
    show(s, j, SC_A2, (float)f);
    if (t == 1) home(s, j, 32, 4);
    if (t >= 3 && t < 15) { j->wmode = W_ORBIT; j->wang += 36; dash(s, j, 2.0f); }
    else { j->wmode = W_META; stop(s); }
    if (t == 3) { arc(s, j, SC_ARC_TWIRL_B, 20, -35); play_c(s, SCS_SPIN, 1.05); }
    if (t == 5 || t == 11) {
        melee(s, j, 26, -36, SPR_MASK32, 1.5f, 1.5f, 0.6, 3, -2, 14, 0, SPR_HIT_1);
        play_c(s, SCS_SLASH, t == 5 ? 1.1 : 1.25);
    }
    if (t == 14) {
        rift(s, j, 40, -40, 45, 0.9f, 0); rift(s, j, 40, -40, -45, 0.9f, 0);
        arc(s, j, SC_ARC_XCUT_B, 40, -40);
        play_c(s, SCS_RIP, 1.0);
    }
}
static void step_thrust(CInstance *s, Scy *j, int t) {       /* Comet Thrust: coil, lunge through ring bursts */
    static const float V[] = { 11, 10, 8.5f, 6.5f, 4.5f, 2.6f, 1.2f };
    show(s, j, SC_THRUST, (float)(t < 6 ? 0 : t < 11 ? 1 : t < 16 ? 2 : 3));
    if (t == 1) { home(s, j, 46, 5); play(s, SND_BALL_CHARGE, 1.6); }
    if (t >= 6 && t < 13) { dash(s, j, V[t - 6]); j->smear = 1; j->ghosting = 1; }
    else { stop(s); j->smear = 0; j->ghosting = 0; }
    float x = sx_(s), y = sy_(s);
    if (t == 6) {
        play(s, SND_WOOSH3, 1.2); play_c(s, SCS_SLASH, 1.3);
        fx_at(j, SC_DASH, x - j->dir * 24, y - 30, j->dir, 1, 0, 2, 1);
        squash(j, 1.18f, 0.88f);
    }
    if (t == 8) {
        melee(s, j, 38, -32, SPR_MASK32, 1.9f, 1.0f, 0.55, 3, -1, 14, 0, SPR_HIT_1);
        for (int k = 0; k < 3; k++)                          /* rings burst around the thrust line */
            ring(j, x + j->dir * (34 + 16 * k), y - 32, 4, 20 + 5 * k, 0.34f, 2.2f, 14 + 3 * k, C_VIOLET, 1.0f, 1);
    }
    if (t == 11) {
        melee(s, j, 40, -32, SPR_MASK32, 2.0f, 1.0f, 0.6, 6, -3, 18, 0, SPR_HIT_3);
        rift(s, j, 52, -32, 0, 1.15f, 0);
        fx_at(j, SC_VL_TIP, x + j->dir * 60, y - 32, j->dir, 1, 0, 1, 1);
        play_c(s, SCS_RIP, 1.2);
        camera_shake(2);
    }
}
static void step_orbit(CInstance *s, Scy *j, int t) {        /* Orbit Reap: full spin, hits front and behind */
    static const int K[] = { 0, 3, 7, 10, 13, 16, 20, 24 };
    show(s, j, SC_A3, (float)kf(t, K, 8));
    if (t == 1) home(s, j, 30, 3);
    j->ghosting = (t >= 3 && t < 22);
    if (t >= 16 && t < 24) dash(s, j, 2.6f); else stop(s);
    if (t == 3) {
        arc(s, j, SC_ARC_ORBIT_B, -4, -36);
        ring(j, sx_(s), sy_(s) - 2, 16, 66, 0.26f, 3.2f, 22, C_VIOLET, 0.9f, 0);
        play_c(s, SCS_SPIN, 0.95);
    }
    if (t == 4) { melee(s, j, 30, -34, SPR_MASK32, 1.5f, 1.5f, 0.45, 3, -2, 14, 0, SPR_HIT_1); rift(s, j, 36, -36, -10, 0.8f, 0); play_c(s, SCS_SLASH, 1.0); }
    if (t == 10) { melee(s, j, -28, -34, SPR_MASK32, 1.5f, 1.5f, 0.45, 3, -2, 14, 0, SPR_HIT_1); rift(s, j, -34, -34, 10, 0.8f, 0); play_c(s, SCS_SLASH, 1.1); }
    if (t == 17) { melee(s, j, 32, -30, SPR_MASK32, 1.6f, 1.5f, 0.55, 4, -3, 16, 0, SPR_HIT_3); rift(s, j, 40, -30, 20, 0.9f, 0); play_c(s, SCS_SLASH, 1.2); play_c(s, SCS_RIP, 1.1); }
}
static void step_cleave(CInstance *s, Scy *j, int t) {       /* Event Horizon Cleave: leap, flip, slam, giant tear */
    static const int K[] = { 0, 5, 8, 11, 14, 18, 21, 34 };
    show(s, j, SC_A4, (float)kf(t, K, 8));
    if (t == 5) {
        int tid = -1;
        CInstance *e = nearest_enemy(s, &tid, 220, 120);
        float dx = e ? ((float)sget(e, &g_VAR_x) - sx_(s)) * j->dir - 22 : 40;
        if (dx < 12) dx = 12;
        if (dx > 120) dx = 120;
        j->home_v = dx / 13.0f;                              /* lands right on him */
        bset(s, &g_VAR_vspeed, -7.6); play(s, SND_WOOSH3, 0.95);
        squash(j, 0.85f, 1.2f);
        debris(j, sx_(s), sy_(s), 4, 0.6f);
    }
    if (t > 5 && t < 18) { dash(s, j, j->home_v); j->ghosting = 1; }
    if (t == 18) { bset(s, &g_VAR_vspeed, 10.5); stop(s); arc(s, j, SC_ARC_CLEAVE_B, 18, -60); play_c(s, SCS_SLASH, 0.8); }
    if (t > 18) stop(s);
    if (t == 21) {
        float x = sx_(s), y = sy_(s);
        j->ghosting = 0;
        rift(s, j, 30, -48, 90, 0.85f, 1);
        melee(s, j, 30, -40, SPR_MASK64, 1.3f, 1.7f, 1.0, 2, -2, 24, 0, SPR_HIT_3);
        ring(j, x + j->dir * 26, y - 1, 8, 100, 0.24f, 5.0f, 24, C_VIOLET, 1.0f, 0);
        debris(j, x + j->dir * 26, y, 12, 1.0f);
        squash(j, 1.22f, 0.8f);
        camera_shake(3);
        play_c(s, SCS_RIP, 0.8); play(s, SND_STRONG2, 0.9);
    }
    if (t == 27) ring(j, sx_(s) + j->dir * 26, sy_(s) - 1, 6, 62, 0.24f, 3.0f, 18, C_WHITE, 0.7f, 0);
    if (t == 40) {                                            /* the tear snaps shut: knockdown */
        float x = sx_(s) + j->dir * 30, y = sy_(s) - 40;
        Hit h = { my_dmg(s) * 1.25, j->dir * 8.0, -8.0, 30, 7, 1.6, 1.6, SPR_MASK64, 1, 1, 1, 1, SPR_HIT_3, C_VIOLET, 2 };
        spawn_hit(s, x, y, &h);
        fx_at(j, SC_BH_BURST, x, y, 0.55f, 0.55f, 0, 2, 1);
        camera_shake(4);
        play_c(s, SCS_COLLAPSE, 1.2);
    }
}
/* run + attack ---------------------------------------------------------------------------------- */
static void step_dash(CInstance *s, Scy *j, int t) {         /* Meteor Dash: straight through him */
    show(s, j, SC_DASHATK, (float)(t < 4 ? 0 : t < 11 ? 1 : t < 17 ? 2 : 3));
    if (t < 3) dash(s, j, 6.0f);
    else if (t < 12) { dash(s, j, 11.0f); j->smear = 1; j->ghosting = 1; }
    else if (t < 20) { dash(s, j, (20 - t) * 0.7f); j->smear = 0; j->ghosting = 0; }
    else stop(s);
    float x = sx_(s), y = sy_(s);
    if (t == 3) { play(s, SND_WOOSH3, 1.1); play_c(s, SCS_SLASH, 1.15); fx_at(j, SC_DASH, x - j->dir * 20, y - 28, j->dir, 1, 0, 2, 1); }
    if (t == 6 || t == 9) melee(s, j, 18, -30, SPR_MASK32, 1.8f, 1.5f, 0.55, 4, -2, 14, 0, SPR_HIT_1);
    if (t == 11) {                                            /* the cut he left behind him splits open */
        rift_at(j, x - j->dir * 40, y - 30, 0, 1.4f, 0, 60);
        arc(s, j, SC_ARC_SWEEP_B, 6, -30);
        play_c(s, SCS_RIP, 1.05);
    }
    if (t == 13 || t == 16) { debris(j, x, y, 2, 0.5f); ring(j, x, y - 1, 4, 22, 0.25f, 2.0f, 12, C_DUSK, 0.6f, 0); }
}
/* combo B ------------------------------------------------------------------------------------ */
static void step_b1(CInstance *s, Scy *j, int t) {           /* Crescent Throw: buzzsaw boomerang */
    int f = t < 5 ? 0 : 1;
    if (j->th_on && t >= 7) f = t < 20 ? 2 : 3;
    if (!j->th_on && t > 6) f = (t < j->dur - 6) ? 4 : 5;
    show(s, j, SC_B1, (float)f);
    stop(s);
    j->wmode = (j->th_on ? W_HIDDEN : W_META);
    if (t == 1) home(s, j, 9999, 1);                          /* only turns to face him */
    if (t == 6) {
        const ScyFrame *m = frame_meta(s);
        j->th_on = 1; j->th_t = 0; j->th_hits = 0;
        j->th_x = sx_(s) + j->dir * (m ? m->gx / 2.0f : 20); j->th_y = sy_(s) + (m ? m->gy / 2.0f : -36);
        j->th_vx = j->dir * 9.8f; j->th_ang = 0;
        play_c(s, SCS_SPIN, 1.05); play(s, SND_WOOSH2, 0.9);
    }
    if (j->th_on && t > 6) j->dur = t + 12;                   /* hold the pose until it comes back */
}
static void thrown_step(CInstance *s, Scy *j) {
    if (!j->th_on) return;
    j->th_t++;
    j->th_ang = wrap360(j->th_ang + 34);
    j->th_x += j->th_vx;
    j->th_vx -= j->dir * 0.36f;
    float hx = sx_(s) + j->dir * 18, hy = sy_(s) - 36;
    j->th_y += (hy - j->th_y) * 0.06f;
    if (j->th_t % 6 == 3 && j->th_hits < 4 && parent_ok(s)) {
        Hit h = { my_dmg(s) * 0.38, j->th_vx > 0 ? 2.0 : -2.0, -1.0, 12, 4, 1.4, 1.0, SPR_MASK32, 1, 0, 1, 0, SPR_HIT_1, C_VIOLET, 1 };
        spawn_hit(s, j->th_x, j->th_y, &h);
        j->th_hits++;
    }
    if (j->th_t % 9 == 5) rift_at(j, j->th_x, j->th_y, 0, 0.5f, 0, 40);
    float d = j->th_x - hx;
    if ((j->th_t > 16 && fabsf_(d) < 16) || j->th_t > 70) {   /* caught */
        j->th_on = 0;
        play(s, SND_STRONG1, 1.3);
        squash(j, 1.1f, 0.92f);
    }
}
static void step_vault(CInstance *s, Scy *j, int t) {        /* Spur Vault: vault, double spur kick, rip */
    static const int K[] = { 0, 4, 7, 11, 17, 25 };
    show(s, j, SC_B2, (float)kf(t, K, 6));
    if (t == 1) home(s, j, 34, 3);
    if (t == 2) play(s, SND_STRONG1, 0.85);
    if (t == 4) { bset(s, &g_VAR_vspeed, -5.6); dash(s, j, 2.2f); ring(j, sx_(s), sy_(s) - 1, 4, 26, 0.25f, 2.0f, 12, C_DUSK, 0.6f, 0); }
    if (t > 4 && t < 17) dash(s, j, 1.6f); else if (t >= 17) stop(s);
    if (t == 7) { melee(s, j, 22, -26, SPR_MASK24, 1.3f, 1.3f, 0.5, 3, -2, 14, 0, SPR_HIT_1); play(s, SND_WOOSH1, 1.2); }
    if (t == 11) { melee(s, j, 22, -22, SPR_MASK24, 1.3f, 1.3f, 0.5, 3, -2, 14, 0, SPR_HIT_1); play(s, SND_WOOSH2, 1.2); }
    if (t == 17) {
        melee(s, j, 26, -40, SPR_MASK32, 1.3f, 1.8f, 0.75, 2, -6.5, 20, 0, SPR_HIT_3);
        arc(s, j, SC_ARC_RISE_B, 10, -26);
        rift(s, j, 30, -36, -70, 1.0f, 0);
        play_c(s, SCS_SLASH, 1.0); play_c(s, SCS_RIP, 1.0);
    }
    if (t == 25) squash(j, 1.12f, 0.9f);
}
/* can the rooster stand at (x, y)? no solid there and inside the room */
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
/* blink through the opponent to his other side and turn round (Phase Step) */
static void blink(CInstance *s, Scy *j) {
    float x = sx_(s), y = sy_(s);
    ghost_c(s, j, C_VIOLET, 0.7f);
    rift_at(j, x, y - 36, 90, 0.45f, 0, 30);
    int tid = -1;
    CInstance *e = nearest_enemy(s, &tid, 200, 90);
    float nx = e ? (float)sget(e, &g_VAR_x) + j->dir * 30 : x + j->dir * 56;
    if (free_at(s, nx, y)) bset(s, &g_VAR_x, nx);
    if (e) {                                                  /* he is behind us now: turn round */
        j->dir = -j->dir;
        bset(s, &g_VAR_image_xscale, j->dir);
    }
    play(s, SND_MAGIC3, 1.5);
    j->blink = 0;
    rift_at(j, sx_(s), y - 36, 90, 0.45f, 0, 30);
}
static void step_phase(CInstance *s, Scy *j, int t) {        /* Phase Step: blinks through him three times */
    int f = t < 4 ? 0 : t < 12 ? 1 : t < 20 ? 2 : 3;
    show(s, j, SC_PHASE, (float)f);
    stop(s);
    if (t == 4 || t == 12 || t == 20) blink(s, j);
    if (t == 5) {
        melee(s, j, 24, -38, SPR_MASK32, 1.5f, 1.6f, 0.45, 3, -2, 14, 0, SPR_HIT_1);
        arc(s, j, SC_ARC_STITCHA_B, 16, -40);
        play_c(s, SCS_SLASH, 1.15);
    }
    if (t == 13) {
        melee(s, j, 26, -20, SPR_MASK32, 1.6f, 1.2f, 0.45, 3, -2, 14, 0, SPR_HIT_1);
        arc(s, j, SC_ARC_SWEEP_B, 10, -22);
        play_c(s, SCS_SLASH, 1.25);
    }
    if (t == 21) {                                            /* launcher from the third side */
        melee(s, j, 24, -36, SPR_MASK32, 1.5f, 1.8f, 0.7, 3, -6.5, 20, 0, SPR_HIT_3);
        arc(s, j, SC_ARC_RISE_B, 8, -26);
        rift(s, j, 30, -40, -70, 1.0f, 0);
        play_c(s, SCS_SLASH, 0.95); play_c(s, SCS_RIP, 1.15);
    }
}
static void step_stitch(CInstance *s, Scy *j, int t) {       /* Dimensional Stitch: six fast cuts */
    int f = t < 26 ? (t / 4) % 5 : 5;
    show(s, j, SC_B3, (float)f);
    if (t == 1) home(s, j, 30, 3);
    if (t < 24) dash(s, j, 0.7f); else stop(s);
    if (t < 24 && t % 4 == 2) {
        int i = t / 4;
        melee(s, j, 26, -34 + (i % 2 ? 6 : -6), SPR_MASK24, 1.4f, 1.3f, 0.24, 2, -1, 10, 0, SPR_HIT_1);
        arc(s, j, i % 2 ? SC_ARC_STITCHB_B : SC_ARC_STITCHA_B, 18, -36);
        rift(s, j, 30 + 4 * i, -46 + (i % 2) * 16, i % 2 ? 50 : -50, 0.55f, 0);
        play_c(s, SCS_SLASH, 1.0 + 0.06 * i);
    }
    if (t == 23) play_c(s, SCS_RIP, 1.2);
}
static CInstance *nearest_enemy(CInstance *s, int *out_id, float maxdx, float maxdy);
static void step_rend(CInstance *s, Scy *j, int t) {         /* Singular Rend: through a portal, cut from behind */
    static const int K[] = { 0, 5, 9, 13, 18, 22, 32 };
    show(s, j, SC_B4, (float)kf(t, K, 7));
    if (t == 6) { portal_at(j, sx_(s) + j->dir * 30, sy_(s) - 44, 0.7f, 30); play_c(s, SCS_RIP, 0.9); }
    if (t >= 9 && t < 14) { dash(s, j, 2.6f); j->alpha = 1 - (t - 9) / 5.0f; j->ghosting = 1; }
    else stop(s);
    if (t == 14) {
        int tid = -1;
        CInstance *e = nearest_enemy(s, &tid, 260, 140);
        float nx = sx_(s) + j->dir * 90;
        if (e) nx = (float)sget(e, &g_VAR_x) + j->dir * 34;
        if (free_at(s, nx, sy_(s))) {
            bset(s, &g_VAR_x, nx);
            j->dir = -j->dir;
            bset(s, &g_VAR_image_xscale, j->dir);
        }
        portal_at(j, sx_(s) - j->dir * 4, sy_(s) - 44, 0.7f, 30);
        play(s, SND_MAGIC3, 1.2);
    }
    if (t >= 14 && t < 19) j->alpha = (t - 14) / 5.0f;
    if (t >= 19) { j->alpha = 1; j->ghosting = 0; }
    if (t == 24) {
        float x = sx_(s), y = sy_(s);
        Hit h = { my_dmg(s) * 1.3, j->dir * 7.0, -7.0, 30, 7, 1.4, 1.4, SPR_MASK64, 1, 1, 1, 1, SPR_HIT_3, C_VIOLET, 2 };
        spawn_hit(s, x + j->dir * 28, y - 32, &h);
        fx_at(j, SC_IMPACT, x + j->dir * 30, y - 32, j->dir * 0.6f, 0.6f, 0, 1, 1);
        arc(s, j, SC_ARC_SWEEP_B, 16, -32);
        rift(s, j, 36, -32, 0, 1.0f, 0);
        ring(j, x + j->dir * 20, y - 1, 8, 70, 0.24f, 3.5f, 18, C_VIOLET, 0.9f, 0);
        debris(j, x + j->dir * 24, y, 6, 0.8f);
        camera_shake(3);
        play_c(s, SCS_SLASH, 0.9); play(s, SND_STRONG2, 1.0);
    }
}
/* crouch / air --------------------------------------------------------------------------------- */
static void step_crouch_a(CInstance *s, Scy *j, int t) {     /* Ground Reaper: low sweep that trips */
    show(s, j, SC_CROUCHATK, t < 4 ? 0 : t < 9 ? 1 : 2);
    if (t == 1) home(s, j, 30, 3);
    stop(s);
    if (t == 4) {
        float x = sx_(s), y = sy_(s);
        Hit h = { my_dmg(s) * 0.9, j->dir * 4.0, -4.0, 20, 7, 1.7, 0.9, SPR_MASK24, 1, 1, 1, 1, SPR_HIT_1, C_VIOLET, 1 };
        spawn_hit(s, x + j->dir * 28, y - 10, &h);
        fx_at(j, SC_HITFX, x + j->dir * 28, y - 10, 0.6f, 0.6f, 0, 1, 1);
        arc(s, j, SC_ARC_SWEEP_B, 12, -14);
        rift(s, j, 34, -6, 0, 0.8f, 0);
        ring(j, x + j->dir * 24, y - 1, 4, 34, 0.25f, 2.0f, 12, C_DUSK, 0.6f, 0);
        debris(j, x + j->dir * 26, y, 3, 0.5f);
        play_c(s, SCS_SLASH, 1.1);
    }
}
static void step_crouch_b(CInstance *s, Scy *j, int t) {     /* Rising Moon: springs up, vertical crescent launcher */
    show(s, j, SC_CROUCHB, (float)(t < 4 ? 0 : t < 9 ? 1 : t < 18 ? 2 : 3));
    if (t == 1) home(s, j, 28, 3);
    if (t > 4 && t < 12) dash(s, j, 1.2f); else stop(s);
    if (t == 4) {
        bset(s, &g_VAR_vspeed, -4.8);
        arc(s, j, SC_ARC_RISE_B, 6, -30);
        squash(j, 0.86f, 1.18f);
        play_c(s, SCS_SLASH, 0.9); play(s, SND_WOOSH2, 1.1);
    }
    if (t == 5) {
        float x = sx_(s), y = sy_(s);
        Hit h = { my_dmg(s) * 0.9, j->dir * 2.0, -9.5, 26, 7, 1.4, 2.0, SPR_MASK32, 1, 1, 1, 1, SPR_HIT_3, C_VIOLET, 2 };
        spawn_hit(s, x + j->dir * 24, y - 40, &h);
        fx_at(j, SC_HITFX, x + j->dir * 24, y - 40, 0.7f, 0.7f, 45, 1, 1);
        rift(s, j, 26, -48, 80, 0.9f, 0);
    }
}
static void step_air_a(CInstance *s, Scy *j, int t) {        /* Falling Star: twirls like a buzzsaw */
    show(s, j, SC_AIRATK, t < 12 ? (float)((t / 3) % 2) : 2);
    if (t < 12) { j->wmode = W_ORBIT; j->wang += 38; } else j->wmode = W_META;
    if (t == 2) { arc(s, j, SC_ARC_SPIN_B, 20, -34); play_c(s, SCS_SPIN, 1.2); }
    if (t == 3 || t == 9) melee(s, j, 20, -30, SPR_MASK32, 1.5f, 1.5f, 0.5, 2, 3, 14, 0, SPR_HIT_1);
}
/* the dives: hit the ground -> crater (Sky Splitter, Gravity Drop) */
static void impact(CInstance *s, Scy *j, double k, float big) {
    float x = sx_(s), y = sy_(s);
    Hit h = { my_dmg(s) * k, j->dir * 4.0, -7.0, 26, 7, 1.6 * big, 1.2, SPR_MASK64, 1, 1, 1, 1, SPR_HIT_3, C_VIOLET, 2 };
    spawn_hit(s, x + j->dir * 10, y - 16, &h);
    rift_at(j, x + j->dir * 6, y - 3, 0, 0.55f * big, 1, 70)->back = 1;   /* the crater, behind his feet */
    ring(j, x, y - 1, 10, 90 * big, 0.24f, 4.5f, 22, C_VIOLET, 1.0f, 0);
    ring(j, x, y - 1, 6, 52 * big, 0.24f, 2.5f, 16, C_WHITE, 0.7f, 0);
    debris(j, x, y, (int)(10 * big), 1.0f);
    squash(j, 1.25f, 0.78f);
    camera_shake(3 + (big > 1 ? 1 : 0));
    play_c(s, SCS_RIP, 0.85); play(s, SND_STRONG2, 0.85);
}
static void step_sky(CInstance *s, Scy *j, int t) {          /* Sky Splitter: diving diagonal cleave */
    if (t <= 4) { show(s, j, SC_AIRATK2, 0); stop(s); bset(s, &g_VAR_vspeed, -1.2); return; }
    if (!j->landed) {
        show(s, j, SC_AIRATK2, 1);
        if (t == 5) { arc(s, j, SC_ARC_CLEAVE_B, 14, -40); play(s, SND_WOOSH3, 1.05); play_c(s, SCS_SLASH, 1.0); }
        bset(s, &g_VAR_vspeed, 9.5); dash(s, j, 4.5f);
        j->ghosting = 1; j->smear = 1;
        if (t == 6 || t == 10) melee(s, j, 22, -18, SPR_MASK32, 1.5f, 1.6f, 0.4, 3, 6, 12, 0, SPR_HIT_1);
        if ((t > 6 && !on_air(s)) || t >= 40) {
            j->landed = 1; j->land_t = t; j->ghosting = 0; j->smear = 0;
            stop(s);
            impact(s, j, 1.0, 1.0f);
        }
    } else {
        show(s, j, SC_AIRATK2, 2); stop(s);
        if (t >= j->land_t + 14) end_move(s, j);
    }
}
static void step_air_b(CInstance *s, Scy *j, int t) {        /* Gravity Drop: straight down, blades first */
    if (t <= 6) {
        show(s, j, SC_AIRB, 0); stop(s);
        if (t == 1) { bset(s, &g_VAR_vspeed, -3.5); play_c(s, SCS_SPIN, 0.85); }
        return;
    }
    if (!j->landed) {
        show(s, j, SC_AIRB, 1); stop(s);
        bset(s, &g_VAR_vspeed, 11);
        j->ghosting = 1; j->smear = 1;
        if (t == 7) play(s, SND_WOOSH3, 0.8);
        if (t % 5 == 0) melee(s, j, 4, -6, SPR_MASK32, 1.3f, 1.3f, 0.3, 0, 4, 10, 0, SPR_HIT_1);
        if ((t > 7 && !on_air(s)) || t >= 48) {
            j->landed = 1; j->land_t = t; j->ghosting = 0; j->smear = 0;
            impact(s, j, 1.2, 1.25f);
        }
    } else {
        show(s, j, SC_AIRB, 2); stop(s);
        if (t >= j->land_t + 16) end_move(s, j);
    }
}

/* distance to the opponent in front of him (9999: nobody there) */
static float front_gap(CInstance *s, Scy *j) {
    int tid = -1;
    CInstance *e = nearest_enemy(s, &tid, 260, 70);
    if (!e) return 9999;
    float dx = ((float)sget(e, &g_VAR_x) - sx_(s)) * j->dir;
    return dx > -6 ? dx : 9999;
}

static void combo_step(CInstance *s, Scy *j) {
    j->t++;
    int t = j->t;
    j->gap = front_gap(s, j);
    switch (j->step) {
    case ST_A1: step_a1(s, j, t); break;
    case ST_A2: step_a2(s, j, t); break;
    case ST_THRUST: step_thrust(s, j, t); break;
    case ST_ORBIT: step_orbit(s, j, t); break;
    case ST_CLEAVE: step_cleave(s, j, t); break;
    case ST_DASH_A: case ST_DASH_B: step_dash(s, j, t); break;
    case ST_B1: step_b1(s, j, t); break;
    case ST_VAULT: step_vault(s, j, t); break;
    case ST_PHASE: step_phase(s, j, t); break;
    case ST_STITCH: step_stitch(s, j, t); break;
    case ST_REND: step_rend(s, j, t); break;
    case ST_CROUCH_A: step_crouch_a(s, j, t); break;
    case ST_CROUCH_B: step_crouch_b(s, j, t); break;
    case ST_AIR_A: step_air_a(s, j, t); break;
    case ST_SKY: step_sky(s, j, t); break;
    case ST_AIR_B: step_air_b(s, j, t); break;
    }
    if (j->move != MV_COMBO) return;                         /* the move ended itself */
    if (j->home_t > 0) {                                      /* homing lunge on top of the move's motion */
        j->home_t--;
        bset(s, &g_VAR_hspeed, sget(s, &g_VAR_hspeed) + j->dir * j->home_v);
    }
    if (!j->pass) {                                           /* stop at contact instead of walking through him */
        float fwd = (float)sget(s, &g_VAR_hspeed) * j->dir, room = j->gap - 24;
        if (room < 0) room = 0;
        if (fwd > room) bset(s, &g_VAR_hspeed, j->dir * room);
    }
    if (t > j->dur) end_move(s, j);                           /* (alarm[2] chains the next move at t = dur) */
}

/* alarm[3]: start of an attack (scr_plr_step sets combo_next) */
void gml_Object_o_scyther_Alarm_3(CInstance *s, CInstance *o) {
    if (parent_ok(s)) pset_b(s, &g_VAR_is_attacking, true);
    scy_start(s, o, (int)iget(s, &g_VAR_combo_next));
}

/* alarm[2]: the current move's window is over -> chain the next one or finish (scr_alarm2_combo) */
void gml_Object_o_scyther_Alarm_2(CInstance *s, CInstance *o) {
    Scy *j = slot(s, true);
    if (j->move == MV_SPECIAL) return;
    double next = iget(s, &g_VAR_combo_next);
    RValue *nc = var_slot_r(s, g_VAR_combo_nextcombo.id);
    if (j->th_on) { bset_i(s, &g_VAR_alarm, 2, 6); return; }     /* wait for the thrown scythe */
    if (j->move == MV_COMBO && (j->step == ST_SKY || j->step == ST_AIR_B)) {
        bset_i(s, &g_VAR_alarm, 2, 4); return;                     /* still diving / landing */
    }
    if (nc && BOOL_RValue(nc) && next > 0) {
        scy_start(s, o, (int)next);
        return;
    }
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
/* skill 1 - Event Horizon                                                                     */
/* ------------------------------------------------------------------------------------------ */
static void start_skill1(CInstance *s, Scy *j) {
    j->move = MV_SKILL1; j->t = 0; j->dir = facing(s); j->dur = 40; j->wmode = W_META;
    iset(s, &g_VAR_combo_next, -1);
    bset_i(s, &g_VAR_alarm, 2, 40);
    show(s, j, SC_CAST1, 0);
    stop(s);
    play(s, SND_MAGICSTUN_CAST, 0.9);
}
static void skill1_step(CInstance *s, Scy *j) {
    int t = ++j->t;
    int f = t < 8 ? 0 : t < 20 ? 1 + ((t / 3) % 2) : t < 26 ? 3 : 4;
    show(s, j, SC_CAST1, (float)f);
    stop(s);
    j->wmode = (t >= 8 && t < 20) ? W_ORBIT : W_META;
    if (j->wmode == W_ORBIT) j->wang += 32;
    if (t == 20) {
        j->bh_on = 1; j->bh_t = 0;
        j->bh_x = sx_(s) + j->dir * 96; j->bh_y = sy_(s) - 40;
        ring(j, j->bh_x, j->bh_y + 38, 10, 80, 0.24f, 4.0f, 24, C_VIOLET, 0.9f, 0);
        play_c(s, SCS_BH, 1.0); play(s, SND_MAGIC3, 0.7);
        camera_shake(2);
    }
    if (t > j->dur) end_move(s, j);
}
/* drag every opponent near the hole toward it */
static void pull_enemies(CInstance *s, Scy *j) {
    RValue me = rv_undef();
    YYGML_Variable_GetValue(parent_of(s), g_VAR_plr_team.id, ARRAY_INDEX_NONE, &me, false, false);
    double my_team = rv_num(&me); rv_free(&me);
    int cnt = inst_count(s, OBJ_PARENT_CHARACTER);
    for (int i = 0; i < cnt; i++) {
        int iid = -1;
        CInstance *c = inst_nth(s, OBJ_PARENT_CHARACTER, i, &iid);
        if (!c || c == s) continue;
        RValue cp = rv_undef(); RValue id = rv_real(iid);
        YYGML_Variable_GetValue(&id, g_VAR_parent.id, ARRAY_INDEX_NONE, &cp, false, false);
        bool ok = inst_exists_rv(s, &cp);
        double team = ok ? get_rv(&cp, &g_VAR_plr_team, ARRAY_INDEX_NONE) : my_team;
        rv_free(&cp);
        if (!ok || team == my_team) continue;
        float ex = (float)sget(c, &g_VAR_x), ey = (float)sget(c, &g_VAR_y) - 30;
        float dx = j->bh_x - ex, dy = j->bh_y - ey;
        if (fabsf_(dx) > 160 || fabsf_(dy) > 110) continue;
        float step = dx * 0.06f;
        if (step > 2.2f) step = 2.2f;
        if (step < -2.2f) step = -2.2f;
        RValue r = rv_undef();
        RValue pa[3] = { rv_real(ex + step), rv_real(ey + 30), rv_real(OBJ_PARENT_SOLID) };
        F_PlaceMeeting(&r, c, c, 3, pa);
        bool blocked = rv_num(&r) > 0.5; rv_free(&r);
        if (!blocked) bset(c, &g_VAR_x, ex + step);
    }
}
static void blackhole_step(CInstance *s, Scy *j) {
    if (!j->bh_on) return;
    int t = ++j->bh_t;
    if (parent_ok(s)) {
        pull_enemies(s, j);
        if (t % 8 == 4 && t < 80) {
            Hit h = { my_dmg(s) * 0.22, 0, -1, 14, 3, 1.4, 1.4, SPR_MASK64, 1, 0, 1, 0, SPR_HIT_5, C_VIOLET, 1 };
            spawn_hit(s, j->bh_x, j->bh_y, &h);
        }
    }
    if (t == 80) {                                             /* collapse */
        if (parent_ok(s)) {
            Hit h = { my_dmg(s) * 1.4, j->dir * 9.0, -8.0, 30, 6, 2.0, 2.0, SPR_MASK64, 1, 1, 1, 1, SPR_HIT_3, C_VIOLET, 2 };
            spawn_hit(s, j->bh_x, j->bh_y, &h);
        }
        fx_at(j, SC_BH_BURST, j->bh_x, j->bh_y, 1, 1, 0, 2, 1);
        ring(j, j->bh_x, j->bh_y + 38, 12, 120, 0.24f, 5.0f, 26, C_VIOLET, 1.0f, 0);
        debris(j, j->bh_x, j->bh_y + 38, 10, 1.1f);
        play_c(s, SCS_COLLAPSE, 1.0);
        camera_shake(4);
        j->bh_on = 0;
    }
}

/* ------------------------------------------------------------------------------------------ */
/* skill 2 - Void Lance                                                                        */
/* ------------------------------------------------------------------------------------------ */
static void start_skill2(CInstance *s, Scy *j) {
    j->move = MV_SKILL2; j->t = 0; j->dir = facing(s); j->dur = 56; j->wmode = W_META;
    iset(s, &g_VAR_combo_next, -1);
    bset_i(s, &g_VAR_alarm, 2, 56);
    show(s, j, SC_CAST2, 0);
    stop(s);
    play(s, SND_BALL_CHARGE, 0.85);
}
static void skill2_step(CInstance *s, Scy *j) {
    int t = ++j->t;
    int f = t < 6 ? 0 : t < 10 ? 1 : t < 24 ? 2 : t < 42 ? 3 : 4;
    show(s, j, SC_CAST2, (float)f);
    stop(s);
    if (t == 8) {
        j->eye_on = 1; j->eye_t = 0;
        j->eye_x = sx_(s) + j->dir * 40; j->eye_y = sy_(s) - 38;
        rift_at(j, j->eye_x, j->eye_y, 90, 0.42f, 1, 66);
        play_c(s, SCS_RIP, 0.85);
    }
    if (t == 24) {
        j->beam_on = 1; j->beam_t = 0; j->beam_len = 0; j->beam_dir = j->dir;
        j->beam_x = j->eye_x; j->beam_y = j->eye_y;
        ring(j, j->eye_x + j->dir * 10, j->eye_y, 6, 30, 0.34f, 3.0f, 16, C_VIOLET, 1.0f, 1);
        play_c(s, SCS_BEAM, 1.0);
        camera_shake(2);
    }
    if (t > j->dur) end_move(s, j);
}
static void lance_step(CInstance *s, Scy *j) {
    if (j->eye_on && ++j->eye_t > 68) j->eye_on = 0;
    if (!j->beam_on) return;
    int t = ++j->beam_t;
    j->beam_len += (360.0f - j->beam_len) * 0.3f;
    if (t % 4 == 0 && t <= 40 && parent_ok(s)) {
        Hit h = { my_dmg(s) * 0.2, j->beam_dir * 1.5, -0.5, 10, 3, j->beam_len / 64.0, 0.45, SPR_MASK64, 1, 0, 1, 0, SPR_HIT_5, C_VIOLET, 1 };
        spawn_hit(s, j->beam_x + j->beam_dir * j->beam_len * 0.5f, j->beam_y, &h);
    }
    if (t % 10 == 5 && t <= 40)                              /* rings travelling down the beam */
        ring(j, j->beam_x + j->beam_dir * (40 + 6 * t), j->beam_y, 4, 18, 0.34f, 2.0f, 12, C_VIOLET, 0.8f, 1);
    if (t == 44) {
        float nx = j->beam_x + j->beam_dir * j->beam_len, ny = j->beam_y;
        if (parent_ok(s)) {
            Hit h = { my_dmg(s) * 1.2, j->beam_dir * 10.0, -9.0, 30, 6, 1.6, 1.6, SPR_MASK64, 1, 1, 1, 1, SPR_HIT_3, C_VIOLET, 2 };
            spawn_hit(s, nx, ny, &h);
        }
        fx_at(j, SC_VL_NOVA, nx, ny, 1, 1, 0, 2, 1);
        play(s, SND_EXPLOSION_MEGA, 1.1);
        camera_shake(3);
    }
    if (t >= 56) j->beam_on = 0;
}

/* ------------------------------------------------------------------------------------------ */
/* special - SINGULARITY                                                                       */
/* ------------------------------------------------------------------------------------------ */
static CInstance *nearest_enemy(CInstance *s, int *out_id, float maxdx, float maxdy) {
    *out_id = -1;
    if (!parent_ok(s)) return 0;
    RValue me = rv_undef();
    YYGML_Variable_GetValue(parent_of(s), g_VAR_plr_team.id, ARRAY_INDEX_NONE, &me, false, false);
    double my_team = rv_num(&me); rv_free(&me);
    double mx = sget(s, &g_VAR_x), my = sget(s, &g_VAR_y);
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

static bool special_ready(CInstance *s) {
    if (pget(s, &g_VAR_is_hurt) > 0.5 || pget(s, &g_VAR_is_fallen) > 0.5 || pget(s, &g_VAR_is_dead) > 0.5) return false;
    if (pget(s, &g_VAR_is_onair) > 0.5) return false;
    return true;
}
static bool special_pressed(CInstance *s) {
    if (!parent_ok(s)) return false;
    if (pget(s, &g_VAR_keyp_special) < 0.5 || pget(s, &g_VAR_key_defend) < 0.5) return false;
    return special_ready(s);
}
/* the CPU never holds shield + skill together: when it presses skill with a full bar and the
   opponent in reach, it uses SINGULARITY instead */
static bool cpu_wants_special(CInstance *s) {
    if (!is_cpu(s) || pget(s, &g_VAR_keyp_special) < 0.5 || !special_ready(s)) return false;
    double e = pget(s, &g_VAR_plr_energy), emax = pget(s, &g_VAR_plr_maxenergy);
    double need = emax > 0 ? (emax < 100 ? emax : 100) : 100;
    if (e + 0.001 < need) return false;
    int tid = -1;
    return nearest_enemy(s, &tid, 300, 140) != 0;
}

static void set_target_frozen(CInstance *s, Scy *j, bool frozen) {
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

static void void_activate(CInstance *s, Scy *j);

static void start_special(CInstance *s, Scy *j) {
    pset_b(s, &g_VAR_keyp_special, false);                     /* don't also fire a skill */
    double e = pget(s, &g_VAR_plr_energy), emax = pget(s, &g_VAR_plr_maxenergy);
    double need = emax > 0 ? (emax < 100 ? emax : 100) : 100;
    int tid = -1;
    CInstance *t = nearest_enemy(s, &tid, 420, 180);
    if (e + 0.001 < need || !t) { j->fail_t = 24; play(s, SND_WOOSH3, 0.6); return; }
    pset(s, &g_VAR_plr_energy, e - need);
    j->move = MV_SPECIAL; j->t = 0; j->cut_t = 0; j->hit_done = 0; j->wmode = W_META;
    j->tgt_id = tid;
    j->tgt_x = (float)sget(t, &g_VAR_x); j->tgt_y = (float)sget(t, &g_VAR_y);
    j->dir = j->tgt_x >= sx_(s) ? 1.0f : -1.0f;
    bset(s, &g_VAR_image_xscale, j->dir);
    pset_b(s, &g_VAR_is_attacking, true);
    pset_b(s, &g_VAR_can_gethurt, false);
    iset(s, &g_VAR_combo_next, -1);
    bset_i(s, &g_VAR_alarm, 2, -1);
    j->old_depth = sget(s, &g_VAR_depth); j->depth_saved = 1;
    bset(s, &g_VAR_depth, -15000);                            /* the GUI cutscene draws over the HUD */
    show(s, j, SC_SP, 0);
    stop(s);
    bset(s, &g_VAR_vspeed, 0);
    j->ground_y = sy_(s);
    play(s, SND_SUSPENSE, 1.0);
    camera_shake(2);
}

static void special_step(CInstance *s, Scy *j) {
    int t = ++j->t;
    stop(s);
    bset(s, &g_VAR_vspeed, 0);
    set_target_frozen(s, j, true);
    float tx = j->tgt_x, ty = j->tgt_y - 36;
    if (t <= SP_WIND) {                                      /* overhead twirl, then the X cut */
        int f = t < 10 ? 0 : t < 20 ? 1 : t < 26 ? 2 : t < 32 ? 3 : 4;
        show(s, j, SC_SP, (float)f);
        j->wmode = (t >= 10 && t < 20) ? W_ORBIT : W_META;
        if (j->wmode == W_ORBIT) j->wang += 36;
        if (t == 10) play_c(s, SCS_SPIN, 0.8);
        if (t == 20) { rift_at(j, tx, ty, 45, 1.2f, 0, 60); fx_at(j, SC_ARC_XCUT_F, tx, ty, j->dir, 1, 0, 3, 1); play_c(s, SCS_RIP, 0.8); }
        if (t == 26) { rift_at(j, tx, ty, -45, 1.2f, 0, 54); play_c(s, SCS_RIP, 0.7); camera_shake(3); ring(j, tx, j->tgt_y - 1, 8, 90, 0.24f, 4.0f, 24, C_VIOLET, 1.0f, 0); }
        if (t == SP_WIND) { play_c(s, SCS_BH, 0.85); play(s, SND_THUNDER, 0.6); }
        return;
    }
    if (t <= SP_WIND + SP_CUT) {                             /* the cutscene (drawn in Draw_64) */
        j->cut_t = t - SP_WIND;
        show(s, j, SC_SP, 4);
        int c = j->cut_t;
        if (c == 30) play_c(s, SCS_COLLAPSE, 0.8);
        if (c == 64) { play_c(s, SCS_SHATTER, 1.0); j->shake = 12; }
        if (c == 80) { play_c(s, SCS_SHATTER, 0.85); j->shake = 16; }
        if (c == 120) play(s, SND_MAGIC3, 0.6);
        if (j->shake > 0) j->shake *= 0.9f;
        return;
    }
    if (!j->hit_done) {                                      /* the blow: huge, unblockable - not a K.O. */
        j->hit_done = 1;
        set_target_frozen(s, j, false);
        CInstance *c = j->tgt_id >= 0 ? YYGML_FindInstance(j->tgt_id) : 0;
        if (c) {
            float cx = (float)sget(c, &g_VAR_x), cy = (float)sget(c, &g_VAR_y);
            Hit h = { my_dmg(s) * 12.0, j->dir * 10.0, -9.0, 40, 6, 2.0, 2.0, SPR_MASK64, 1, 1, 0, 1, SPR_HIT_3, C_VIOLET, 2 };
            spawn_hit(s, cx, cy - 28, &h);
            fx_at(j, SC_IMPACT, cx, cy - 30, j->dir, 1, 0, 3, 1);
            fx_at(j, SC_BH_BURST, cx, cy - 30, 0.8f, 0.8f, 0, 2, 1);
            ring(j, cx, cy - 1, 10, 140, 0.24f, 6.0f, 30, C_VIOLET, 1.0f, 0);
            debris(j, cx, cy, 14, 1.3f);
        }
        play(s, SND_WINLOSE_IMPACT, 1.0);
        play_c(s, SCS_KO, 1.0);
        camera_shake(5);
        if (j->depth_saved) { bset(s, &g_VAR_depth, j->old_depth); j->depth_saved = 0; }
        void_activate(s, j);
    }
    show(s, j, SC_SP, 5);
    if (t >= SP_WIND + SP_CUT + SP_AFTER) {
        j->move = MV_NONE; j->anim = -1;
        pset_b(s, &g_VAR_can_gethurt, true);
        bset(s, &g_VAR_image_speed, 0.25);
        bset_i(s, &g_VAR_alarm, 2, 1);
    }
}

static void special_abort(CInstance *s, Scy *j) {
    set_target_frozen(s, j, false);
    if (j->depth_saved) { bset(s, &g_VAR_depth, j->old_depth); j->depth_saved = 0; }
    j->move = MV_NONE; j->anim = -1;
    if (parent_ok(s)) { pset_b(s, &g_VAR_can_gethurt, true); pset_b(s, &g_VAR_is_attacking, false); }
}

/* ------------------------------------------------------------------------------------------ */
/* the void stage                                                                              */
/*   The stages draw their scenery two ways: background / tile / asset layers, and placed       */
/*   instances (o_map_bk paints the whole backdrop from a 900000-deep instance layer, o_tile_*  */
/*   objects are trees, houses, grass).  Everything behind the fighters is hidden - layers with */
/*   layer_set_visible, scenery instances with visible = false (they keep stepping and their    */
/*   collisions) - and Draw Begin paints space, floating rocks and a perspective stone slab on  */
/*   every solid the fighters can stand on.                                                     */
/* ------------------------------------------------------------------------------------------ */
static double arr_len(CInstance *s, RValue *arr) {
    RValue r = rv_undef();
    RValue *args[1] = { arr };
    YYGML_CallLegacyFunction(s, s, &r, 1, g_FUNC_array_length_1d.id, args);
    double d = rv_num(&r);
    rv_free(&r);
    return d;
}
/* the deepest fighter: everything deeper than this is scenery */
static double fighters_depth(CInstance *s) {
    double dmax = sget(s, &g_VAR_depth);
    if (dmax < -1000) dmax = 0;                              /* (during the cutscene we sit at -15000) */
    int cnt = inst_count(s, OBJ_PARENT_CHARACTER);
    for (int i = 0; i < cnt && i < 16; i++) {
        CInstance *c = inst_nth(s, OBJ_PARENT_CHARACTER, i, 0);
        if (!c || c == s) continue;
        double d = sget(c, &g_VAR_depth);
        if (d > dmax) dmax = d;
    }
    return dmax;
}
static void hide_scenery(CInstance *s, double dmax) {
    for (int k = 0; k < N_STAGE_DECOR; k++) {
        int obj = k_stage_decor[k];
        int n = inst_count(s, obj);
        for (int i = 0; i < n && i < 400; i++) {
            CInstance *c = inst_nth(s, obj, i, 0);
            if (c && sget(c, &g_VAR_depth) > dmax) bset(c, &g_VAR_visible, 0);
        }
    }
}
static void hide_layers(CInstance *s, double dmax) {
    /* layers = layer_get_all(); hide the deeper ones that hold no instances (backgrounds, tiles, assets) */
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
static void void_activate(CInstance *s, Scy *j) {
    if (j->void_on) return;
    j->void_on = 1; j->void_t = 0;
    double dmax = fighters_depth(s);
    hide_scenery(s, dmax);
    if (!j->void_hidden) { j->void_hidden = 1; hide_layers(s, dmax); }
}

#define SLAB_BACK 14.0f        /* how far up the top face's far edge sits (px) */
#define SLAB_PERSP 0.84f       /* the far edge is scaled toward the camera centre -> parallax */
#define SLAB_FRONT 48.0f       /* height of the front face sprite */
typedef struct { float l, r, t; } Slab;

static void draw_slab(CInstance *s, const Slab *b, float cx, float vx, float vw, float fade) {
    float x0 = b->l > vx - 80 ? b->l : vx - 80, x1 = b->r < vx + vw + 80 ? b->r : vx + vw + 80;
    if (x1 - x0 < 1) return;
    float T = b->t;
    /* top face, in 64 px chunks aligned to the world so the texture stays put */
    int m0 = (int)(x0 / 64.0f); if (x0 < 0) m0--;
    for (int m = m0; m * 64.0f < x1; m++) {
        float a = m * 64.0f, c = a + 64;
        if (a < x0) a = x0;
        if (c > x1) c = x1;
        if (c - a < 0.5f) continue;
        float fa = cx + (a - cx) * SLAB_PERSP, fc = cx + (c - cx) * SLAB_PERSP;
        spr_pos(s, SC_VOID_TOP, (float)(((m % 4) + 4) % 4), fa, T - SLAB_BACK, fc, T - SLAB_BACK, c, T, a, T, fade);
    }
    /* the end faces you can see from where the camera is */
    float H = SLAB_FRONT * 0.7f;
    if (b->l > cx && b->l >= vx - 80) {
        float fl = cx + (b->l - cx) * SLAB_PERSP;
        spr_pos(s, SC_VOID_TOP, 4, fl, T - SLAB_BACK, b->l, T, b->l, T + H, fl, T - SLAB_BACK + H * SLAB_PERSP, fade);
    }
    if (b->r < cx && b->r <= vx + vw + 80) {
        float fr = cx + (b->r - cx) * SLAB_PERSP;
        spr_pos(s, SC_VOID_TOP, 4, b->r, T, fr, T - SLAB_BACK, fr, T - SLAB_BACK + H * SLAB_PERSP, b->r, T + H, fade);
    }
    /* front face: the 256 px stone strip tiled along the world */
    for (float x = x0; x < x1;) {
        int u = (int)x % 256; if (u < 0) u += 256;
        float w = 256.0f - u;
        if (x + w > x1) w = x1 - x;
        spr_part(s, SC_VOID_FLOOR, 0, (float)u, 0, w, SLAB_FRONT, x, T, fade);
        x += w;
    }
}
static void draw_floor(CInstance *s, Scy *j, float vx, float vy, float vw, float vh, float fade) {
    Slab sl[32]; int n = 0;
    int cnt = inst_count(s, OBJ_PARENT_SOLID);
    for (int i = 0; i < cnt && i < 128 && n < 32; i++) {
        CInstance *c = inst_nth(s, OBJ_PARENT_SOLID, i, 0);
        if (!c) continue;
        float l = (float)sget(c, &g_VAR_bbox_left), r = (float)sget(c, &g_VAR_bbox_right) + 1, t = (float)sget(c, &g_VAR_bbox_top);
        if (r - l < 24 || r < vx - 80 || l > vx + vw + 80 || t > vy + vh + 20 || t < vy - 80) continue;
        /* insertion by (top, left) so the higher (farther looking) slabs draw first */
        int k = n++;
        while (k > 0 && (sl[k - 1].t > t || (sl[k - 1].t == t && sl[k - 1].l > l))) { sl[k] = sl[k - 1]; k--; }
        sl[k].l = l; sl[k].r = r; sl[k].t = t;
    }
    /* merge neighbours at the same height into one slab (no seams between tiles of the floor) */
    int m = 0;
    for (int i = 0; i < n; i++) {
        if (m > 0 && fabsf_(sl[m - 1].t - sl[i].t) < 2 && sl[i].l <= sl[m - 1].r + 2) {
            if (sl[i].r > sl[m - 1].r) sl[m - 1].r = sl[i].r;
        } else sl[m++] = sl[i];
    }
    if (m == 0 && j->ground_y > 0) { sl[0].l = vx - 100; sl[0].r = vx + vw + 100; sl[0].t = j->ground_y; m = 1; }
    float cx = vx + vw * 0.5f;
    for (int i = 0; i < m; i++) draw_slab(s, &sl[i], cx, vx, vw, fade);
}

static const short ROCK_X[10] = { 40, 150, 260, 380, 470, 560, 90, 330, 520, 230 };
static const short ROCK_Y[10] = { 22, 12, 30, 16, 26, 10, 48, 44, 52, 38 };     /* % of view height */
static const unsigned char ROCK_S[10] = { 60, 45, 70, 50, 65, 40, 90, 100, 80, 120 };   /* scale % */

static void draw_void(CInstance *s, Scy *j) {
    j->void_drawn = j->aura_t;
    RValue zero = rv_real(0);
    double cam = fcall1(s, F_ViewGetCamera, zero);
    RValue camv = rv_real(cam);
    float vx = (float)fcall1(s, F_CameraGetViewX, camv), vy = (float)fcall1(s, F_CameraGetViewY, camv);
    float vw = (float)fcall1(s, F_CameraGetViewWidth, camv), vh = (float)fcall1(s, F_CameraGetViewHeight, camv);
    if (vw < 16 || vh < 16) { vw = 600; vh = 300; vx = sx_(s) - 300; vy = sy_(s) - 200; }   /* no camera: around us */
    float fade = j->void_t < 30 ? j->void_t / 30.0f : 1.0f;
    /* deep space */
    if (g_scy_spr[SC_VOID_SKY] >= 0) {
        RValue r = rv_undef();
        RValue a[8] = { rv_real(g_scy_spr[SC_VOID_SKY]), rv_real((j->void_t / 40) % 2), rv_real(vx), rv_real(vy),
                        rv_real(vw), rv_real(vh), rv_real(C_WHITE), rv_real(fade) };
        F_DrawSpriteStretchedExt(&r, s, s, 8, a);
        rv_free(&r);
    }
    /* floating rocks with parallax and a slow bob */
    for (int i = 0; i < 10; i++) {
        float sc = ROCK_S[i] / 100.0f;
        float par = 0.12f + sc * 0.25f;
        float span = vw + 160;
        float rx = ROCK_X[i] - vx * par;
        while (rx < -80) rx += span;
        while (rx > span - 80) rx -= span;
        float bob = sinf_(j->void_t * 0.025f + i * 1.7f) * 3.0f;
        spr(s, SC_VOID_ROCKS, (float)(i % 8), vx + rx, vy + ROCK_Y[i] * vh / 100.0f + bob, sc, sc, 0, sc < 0.6f ? C_DUSK : C_WHITE, fade);
    }
    /* drifting pebbles */
    for (int i = 0; i < 12; i++) {
        float px = (float)((i * 97 + j->void_t / 2) % (int)(vw + 20)) - 10;
        float py = (float)((i * 53) % (int)vh) + sinf_(j->void_t * 0.03f + i) * 6;
        spr(s, SC_VOID_DUST, (float)(i % 8), vx + px, vy + py, 1, 1, 0, C_WHITE, fade * 0.8f);
    }
    /* the ground: a perspective stone slab on every solid the fighters stand on */
    draw_floor(s, j, vx, vy, vw, vh, fade);
}

/* Draw Begin: runs before any layer or instance draws, i.e. behind everything */
void gml_Object_o_scyther_Draw_72(CInstance *s, CInstance *o) {
    (void)o;
    Scy *j = slot(s, false);
    if (!j || !j->void_on) return;
    draw_void(s, j);
}

/* ------------------------------------------------------------------------------------------ */
/* step                                                                                        */
/* ------------------------------------------------------------------------------------------ */
void gml_Object_o_scyther_Step_0(CInstance *s, CInstance *o) {
    Scy *j = slot(s, true);
    j->aura_t++;
    if (j->fail_t > 0) j->fail_t--;
    if (j->void_on) {
        j->void_t++;
        if (j->void_t % 30 == 0 && parent_ok(s)) hide_scenery(s, fighters_depth(s));   /* (new scenery) */
    }
    bool pok = parent_ok(s);

    if (j->move == MV_SPECIAL) {
        if (!pok) special_abort(s, j);
        else special_step(s, j);
        effects_step(s, j); thrown_step(s, j); blackhole_step(s, j); lance_step(s, j);
        weapon_update(s, j);
        return;
    }
    if (pok && j->move == MV_NONE && (special_pressed(s) || cpu_wants_special(s))) {
        start_special(s, j);
        if (j->move == MV_SPECIAL) { weapon_update(s, j); return; }
    }

    RValue ret = rv_undef();
    gml_Script_scr_plr_step(s, o, &ret, 0, 0);             /* the game's movement / input framework */
    rv_free(&ret);

    if (pok && j->move != MV_NONE) {
        if (pget(s, &g_VAR_is_hurt) > 0.5 || pget(s, &g_VAR_is_fallen) > 0.5) {   /* interrupted */
            j->move = MV_NONE; j->anim = -1; j->wmode = W_META; j->ghosting = 0; j->smear = 0; j->alpha = 1; j->home_t = 0;
            bset(s, &g_VAR_image_speed, 0.25);
        } else if (j->move == MV_COMBO) combo_step(s, j);
        else if (j->move == MV_SKILL1) skill1_step(s, j);
        else if (j->move == MV_SKILL2) skill2_step(s, j);
    }
    effects_step(s, j);
    thrown_step(s, j);
    blackhole_step(s, j);
    lance_step(s, j);
    weapon_update(s, j);

    RValue v[2] = { rv_real(0.6), rv_real(1) };
    RValue *args[2] = { &v[0], &v[1] };
    RValue r2 = rv_undef();
    gml_Script_scr_char_charge_effect(s, o, &r2, 2, args);
    rv_free(&r2);
}

/* ------------------------------------------------------------------------------------------ */
/* drawing                                                                                     */
/* ------------------------------------------------------------------------------------------ */
/* the scythe in hand: the frame's angle (tweened in Step), or the 3D orbit sprites */
static void draw_weapon(CInstance *s, Scy *j, float x, float y, float xs, int layer_pass) {
    const ScyFrame *m = frame_meta(s);
    if (!m || (m->fl & 2) || j->wmode == W_HIDDEN || j->th_on) return;
    float gx = x + xs * (m->gx / 2.0f), gy = y + m->gy / 2.0f;
    float wf = (m->fl & 4) ? -1.0f : 1.0f;
    if (j->wmode == W_ORBIT) {                               /* twirl in a tilted plane around the grip */
        int idx = ((int)(wrap360(j->wang) / 18.0f + 0.5f)) % 20;
        if (layer_pass == 0) spr(s, SC_ORBB, (float)idx, gx, gy, xs * wf, 1, 0, C_WHITE, j->alpha);
        else spr(s, SC_ORBF, (float)idx, gx, gy, xs * wf, 1, 0, C_WHITE, j->alpha);
        return;
    }
    int behind = (m->fl & 1) != 0;
    if ((layer_pass == 0) != behind) return;
    if (!j->wdraw_ok) { j->wdraw = (float)m->ang; j->wdraw_ok = 1; }
    int idx = ((int)(j->wdraw / 11.25f + 0.5f)) % 32;
    if (idx < 16) spr(s, SC_WPN0, (float)idx, gx, gy, xs * wf, 1, 0, C_WHITE, j->alpha);
    else spr(s, SC_WPN1, (float)(idx - 16), gx, gy, xs * wf, 1, 0, C_WHITE, j->alpha);
}

static void draw_arcs(CInstance *s, Scy *j, int front) {
    blend(s, 1);
    for (int i = 0; i < N_ARC; i++) {
        ArcFx *a = &j->arcs[i];
        if (!a->on) continue;
        spr(s, a->a + front, a->t / 3.0f, a->x, a->y, a->xs, 1, 0, C_WHITE, 1);
    }
    blend(s, 0);
}
/* rings, blade trails: the far halves behind him, the near halves in front */
static void draw_3d(CInstance *s, Scy *j, int front) {
    blend(s, 1);
    for (int i = 0; i < N_RING; i++) if (j->rings[i].on) draw_ring(s, &j->rings[i], front);
    draw_trail(s, j, 0, front);
    draw_trail(s, j, 1, front);
    blend(s, 0);
    draw_debris(s, j, front);
}

/* reality tears: the hole (normal blend) then its glowing torn edge (additive); portals turn in 3D */
static void draw_rifts(CInstance *s, Scy *j, int back) {
    for (int i = 0; i < N_RIFT; i++) {
        Rift *r = &j->rifts[i];
        if (!r->on || r->back != back) continue;
        float f = rift_frame(r);
        int v = r->big ? SC_RIFTBIG_V : SC_RIFT_V;
        float ys = r->sc;
        if (r->spin) {                                       /* edge-on -> facing us -> edge-on */
            float ph = r->t < 10 ? (10 - r->t) / 10.0f : (r->t > r->life - 10 ? (r->t - (r->life - 10)) / 10.0f : 0);
            ys *= 0.08f + 0.92f * cosf_(ph * PI_F / 2) * (0.9f + 0.1f * sinf_(r->t * 0.4f));
        }
        spr(s, v, f, r->x, r->y, r->sc, ys, -r->ang, C_WHITE, 1);
        blend(s, 1);
        spr(s, v + 1, f, r->x, r->y, r->sc, ys, -r->ang, C_WHITE, 1);
        blend(s, 0);
    }
}

void gml_Object_o_scyther_Draw_0(CInstance *s, CInstance *o) {
    (void)o;
    Scy *j = slot(s, true);
    float x = sx_(s), y = sy_(s);
    float xs = (float)sget(s, &g_VAR_image_xscale);
    bool pok = parent_ok(s);
    bool charging = pok && pget(s, &g_VAR_is_charging) > 0.5;
    if (j->void_on && j->void_drawn != j->aura_t) draw_void(s, j);   /* Draw Begin didn't run: draw it here */

    /* behind the body: far halves of rings / trails / swings / scythe, debris behind, aura, afterimages */
    draw_3d(s, j, 0);
    draw_rifts(s, j, 1);
    draw_arcs(s, j, 0);
    if (charging || (j->move == MV_SPECIAL && j->t < SP_WIND)) {
        blend(s, 1);
        spr(s, SC_AURA, (float)(j->aura_t / 3), x, y, 1, 1, 0, C_WHITE, 0.85f);
        blend(s, 0);
    }
    draw_weapon(s, j, x, y, xs, 0);
    for (int i = 0; i < N_GHOST; i++) {
        Ghost *g = &j->ghosts[i];
        if (!g->on || g->spr < 0) continue;
        YYGML_draw_sprite_ext(s, g->spr, g->img, g->x, g->y, g->xs * 0.5f, 0.5f, 0, g->col, g->a0 * (1 - g->t / 14.0f));
    }
    /* the rooster himself (2x sprite at half scale), with a motion smear when he dashes */
    int sp = (int)sget(s, &g_VAR_sprite_index);
    if (sp >= 0) {
        int ours = body_anim(s) >= 0;
        float k = ours ? 0.5f : 1.0f;
        float img = (float)sget(s, &g_VAR_image_index);
        float al = j->alpha * (float)sget(s, &g_VAR_image_alpha);
        if (j->smear && ours) {                              /* streaks back along his velocity */
            float hs = (float)sget(s, &g_VAR_hspeed), vs = (float)sget(s, &g_VAR_vspeed);
            float sp_ = sqrtf_(hs * hs + vs * vs);
            float ux = sp_ > 0.5f ? hs / sp_ : j->dir, uy = sp_ > 0.5f ? vs / sp_ : 0;
            float step = 3.0f + sp_ * 0.9f;
            blend(s, 1);
            for (int n = 1; n <= 3; n++)
                YYGML_draw_sprite_ext(s, sp, img, x - ux * step * n, y - uy * step * n, xs * k * (1 + 0.05f * n * fabsf_(ux)),
                                      k * (1 + 0.05f * n * fabsf_(uy)), 0, C_GHOST, al * 0.3f / n);
            blend(s, 0);
        }
        if (j->blink < 5 && ours) {                          /* stepping out of a blink: stretched in */
            float st = 1 + (5 - j->blink) * 0.12f;
            blend(s, 1);
            YYGML_draw_sprite_ext(s, sp, img, x, y, xs * k * st, k / st, 0, C_VIOLET, 0.6f * (5 - j->blink) / 5.0f);
            blend(s, 0);
        }
        YYGML_draw_sprite_ext(s, sp, img, x, y, xs * k * j->sqx, k * j->sqy,
                              (float)sget(s, &g_VAR_image_angle), C_WHITE, al);
    }
    /* in front: trails, the scythe, swings, the near halves of the rings, debris in front */
    draw_3d(s, j, 1);
    draw_weapon(s, j, x, y, xs, 1);
    draw_arcs(s, j, 1);

    draw_rifts(s, j, 0);
    /* Event Horizon */
    if (j->bh_on) {
        float g = j->bh_t < 12 ? 0.25f + 0.75f * j->bh_t / 12.0f : 1.0f;
        if (j->bh_t > 70) g *= 1.0f - (j->bh_t - 70) / 12.0f;
        blend(s, 1);
        spr(s, SC_BH_PULL, (float)(j->bh_t / 3), j->bh_x, j->bh_y, g, g, 0, C_WHITE, 0.8f);
        spr(s, SC_BH_DISKB, (float)(j->bh_t / 2), j->bh_x, j->bh_y, g, g, 0, C_WHITE, 1);
        blend(s, 0);
        spr(s, SC_BH_CORE, (float)(j->bh_t / 3), j->bh_x, j->bh_y, g, g, 0, C_WHITE, 1);
        for (int i = 0; i < 6; i++) {                        /* debris spiralling in */
            float ph = (float)((j->bh_t * 3 + i * 40) % 90) / 90.0f;
            float ang = i * 1.05f + ph * 7.0f;
            float rr = 80 * (1 - ph) + 10;
            spr(s, SC_BH_DEBRIS, (float)((j->bh_t / 3 + i) % 8), j->bh_x + rr * cosf_(ang), j->bh_y + rr * 0.45f * sinf_(ang),
                1, 1, 0, C_WHITE, g);
        }
        blend(s, 1);
        spr(s, SC_BH_DISKF, (float)(j->bh_t / 2), j->bh_x, j->bh_y, g, g, 0, C_WHITE, 1);
        blend(s, 0);
    }
    /* Void Lance: iris charging in the aperture, the beam, its head */
    blend(s, 1);
    if (j->eye_on) {
        float k = j->eye_t < 16 ? j->eye_t / 16.0f : 1.0f;
        if (j->eye_t > 56) k *= 1 - (j->eye_t - 56) / 12.0f;
        spr(s, SC_VL_IRIS, (float)(j->eye_t / 2), j->eye_x, j->eye_y, 0.6f + 0.6f * k, 0.6f + 0.6f * k, 0, C_WHITE, k);
    }
    if (j->beam_on) {
        float fade = j->beam_t > 44 ? 1.0f - (j->beam_t - 44) / 12.0f : 1.0f;
        float wob = 1.0f + 0.12f * (float)((j->beam_t % 4) < 2 ? 1 : -1);
        spr(s, SC_VL_BEAM, (float)(j->beam_t / 2), j->beam_x, j->beam_y, j->beam_dir * j->beam_len / 32.0f, wob * fade, 0, C_WHITE, fade);
        spr(s, SC_VL_TIP, (float)(j->beam_t / 2), j->beam_x + j->beam_dir * j->beam_len, j->beam_y, j->beam_dir, 1, 0, C_WHITE, fade);
    }
    /* one-shot effects */
    for (int i = 0; i < N_FX; i++) {
        Fx *f = &j->fx[i];
        if (!f->on) continue;
        if (!f->add) blend(s, 0);
        spr(s, f->a, (float)(f->t / f->tpf), f->x, f->y, f->xs, f->ys, f->rot, C_WHITE, 1);
        if (!f->add) blend(s, 1);
    }
    if (j->fail_t > 0)                                       /* the special needs a full bar */
        spr(s, SC_VL_IRIS, (float)(j->aura_t / 2), x, y - 70, 0.7f, 0.7f, 0, C_RED, j->fail_t / 24.0f);
    blend(s, 0);
    /* the thrown scythe: a spinning disc of blades */
    if (j->th_on) {
        int idx = ((int)(j->th_ang / 18.0f)) % 20;
        spr(s, SC_DISC, (float)idx, j->th_x, j->th_y, 1, 1, 0, C_WHITE, 1);
        blend(s, 1);
        spr(s, SC_ARC_SPIN_F, (float)((j->th_t / 2) % 6), j->th_x, j->th_y, 1, 1, 0, C_WHITE, 0.8f);
        blend(s, 0);
    }
}

/* GUI layer: the SINGULARITY cutscene */
void gml_Object_o_scyther_Draw_64(CInstance *s, CInstance *o) {
    (void)o;
    Scy *j = slot(s, false);
    if (!j || j->move != MV_SPECIAL || j->t <= SP_WIND || j->t > SP_WIND + SP_CUT) return;
    int c = j->cut_t;
    float gw = (float)legacy0(s, &g_FUNC_display_get_gui_width);
    float gh = (float)legacy0(s, &g_FUNC_display_get_gui_height);
    if (gw < 16 || gh < 16) return;
    float sc = gw / SCY_CUT_W; if (gh / SCY_CUT_H > sc) sc = gh / SCY_CUT_H;     /* cover the screen */
    float w = SCY_CUT_W * sc, h = SCY_CUT_H * sc;
    float ox = (gw - w) * 0.5f, oy = (gh - h) * 0.5f;
    float sxo = 0, syo = 0;
    if (j->shake > 0.3f) { sxo = frand(-j->shake, j->shake) * sc * 0.3f; syo = frand(-j->shake, j->shake) * sc * 0.3f; }
    int f = c / 5; if (f > 35) f = 35;
    int a = f < 12 ? SC_CUT_A : f < 24 ? SC_CUT_B : SC_CUT_C;
    YYGML_draw_set_alpha(1);
    YYGML_draw_set_colour(0);
    YYGML_draw_rectangle(0, 0, gw, gh, false);
    spr(s, a, (float)(f % 12), ox + sxo, oy + syo, sc, sc, 0, C_WHITE, 1);
    /* act 3: the rooster on his rock, drawn live from his 2x sprites so he stays crisp */
    float fh = c / 5.0f - 28;
    if (fh > 0) {
        float al = fh / 3 > 1 ? 1 : fh / 3;
        float hk = SCY_CUT_HERO_K * sc;
        float hx = ox + sxo + SCY_CUT_HERO_X * sc, hy = oy + syo + SCY_CUT_HERO_Y * sc;
        const ScyFrame *m = &k_scy_meta[k_scy_meta_first[SC_SP] + 5];
        float gx = hx + m->gx / 2.0f * hk, gy = hy + m->gy / 2.0f * hk;
        int idx = ((int)(m->ang / 11.25f + 0.5f)) % 32;
        int wa = idx < 16 ? SC_WPN0 : SC_WPN1;
        blend(s, 1);
        spr(s, SC_AURA, (float)((c / 3) % 8), hx, hy, hk, hk, 0, C_WHITE, 0.55f * al);
        blend(s, 0);
        if (m->fl & 1) spr(s, wa, (float)(idx % 16), gx, gy, hk, hk, 0, C_WHITE, al);
        spr(s, SC_SP, 5, hx, hy, hk, hk, 0, C_WHITE, al);
        if (!(m->fl & 1)) spr(s, wa, (float)(idx % 16), gx, gy, hk, hk, 0, C_WHITE, al);
    }
    /* fade in from the arena and out to it */
    float in = c < 8 ? 1 - c / 8.0f : (c > SP_CUT - 8 ? (c - (SP_CUT - 8)) / 8.0f : 0);
    if (in > 0) {
        YYGML_draw_set_colour(0);
        YYGML_draw_set_alpha(in);
        YYGML_draw_rectangle(0, 0, gw, gh, false);
    }
    YYGML_draw_set_colour(C_WHITE);
    YYGML_draw_set_alpha(1);
}

/* the portrait card's index in g_scy_spr (hooks.c doesn't see our sprite enum) */
int scyther_face_index(void) { return SC_FACE; }
