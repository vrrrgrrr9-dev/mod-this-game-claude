/*
 * Black Holing Scyther - a cosmic gamecock with a double-bladed obsidian scythe.
 *
 *  combo A (attack A): Rift Cleave -> Twin Crescent -> Orbit Reap -> Event Horizon Cleave
 *  combo B (attack B): Crescent Throw -> Spur Vault -> Dimensional Stitch -> Singular Rend
 *  down + attack:      Ground Reaper            air attack: Falling Star
 *  defend:             crouches behind the scythe held upright
 *  skill 1:            Event Horizon - opens a black hole that drags the opponent in, then collapses
 *  skill 2 (down):     Void Lance - cuts an aperture in reality that fires a beam, ends in a nova
 *  special (shield + skill, full bar): SINGULARITY - X-cut on the opponent, cutscene (black hole,
 *                      the multiverse shatters), a huge unblockable hit (no instant K.O.), and the
 *                      stage is left as a void of floating rocks for the rest of the match
 *
 * Every cut tears a hole in reality (rift sprites).  Swings draw 3D arcs split into a back half
 * (behind the body) and a front half; the scythe is its own sprite drawn at the wing-hand grip
 * (per-frame grip/angle table from the art build) so it can twirl in a tilted 3D orbit, be thrown
 * and spin.  Body and scythe are drawn from 2x-density sprites at half scale (the game renders
 * its 600x300 view to a 1200x600 surface, so the extra detail reaches the screen).
 *
 * Built on the game's own character framework like the original roster: scr_plr_step drives
 * movement/inputs, alarm[3]/alarm[2] run the combo chain, hits are o_mask_hit hitboxes.
 */
#include "yyc.h"
#include "scyther_assets.h"

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

enum { MV_NONE, MV_COMBO, MV_SKILL1, MV_SKILL2, MV_SPECIAL };
enum { W_META, W_SPIN, W_ORBIT, W_HIDDEN };            /* how the scythe is drawn */

#define N_RIFT 14
#define N_ARC 8
#define N_GHOST 8
#define N_FX 12

#define SP_WIND 40            /* in-world X-cut before the cutscene */
#define SP_CUT  180           /* cutscene length */
#define SP_AFTER 40

typedef struct { int on, t, big, life; float x, y, ang, sc; } Rift;
typedef struct { int on, t, a; float x, y, xs; } ArcFx;
typedef struct { int on, t, spr; float img, x, y, xs; } Ghost;
typedef struct { int on, t, a, tpf, n, add; float x, y, xs, ys, rot; } Fx;

typedef struct {
    CInstance *inst;
    int move, step, t, dur;
    float dir;
    int anim; float frame;
    /* scythe */
    int wmode; float wang, wvel, wdraw; int wdraw_ok;
    float alpha;
    /* thrown scythe (Crescent Throw) */
    int th_on, th_t, th_hits; float th_x, th_y, th_vx, th_ang;
    Rift rifts[N_RIFT]; ArcFx arcs[N_ARC]; Ghost ghosts[N_GHOST]; Fx fx[N_FX];
    int ghosting;
    /* skill 1: black hole */
    int bh_on, bh_t; float bh_x, bh_y;
    /* skill 2: void lance */
    int eye_on, eye_t; float eye_x, eye_y;
    int beam_on, beam_t; float beam_x, beam_y, beam_len, beam_dir;
    /* special */
    int tgt_id; float tgt_x, tgt_y; int cut_t, hit_done, depth_saved; double old_depth; float shake;
    /* the void stage after SINGULARITY */
    int void_on, void_t, void_hidden; float ground_y;
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
static float sinf_(float x) {                     /* small, freestanding sine (radians) */
    while (x > 3.14159265f) x -= 6.2831853f;
    while (x < -3.14159265f) x += 6.2831853f;
    float x2 = x * x;
    return x * (1 - x2 / 6 * (1 - x2 / 20 * (1 - x2 / 42 * (1 - x2 / 72))));
}

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
    j->inst = s; j->dir = 1; j->tgt_id = -1; j->anim = -1; j->alpha = 1;
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

/* a melee hit in front of (dx > 0) or behind (dx < 0) the rooster */
static void melee(CInstance *s, Scy *j, float dx, float dy, int mask, float xs, float ys, double k, double hf, double vf,
                  double stun, int knock, int spr_hit) {
    Hit h = { my_dmg(s) * k, j->dir * hf * (dx < 0 ? -1 : 1), vf, stun, 5, xs, ys, mask, 1, knock, 1, knock, spr_hit, C_VIOLET, 1 };
    spawn_hit(s, sx_(s) + j->dir * dx, sy_(s) + dy, &h);
}

/* ------------------------------------------------------------------------------------------ */
/* effects: reality tears, 3D arcs, afterimages, one-shots                                     */
/* ------------------------------------------------------------------------------------------ */
static void rift_at(Scy *j, float x, float y, float ang, float sc, int big, int life) {
    int best = 0;
    for (int i = 0; i < N_RIFT; i++) { if (!j->rifts[i].on) { best = i; break; } if (j->rifts[i].t > j->rifts[best].t) best = i; }
    Rift *r = &j->rifts[best];
    r->on = 1; r->t = 0; r->big = big; r->life = life;
    r->x = x; r->y = y; r->sc = sc;
    r->ang = j->dir > 0 ? ang : -ang;                   /* mirror for the facing */
}
static void rift(CInstance *s, Scy *j, float dx, float dy, float ang, float sc, int big) {
    rift_at(j, sx_(s) + j->dir * dx, sy_(s) + dy, ang, sc, big, big ? 96 : 48);
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
static void ghost(CInstance *s, Scy *j) {
    int best = 0;
    for (int i = 0; i < N_GHOST; i++) { if (!j->ghosts[i].on) { best = i; break; } if (j->ghosts[i].t > j->ghosts[best].t) best = i; }
    Ghost *g = &j->ghosts[best];
    g->on = 1; g->t = 0; g->spr = (int)sget(s, &g_VAR_sprite_index); g->img = (float)sget(s, &g_VAR_image_index);
    g->x = sx_(s); g->y = sy_(s); g->xs = (float)sget(s, &g_VAR_image_xscale);
}
static void effects_step(CInstance *s, Scy *j) {
    for (int i = 0; i < N_RIFT; i++) if (j->rifts[i].on && ++j->rifts[i].t >= j->rifts[i].life) j->rifts[i].on = 0;
    for (int i = 0; i < N_ARC; i++) if (j->arcs[i].on && ++j->arcs[i].t >= 18) j->arcs[i].on = 0;
    for (int i = 0; i < N_GHOST; i++) if (j->ghosts[i].on && ++j->ghosts[i].t >= 14) j->ghosts[i].on = 0;
    for (int i = 0; i < N_FX; i++) if (j->fx[i].on && ++j->fx[i].t >= j->fx[i].n * j->fx[i].tpf) j->fx[i].on = 0;
    if (j->ghosting && (j->aura_t % 2) == 0) ghost(s, j);
}
static float rift_frame(const Rift *r) {
    if (r->t < 12) return r->t / 3.0f;                          /* opening */
    if (r->t < r->life - 12) return 4 + (float)((r->t / 4) % 8);  /* shimmering hold */
    return 12 + (r->t - (r->life - 12)) / 3.0f;                 /* sealing */
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
    iset(s, &g_VAR_stats_walkspd, 3.3);
    iset(s, &g_VAR_stats_airdashspd, 8.6);
    iset(s, &g_VAR_stats_runspd, 7.6);
    iset(s, &g_VAR_stats_jumpforce, -6.9);
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

static void start_skill1(CInstance *s, Scy *j);
static void start_skill2(CInstance *s, Scy *j);

static const int DUR[] = { 0, 26, 34, 40, 70 };          /* A1..A4 */
static const int DURB[] = { 56, 48, 44, 66 };            /* B1..B4 */

static void scy_start(CInstance *s, CInstance *o, int step) {
    Scy *j = slot(s, true);
    (void)o;
    iset_b(s, &g_VAR_combo_nextcombo, false);
    if (step == 100) { start_skill1(s, j); return; }
    if (step == 110) { start_skill2(s, j); return; }
    j->move = MV_COMBO; j->step = step; j->t = 0; j->dir = facing(s);
    j->wmode = W_META; j->ghosting = 0; j->alpha = 1;
    int next = -1, dur = 26;
    switch (step) {
    case 1: case 2: case 3: next = step + 1; dur = DUR[step]; break;
    case 4: next = -1; dur = DUR[4]; break;
    case 50: case 51: case 52: next = step + 1; dur = DURB[step - 50]; break;
    case 53: next = -1; dur = DURB[3]; break;
    case 10: case 60: dur = 26; break;
    case 11: case 61: dur = 24; break;
    default: j->move = MV_NONE; iset(s, &g_VAR_combo_next, -1); bset_i(s, &g_VAR_alarm, 2, 1); return;
    }
    j->dur = dur;
    iset(s, &g_VAR_combo_next, next);
    bset_i(s, &g_VAR_alarm, 2, dur);
}

/* combo A ------------------------------------------------------------------------------------ */
static void step_a1(CInstance *s, Scy *j, int t) {           /* Rift Cleave */
    static const int K[] = { 0, 6, 11, 17, 22 };
    show(s, j, SC_A1, (float)kf(t, K, 5));
    if (t >= 6 && t <= 9) dash(s, j, 2.0f); else stop(s);
    if (t == 6) {
        melee(s, j, 26, -34, SPR_MASK32, 1.3f, 1.6f, 0.95, 3, -2, 16, 0, SPR_HIT_3);
        arc(s, j, SC_ARC_RISE_B, 8, -24);
        play_c(s, SCS_SLASH, 1.0);
    }
    if (t == 8) { rift(s, j, 36, -44, -55, 1.0f, 0); play_c(s, SCS_RIP, 1.05); }
}
static void step_a2(CInstance *s, Scy *j, int t) {           /* Twin Crescent: 3D twirl, two hits, X tear */
    static const int K[] = { 0, 5, 9, 21 };
    int f = kf(t, K, 4);
    if (f == 1 || f == 2) f = 1 + ((t / 4) % 2);
    show(s, j, SC_A2, (float)f);
    if (t >= 5 && t < 21) { j->wmode = W_ORBIT; j->wang += 30; dash(s, j, 1.5f); }
    else { j->wmode = W_META; stop(s); }
    if (t == 5) { arc(s, j, SC_ARC_TWIRL_B, 20, -35); play_c(s, SCS_SPIN, 1.0); }
    if (t == 8 || t == 16) {
        melee(s, j, 26, -36, SPR_MASK32, 1.4f, 1.5f, 0.6, 3, -2, 14, 0, SPR_HIT_1);
        play_c(s, SCS_SLASH, t == 8 ? 1.1 : 1.2);
    }
    if (t == 21) {
        rift(s, j, 40, -40, 45, 0.9f, 0); rift(s, j, 40, -40, -45, 0.9f, 0);
        arc(s, j, SC_ARC_XCUT_B, 40, -40);
        play_c(s, SCS_RIP, 0.95);
    }
}
static void step_a3(CInstance *s, Scy *j, int t) {           /* Orbit Reap: full spin, hits front and behind */
    static const int K[] = { 0, 5, 10, 14, 19, 23, 28, 34 };
    show(s, j, SC_A3, (float)kf(t, K, 8));
    j->ghosting = (t >= 5 && t < 30);
    if (t >= 23 && t < 34) dash(s, j, 2.2f); else stop(s);
    if (t == 5) { arc(s, j, SC_ARC_ORBIT_B, -4, -36); play_c(s, SCS_SPIN, 0.9); }
    if (t == 6) { melee(s, j, 30, -34, SPR_MASK32, 1.4f, 1.5f, 0.45, 3, -2, 14, 0, SPR_HIT_1); rift(s, j, 36, -36, -10, 0.8f, 0); play_c(s, SCS_SLASH, 1.0); }
    if (t == 15) { melee(s, j, -28, -34, SPR_MASK32, 1.4f, 1.5f, 0.45, 3, -2, 14, 0, SPR_HIT_1); rift(s, j, -34, -34, 10, 0.8f, 0); play_c(s, SCS_SLASH, 1.1); }
    if (t == 24) { melee(s, j, 32, -30, SPR_MASK32, 1.5f, 1.5f, 0.55, 4, -3, 16, 0, SPR_HIT_3); rift(s, j, 40, -30, 20, 0.9f, 0); play_c(s, SCS_SLASH, 1.2); play_c(s, SCS_RIP, 1.1); }
}
static void step_a4(CInstance *s, Scy *j, int t) {           /* Event Horizon Cleave: leap, flip, slam, giant tear */
    static const int K[] = { 0, 8, 14, 18, 22, 26, 30, 45 };
    show(s, j, SC_A4, (float)kf(t, K, 8));
    if (t == 8) { bset(s, &g_VAR_vspeed, -7.5); dash(s, j, 2.5f); play(s, SND_WOOSH3, 0.9); }
    if (t > 8 && t < 26) dash(s, j, 2.5f);
    if (t == 26) { bset(s, &g_VAR_vspeed, 9); stop(s); arc(s, j, SC_ARC_CLEAVE_B, 18, -60); play_c(s, SCS_SLASH, 0.8); }
    j->ghosting = (t >= 8 && t < 30);
    if (t == 30) {
        stop(s);
        rift(s, j, 30, -48, 90, 0.85f, 1);
        melee(s, j, 30, -40, SPR_MASK64, 1.2f, 1.6f, 1.0, 2, -2, 24, 0, SPR_HIT_3);
        camera_shake(3);
        play_c(s, SCS_RIP, 0.8); play(s, SND_STRONG2, 0.9);
    }
    if (t == 58) {                                            /* the tear snaps shut: knockdown */
        float x = sx_(s) + j->dir * 30, y = sy_(s) - 40;
        Hit h = { my_dmg(s) * 1.25, j->dir * 8.0, -8.0, 30, 6, 1.6, 1.6, SPR_MASK64, 1, 1, 1, 1, SPR_HIT_3, C_VIOLET, 2 };
        spawn_hit(s, x, y, &h);
        fx_at(j, SC_BH_BURST, x, y, 0.55f, 0.55f, 0, 2, 1);
        camera_shake(4);
        play_c(s, SCS_COLLAPSE, 1.2);
    }
}
/* combo B ------------------------------------------------------------------------------------ */
static void step_b1(CInstance *s, Scy *j, int t) {           /* Crescent Throw: buzzsaw boomerang */
    int f = t < 8 ? 0 : 1;
    if (j->th_on && t >= 9) f = t < 24 ? 2 : 3;
    if (!j->th_on && t > 8) f = (t < j->dur - 8) ? 4 : 5;
    show(s, j, SC_B1, (float)f);
    stop(s);
    j->wmode = (j->th_on ? W_HIDDEN : W_META);
    if (t == 8) {
        const ScyFrame *m = frame_meta(s);
        j->th_on = 1; j->th_t = 0; j->th_hits = 0;
        j->th_x = sx_(s) + j->dir * (m ? m->gx / 2.0f : 20); j->th_y = sy_(s) + (m ? m->gy / 2.0f : -36);
        j->th_vx = j->dir * 7.5f; j->th_ang = 0;
        play_c(s, SCS_SPIN, 1.0); play(s, SND_WOOSH2, 0.9);
    }
    if (j->th_on && t > 8) j->dur = t + 16;                   /* hold the pose until it comes back */
}
static void thrown_step(CInstance *s, Scy *j) {
    if (!j->th_on) return;
    j->th_t++;
    j->th_ang = wrap360(j->th_ang + 34);
    j->th_x += j->th_vx;
    j->th_vx -= j->dir * 0.24f;
    float hx = sx_(s) + j->dir * 18, hy = sy_(s) - 36;
    j->th_y += (hy - j->th_y) * 0.05f;
    if (j->th_t % 7 == 3 && j->th_hits < 4 && parent_ok(s)) {
        Hit h = { my_dmg(s) * 0.38, j->th_vx > 0 ? 2.0 : -2.0, -1.0, 12, 4, 1.4, 1.0, SPR_MASK32, 1, 0, 1, 0, SPR_HIT_1, C_VIOLET, 1 };
        spawn_hit(s, j->th_x, j->th_y, &h);
        j->th_hits++;
    }
    if (j->th_t % 10 == 5) rift_at(j, j->th_x, j->th_y, 0, 0.5f, 0, 40);
    float d = j->th_x - hx;
    if ((j->th_t > 20 && fabsf_(d) < 14) || j->th_t > 80) {   /* caught */
        j->th_on = 0;
        play(s, SND_STRONG1, 1.3);
    }
}
static void step_b2(CInstance *s, Scy *j, int t) {           /* Spur Vault: plant, vault, double spur kick, rip */
    static const int K[] = { 0, 7, 12, 18, 26, 36 };
    show(s, j, SC_B2, (float)kf(t, K, 6));
    if (t == 2) play(s, SND_STRONG1, 0.8);
    if (t == 7) { bset(s, &g_VAR_vspeed, -5); dash(s, j, 1.5f); }
    if (t > 7 && t < 26) dash(s, j, 1.2f); else if (t >= 26) stop(s);
    if (t == 12) { melee(s, j, 22, -26, SPR_MASK24, 1.2f, 1.2f, 0.5, 3, -2, 14, 0, SPR_HIT_1); play(s, SND_WOOSH1, 1.2); fx_at(j, SC_HITFX, sx_(s) + j->dir * 22, sy_(s) - 26, 1, 1, 0, 2, 1); }
    if (t == 18) { melee(s, j, 22, -22, SPR_MASK24, 1.2f, 1.2f, 0.5, 3, -2, 14, 0, SPR_HIT_1); play(s, SND_WOOSH2, 1.2); fx_at(j, SC_HITFX, sx_(s) + j->dir * 22, sy_(s) - 22, 1, 1, 0, 2, 1); }
    if (t == 26) {
        melee(s, j, 26, -40, SPR_MASK32, 1.2f, 1.8f, 0.75, 2, -6, 20, 0, SPR_HIT_3);
        arc(s, j, SC_ARC_RISE_B, 10, -26);
        rift(s, j, 30, -36, -70, 1.0f, 0);
        play_c(s, SCS_SLASH, 1.0); play_c(s, SCS_RIP, 1.0);
    }
}
static void step_b3(CInstance *s, Scy *j, int t) {           /* Dimensional Stitch: six fast cuts */
    int f = t < 36 ? (t / 6) % 5 : 5;
    show(s, j, SC_B3, (float)f);
    stop(s);
    if (t < 36 && t % 6 == 3) {
        int i = t / 6;
        melee(s, j, 26, -34 + (i % 2 ? 6 : -6), SPR_MASK24, 1.3f, 1.2f, 0.24, 2, -1, 10, 0, SPR_HIT_1);
        arc(s, j, i % 2 ? SC_ARC_STITCHB_B : SC_ARC_STITCHA_B, 18, -36);
        rift(s, j, 30 + 4 * i, -46 + (i % 2) * 16, i % 2 ? 50 : -50, 0.55f, 0);
        play_c(s, SCS_SLASH, 1.0 + 0.06 * i);
    }
    if (t == 33) play_c(s, SCS_RIP, 1.2);
}
static CInstance *nearest_enemy(CInstance *s, int *out_id, float maxdx, float maxdy);
static float room_w(CInstance *s) { return (float)sget(s, &g_VAR_room_width); }
static bool free_at(CInstance *s, float x, float y) {
    RValue r = rv_undef();
    RValue a[3] = { rv_real(x), rv_real(y), rv_real(OBJ_PARENT_SOLID) };
    F_PlaceMeeting(&r, s, s, 3, a);
    bool hit = rv_num(&r) > 0.5;
    rv_free(&r);
    float rw = room_w(s);
    if (rw > 100 && (x < 16 || x > rw - 16)) return false;
    return !hit;
}
static void step_b4(CInstance *s, Scy *j, int t) {           /* Singular Rend: through a portal, cut from behind */
    static const int K[] = { 0, 8, 14, 22, 30, 38, 49 };
    show(s, j, SC_B4, (float)kf(t, K, 7));
    if (t == 10) { rift(s, j, 30, -44, 90, 0.7f, 1); play_c(s, SCS_RIP, 0.9); }
    if (t >= 14 && t < 22) { dash(s, j, 2.0f); j->alpha = 1 - (t - 14) / 8.0f; j->ghosting = 1; }
    else stop(s);
    if (t == 22) {
        int tid = -1;
        CInstance *e = nearest_enemy(s, &tid, 260, 140);
        float nx = sx_(s) + j->dir * 90;
        if (e) nx = (float)sget(e, &g_VAR_x) + j->dir * 34;
        if (free_at(s, nx, sy_(s))) {
            bset(s, &g_VAR_x, nx);
            j->dir = -j->dir;
            bset(s, &g_VAR_image_xscale, j->dir);
        }
        rift(s, j, -6, -44, 90, 0.7f, 1);
        play(s, SND_MAGIC3, 1.2);
    }
    if (t >= 22 && t < 30) { j->alpha = (t - 22) / 8.0f; }
    if (t >= 30) { j->alpha = 1; j->ghosting = 0; }
    if (t == 38) {
        Hit h = { my_dmg(s) * 1.3, j->dir * 7.0, -7.0, 30, 6, 1.3, 1.3, SPR_MASK64, 1, 1, 1, 1, SPR_HIT_3, C_VIOLET, 2 };
        spawn_hit(s, sx_(s) + j->dir * 28, sy_(s) - 32, &h);
        arc(s, j, SC_ARC_SWEEP_B, 16, -32);
        rift(s, j, 36, -32, 0, 1.0f, 0);
        camera_shake(3);
        play_c(s, SCS_SLASH, 0.9); play(s, SND_STRONG2, 1.0);
    }
}
/* crouch / air --------------------------------------------------------------------------------- */
static void step_crouch(CInstance *s, Scy *j, int t) {       /* Ground Reaper: low sweep that trips */
    show(s, j, SC_CROUCHATK, t < 6 ? 0 : t < 12 ? 1 : 2);
    stop(s);
    if (t == 6) {
        Hit h = { my_dmg(s) * 0.9, j->dir * 4.0, -4.0, 20, 5, 1.6, 0.8, SPR_MASK24, 1, 1, 1, 1, SPR_HIT_1, C_VIOLET, 1 };
        spawn_hit(s, sx_(s) + j->dir * 28, sy_(s) - 10, &h);
        arc(s, j, SC_ARC_SWEEP_B, 12, -14);
        rift(s, j, 34, -6, 0, 0.8f, 0);
        play_c(s, SCS_SLASH, 1.1);
    }
}
static void step_air(CInstance *s, Scy *j, int t) {          /* Falling Star: twirl like a buzzsaw */
    show(s, j, SC_AIRATK, t < 15 ? (float)((t / 4) % 2) : 2);
    if (t < 15) { j->wmode = W_ORBIT; j->wang += 34; } else j->wmode = W_META;
    if (t == 2) { arc(s, j, SC_ARC_SPIN_B, 20, -34); play_c(s, SCS_SPIN, 1.2); }
    if (t == 4 || t == 12) melee(s, j, 20, -30, SPR_MASK32, 1.4f, 1.4f, 0.5, 2, 3, 14, 0, SPR_HIT_1);
}

static void combo_step(CInstance *s, Scy *j) {
    j->t++;
    int t = j->t;
    switch (j->step) {
    case 1: step_a1(s, j, t); break;
    case 2: step_a2(s, j, t); break;
    case 3: step_a3(s, j, t); break;
    case 4: step_a4(s, j, t); break;
    case 50: step_b1(s, j, t); break;
    case 51: step_b2(s, j, t); break;
    case 52: step_b3(s, j, t); break;
    case 53: step_b4(s, j, t); break;
    case 10: case 60: step_crouch(s, j, t); break;
    case 11: case 61: step_air(s, j, t); break;
    }
    if (t >= j->dur) {
        j->move = MV_NONE; j->anim = -1; j->wmode = W_META; j->ghosting = 0; j->alpha = 1;
        bset(s, &g_VAR_image_speed, 0.25);
    }
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
    j->move = MV_SKILL1; j->t = 0; j->dir = facing(s); j->dur = 50; j->wmode = W_META;
    iset(s, &g_VAR_combo_next, -1);
    bset_i(s, &g_VAR_alarm, 2, 50);
    show(s, j, SC_CAST1, 0);
    stop(s);
    play(s, SND_MAGICSTUN_CAST, 0.9);
}
static void skill1_step(CInstance *s, Scy *j) {
    int t = ++j->t;
    int f = t < 10 ? 0 : t < 26 ? 1 + ((t / 4) % 2) : t < 32 ? 3 : 4;
    show(s, j, SC_CAST1, (float)f);
    stop(s);
    j->wmode = (t >= 10 && t < 26) ? W_ORBIT : W_META;
    if (j->wmode == W_ORBIT) j->wang += 28;
    if (t == 26) {
        j->bh_on = 1; j->bh_t = 0;
        j->bh_x = sx_(s) + j->dir * 96; j->bh_y = sy_(s) - 40;
        play_c(s, SCS_BH, 1.0); play(s, SND_MAGIC3, 0.7);
        camera_shake(2);
    }
    if (t >= j->dur) { j->move = MV_NONE; j->anim = -1; j->wmode = W_META; bset(s, &g_VAR_image_speed, 0.25); }
}
/* drag every opponent near the hole toward it */
static void pull_enemies(CInstance *s, Scy *j) {
    RValue me = rv_undef();
    YYGML_Variable_GetValue(parent_of(s), g_VAR_plr_team.id, ARRAY_INDEX_NONE, &me, false, false);
    double my_team = rv_num(&me); rv_free(&me);
    RValue n = rv_undef(); RValue a = rv_real(OBJ_PARENT_CHARACTER);
    F_InstanceNumber(&n, s, s, 1, &a);
    int cnt = (int)rv_num(&n); rv_free(&n);
    for (int i = 0; i < cnt; i++) {
        RValue id = rv_undef(); RValue fa[2] = { rv_real(OBJ_PARENT_CHARACTER), rv_real(i) };
        F_InstanceFind(&id, s, s, 2, fa);
        CInstance *c = YYGML_FindInstance(INT32_RValue(&id));
        if (!c || c == s) { rv_free(&id); continue; }
        RValue cp = rv_undef();
        YYGML_Variable_GetValue(&id, g_VAR_parent.id, ARRAY_INDEX_NONE, &cp, false, false);
        bool ok = inst_exists_rv(s, &cp);
        double team = ok ? get_rv(&cp, &g_VAR_plr_team, ARRAY_INDEX_NONE) : my_team;
        rv_free(&cp); rv_free(&id);
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
        play_c(s, SCS_COLLAPSE, 1.0);
        camera_shake(4);
        j->bh_on = 0;
    }
}

/* ------------------------------------------------------------------------------------------ */
/* skill 2 - Void Lance                                                                        */
/* ------------------------------------------------------------------------------------------ */
static void start_skill2(CInstance *s, Scy *j) {
    j->move = MV_SKILL2; j->t = 0; j->dir = facing(s); j->dur = 70; j->wmode = W_META;
    iset(s, &g_VAR_combo_next, -1);
    bset_i(s, &g_VAR_alarm, 2, 70);
    show(s, j, SC_CAST2, 0);
    stop(s);
    play(s, SND_BALL_CHARGE, 0.85);
}
static void skill2_step(CInstance *s, Scy *j) {
    int t = ++j->t;
    int f = t < 8 ? 0 : t < 14 ? 1 : t < 30 ? 2 : t < 51 ? 3 : 4;
    show(s, j, SC_CAST2, (float)f);
    stop(s);
    if (t == 10) {
        j->eye_on = 1; j->eye_t = 0;
        j->eye_x = sx_(s) + j->dir * 40; j->eye_y = sy_(s) - 38;
        rift_at(j, j->eye_x, j->eye_y, 90, 0.42f, 1, 70);
        play_c(s, SCS_RIP, 0.85);
    }
    if (t == 30) {
        j->beam_on = 1; j->beam_t = 0; j->beam_len = 0; j->beam_dir = j->dir;
        j->beam_x = j->eye_x; j->beam_y = j->eye_y;
        play_c(s, SCS_BEAM, 1.0);
        camera_shake(2);
    }
    if (t >= j->dur) { j->move = MV_NONE; j->anim = -1; bset(s, &g_VAR_image_speed, 0.25); }
}
static void lance_step(CInstance *s, Scy *j) {
    if (j->eye_on && ++j->eye_t > 72) j->eye_on = 0;
    if (!j->beam_on) return;
    int t = ++j->beam_t;
    j->beam_len += (360.0f - j->beam_len) * 0.3f;
    if (t % 4 == 0 && t <= 40 && parent_ok(s)) {
        Hit h = { my_dmg(s) * 0.2, j->beam_dir * 1.5, -0.5, 10, 3, j->beam_len / 64.0, 0.45, SPR_MASK64, 1, 0, 1, 0, SPR_HIT_5, C_VIOLET, 1 };
        spawn_hit(s, j->beam_x + j->beam_dir * j->beam_len * 0.5f, j->beam_y, &h);
    }
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
    RValue me = rv_undef();
    YYGML_Variable_GetValue(parent_of(s), g_VAR_plr_team.id, ARRAY_INDEX_NONE, &me, false, false);
    double my_team = rv_num(&me); rv_free(&me);
    double mx = sget(s, &g_VAR_x), my = sget(s, &g_VAR_y);
    RValue n = rv_undef(); RValue a = rv_real(OBJ_PARENT_CHARACTER);
    F_InstanceNumber(&n, s, s, 1, &a);
    int cnt = (int)rv_num(&n); rv_free(&n);
    CInstance *best = 0; double bestd = 1e9; int best_id = -1;
    for (int i = 0; i < cnt; i++) {
        RValue id = rv_undef(); RValue fa[2] = { rv_real(OBJ_PARENT_CHARACTER), rv_real(i) };
        F_InstanceFind(&id, s, s, 2, fa);
        CInstance *c = YYGML_FindInstance(INT32_RValue(&id));
        if (!c || c == s) { rv_free(&id); continue; }
        RValue cp = rv_undef();
        YYGML_Variable_GetValue(&id, g_VAR_parent.id, ARRAY_INDEX_NONE, &cp, false, false);
        if (!inst_exists_rv(s, &cp)) { rv_free(&cp); rv_free(&id); continue; }
        double team = get_rv(&cp, &g_VAR_plr_team, ARRAY_INDEX_NONE);
        double dead = get_rv(&cp, &g_VAR_is_dead, ARRAY_INDEX_NONE);
        rv_free(&cp);
        if (team == my_team || dead > 0.5) { rv_free(&id); continue; }
        double dx = sget(c, &g_VAR_x) - mx, dy = sget(c, &g_VAR_y) - my;
        double adx = dx < 0 ? -dx : dx, ady = dy < 0 ? -dy : dy;
        double d = adx + ady * 1.5;
        if (d < bestd && adx < maxdx && ady < maxdy) { bestd = d; best = c; best_id = INT32_RValue(&id); }
        rv_free(&id);
    }
    *out_id = best_id;
    return best;
}

static bool special_pressed(CInstance *s) {
    if (!parent_ok(s)) return false;
    if (pget(s, &g_VAR_keyp_special) < 0.5 || pget(s, &g_VAR_key_defend) < 0.5) return false;
    if (pget(s, &g_VAR_is_hurt) > 0.5 || pget(s, &g_VAR_is_fallen) > 0.5 || pget(s, &g_VAR_is_dead) > 0.5) return false;
    if (pget(s, &g_VAR_is_onair) > 0.5) return false;
    return true;
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
        if (t == 26) { rift_at(j, tx, ty, -45, 1.2f, 0, 54); play_c(s, SCS_RIP, 0.7); camera_shake(3); }
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
            Hit h = { my_dmg(s) * 12.0, j->dir * 10.0, -9.0, 40, 6, 2.0, 2.0, SPR_MASK64, 1, 1, 0, 1, SPR_HIT_3, C_VIOLET, 2 };
            spawn_hit(s, sget(c, &g_VAR_x), sget(c, &g_VAR_y) - 28, &h);
            fx_at(j, SC_IMPACT, (float)sget(c, &g_VAR_x), (float)sget(c, &g_VAR_y) - 30, j->dir, 1, 0, 3, 1);
            fx_at(j, SC_BH_BURST, (float)sget(c, &g_VAR_x), (float)sget(c, &g_VAR_y) - 30, 0.8f, 0.8f, 0, 2, 1);
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
/* the void stage: hide the stage's own non-instance layers, draw space + floating rocks       */
/* ------------------------------------------------------------------------------------------ */
static double arr_len(CInstance *s, RValue *arr) {
    RValue r = rv_undef();
    RValue *args[1] = { arr };
    YYGML_CallLegacyFunction(s, s, &r, 1, g_FUNC_array_length_1d.id, args);
    double d = rv_num(&r);
    rv_free(&r);
    return d;
}
static void void_activate(CInstance *s, Scy *j) {
    if (j->void_on) return;
    j->void_on = 1; j->void_t = 0;
    if (j->void_hidden) return;
    j->void_hidden = 1;
    /* layers = layer_get_all(); hide every layer that holds no instances (backgrounds, tiles, assets) */
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

static const short ROCK_X[10] = { 40, 150, 260, 380, 470, 560, 90, 330, 520, 230 };
static const short ROCK_Y[10] = { 22, 12, 30, 16, 26, 10, 48, 44, 52, 38 };     /* % of view height */
static const unsigned char ROCK_S[10] = { 60, 45, 70, 50, 65, 40, 90, 100, 80, 120 };   /* scale % */

/* Draw Begin: runs before the room's layers render, i.e. behind everything */
void gml_Object_o_scyther_Draw_72(CInstance *s, CInstance *o) {
    (void)o;
    Scy *j = slot(s, false);
    if (!j || !j->void_on) return;
    j->void_t++;
    RValue zero = rv_real(0);
    double cam = fcall1(s, F_ViewGetCamera, zero);
    RValue camv = rv_real(cam);
    float vx = (float)fcall1(s, F_CameraGetViewX, camv), vy = (float)fcall1(s, F_CameraGetViewY, camv);
    float vw = (float)fcall1(s, F_CameraGetViewWidth, camv), vh = (float)fcall1(s, F_CameraGetViewHeight, camv);
    if (vw < 16 || vh < 16) return;
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
        spr(s, SC_VOID_ROCKS, (float)(i % 8), vx + rx, vy + ROCK_Y[i] * vh / 100.0f + bob, sc, sc, 0, C_WHITE, fade);
    }
    /* drifting pebbles */
    for (int i = 0; i < 12; i++) {
        float px = (float)((i * 97 + j->void_t / 2) % (int)(vw + 20)) - 10;
        float py = (float)((i * 53) % (int)vh) + sinf_(j->void_t * 0.03f + i) * 6;
        spr(s, SC_VOID_DUST, (float)(i % 8), vx + px, vy + py, 1, 1, 0, C_WHITE, fade * 0.8f);
    }
    /* the floating stone floor the fighters stand on */
    if (j->ground_y > 0) {
        float x0 = vx - 256;
        int k = (int)(x0 / 256); if (x0 < 0) k--;
        for (float x = k * 256.0f; x < vx + vw + 256; x += 256)
            spr(s, SC_VOID_FLOOR, 0, x, j->ground_y, 1, 1, 0, C_WHITE, fade);
    }
}

/* ------------------------------------------------------------------------------------------ */
/* step                                                                                        */
/* ------------------------------------------------------------------------------------------ */
void gml_Object_o_scyther_Step_0(CInstance *s, CInstance *o) {
    Scy *j = slot(s, true);
    j->aura_t++;
    if (j->fail_t > 0) j->fail_t--;
    bool pok = parent_ok(s);

    if (j->move == MV_SPECIAL) {
        if (!pok) special_abort(s, j);
        else special_step(s, j);
        effects_step(s, j); thrown_step(s, j); blackhole_step(s, j); lance_step(s, j);
        return;
    }
    if (pok && j->move == MV_NONE && special_pressed(s)) {
        start_special(s, j);
        if (j->move == MV_SPECIAL) return;
    }

    RValue ret = rv_undef();
    gml_Script_scr_plr_step(s, o, &ret, 0, 0);             /* the game's movement / input framework */
    rv_free(&ret);

    if (pok && j->move != MV_NONE) {
        if (pget(s, &g_VAR_is_hurt) > 0.5 || pget(s, &g_VAR_is_fallen) > 0.5) {   /* interrupted */
            j->move = MV_NONE; j->anim = -1; j->wmode = W_META; j->ghosting = 0; j->alpha = 1;
            bset(s, &g_VAR_image_speed, 0.25);
        } else if (j->move == MV_COMBO) combo_step(s, j);
        else if (j->move == MV_SKILL1) skill1_step(s, j);
        else if (j->move == MV_SKILL2) skill2_step(s, j);
    }
    effects_step(s, j);
    thrown_step(s, j);
    blackhole_step(s, j);
    lance_step(s, j);

    RValue v[2] = { rv_real(0.6), rv_real(1) };
    RValue *args[2] = { &v[0], &v[1] };
    RValue r2 = rv_undef();
    gml_Script_scr_char_charge_effect(s, o, &r2, 2, args);
    rv_free(&r2);
}

/* ------------------------------------------------------------------------------------------ */
/* drawing                                                                                     */
/* ------------------------------------------------------------------------------------------ */
/* the scythe in hand: tween toward the frame's angle, or spin, or the 3D orbit sprites */
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
    float target = (float)m->ang;
    if (!j->wdraw_ok) { j->wdraw = target; j->wdraw_ok = 1; }
    float d = wrap360(target - j->wdraw + 180) - 180;        /* shortest way round */
    j->wdraw = wrap360(j->wdraw + d * 0.5f);
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

void gml_Object_o_scyther_Draw_0(CInstance *s, CInstance *o) {
    (void)o;
    Scy *j = slot(s, true);
    float x = sx_(s), y = sy_(s);
    float xs = (float)sget(s, &g_VAR_image_xscale);
    bool pok = parent_ok(s);
    bool charging = pok && pget(s, &g_VAR_is_charging) > 0.5;

    /* behind the body: far halves of the swings and of the scythe, the aura, afterimages */
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
        YYGML_draw_sprite_ext(s, g->spr, g->img, g->x, g->y, g->xs * 0.5f, 0.5f, 0, C_GHOST, 0.45f * (1 - g->t / 14.0f));
    }
    /* the rooster himself (2x sprite at half scale) */
    int sp = (int)sget(s, &g_VAR_sprite_index);
    if (sp >= 0) {
        int ours = body_anim(s) >= 0;
        float k = ours ? 0.5f : 1.0f;
        YYGML_draw_sprite_ext(s, sp, (float)sget(s, &g_VAR_image_index), x, y, xs * k, k,
                              (float)sget(s, &g_VAR_image_angle), C_WHITE, j->alpha * (float)sget(s, &g_VAR_image_alpha));
    }
    draw_weapon(s, j, x, y, xs, 1);
    draw_arcs(s, j, 1);

    /* reality tears: the hole (normal blend) then its glowing torn edge (additive) */
    for (int i = 0; i < N_RIFT; i++) {
        Rift *r = &j->rifts[i];
        if (!r->on) continue;
        float f = rift_frame(r);
        int v = r->big ? SC_RIFTBIG_V : SC_RIFT_V;
        spr(s, v, f, r->x, r->y, r->sc, r->sc, -r->ang, C_WHITE, 1);
        blend(s, 1);
        spr(s, v + 1, f, r->x, r->y, r->sc, r->sc, -r->ang, C_WHITE, 1);
        blend(s, 0);
    }
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
            spr(s, SC_BH_DEBRIS, (float)((j->bh_t / 3 + i) % 8), j->bh_x + rr * sinf_(ang + 1.5708f), j->bh_y + rr * 0.45f * sinf_(ang),
                1, 1, 0, C_WHITE, g);
        }
        blend(s, 1);
        spr(s, SC_BH_DISKF, (float)(j->bh_t / 2), j->bh_x, j->bh_y, g, g, 0, C_WHITE, 1);
        blend(s, 0);
    }
    /* Void Lance: iris charging in the aperture, the beam, its head */
    blend(s, 1);
    if (j->eye_on) {
        float k = j->eye_t < 20 ? j->eye_t / 20.0f : 1.0f;
        if (j->eye_t > 60) k *= 1 - (j->eye_t - 60) / 12.0f;
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
