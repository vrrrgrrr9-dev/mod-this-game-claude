/*
 * Jeff the anteater - a new fighter for the WOTU "Coco" mod.
 *
 *  combo 1 (attack A) and combo 2 (attack B): jab -> cross -> hook -> uppercut
 *  defend: crouches and blocks with both hands (spr_defend)
 *  skill 1 (skill button):            Formic Arcana - a runic ant swarm that sweeps forward and bursts
 *  skill 2 (down + skill):            Starlight Lance - a star beam fired from his snout, ends in a nova
 *  special (shield + skill together): Bone Breaker - grabs the nearest enemy, X-ray cutscene that
 *                                     breaks their bones, then their HP is set to 0
 *
 * Built on the game's own character framework (same as Erbito Black Rose): scr_plr_step drives
 * movement/inputs, combos run through alarm[3]/alarm[2] like every original character, and hits
 * are o_mask_hit hitboxes (scr_combo_normal), so blocking, knockback and KO behave normally.
 */
#include "yyc.h"
#include "jeff_assets.h"

#define JEFF_CHAR_ID   1005
#define OBJ_JEFF       685
#define OBJ_MASK_HIT   224
#define OBJ_PARENT_CHARACTER 420
#define OBJ_CAMERA     9

#define SPR_MASK_STAND 1684
#define SPR_MASK_CROUCH 1682
#define SPR_MASK16 656
#define SPR_MASK24 658
#define SPR_MASK32 659
#define SPR_MASK64 660
#define SPR_HIT_1 312
#define SPR_HIT_3 314
#define SPR_HIT_5 317
#define SPR_AURA_WHITE 235

#define SND_JUMP 190
#define SND_WOOSH1 465
#define SND_WOOSH2 466
#define SND_WOOSH3 467
#define SND_MAGIC1 201
#define SND_MAGIC3 203
#define SND_MAGICSTUN_CAST 206
#define SND_BALL_CHARGE 266
#define SND_CYBERBEAM 80
#define SND_EXPLOSION_MEGA 100
#define SND_DARKEXPLOSION 82
#define SND_SUSPENSE 13
#define SND_STRONG1 162
#define SND_STRONG2 163
#define SND_KO 18
#define SND_WINLOSE_IMPACT 464
#define SND_THUNDER 177

#define C_WHITE  0xFFFFFF
#define RGB(r, g, b) ((int)((r) | ((g) << 8) | ((b) << 16)))   /* GameMaker colours are BGR */
#define C_VIOLET RGB(200, 110, 255)
#define C_AMBER  RGB(255, 196, 70)
#define C_CYAN   RGB(120, 240, 255)
#define C_RED    RGB(255, 60, 60)

enum { MOVE_NONE, MOVE_SKILL1, MOVE_SKILL2, MOVE_SPECIAL };

#define SP_DASH   14      /* frames of the dash toward the victim */
#define SP_CUT    156     /* cutscene length (frames) */
#define SP_AFTER  36      /* after the final blow */

typedef struct {
    CInstance *inst;
    int move, t;
    float dir;
    /* skill 1 */
    int sw_on, sw_t; float sw_x, sw_y, sw_dir;
    int burst_on, burst_t; float burst_x, burst_y;
    /* skill 2 */
    int beam_on, beam_t; float beam_x, beam_y, beam_dir, beam_len;
    int nova_on, nova_t; float nova_x, nova_y;
    /* special */
    int tgt_id; float tgt_x, tgt_y, start_x; int cut_t, hit_done, depth_saved; double old_depth;
    int impact_on, impact_t; float impact_x, impact_y;
    float shake;
    int aura_t;
    int fail_t;
    int home_t; float home_v, home_dir;   /* homing lunge at the start of a punch */
} Jeff;

static Jeff g_jeff[8];
int g_jeff_spr[A_COUNT];
int g_jeff_snd[S_COUNT];
int g_jeff_loaded;

/* ------------------------------------------------------------------------------------------ */
/* small runtime helpers                                                                      */
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

/* the controlling o_player_control instance ("parent" in the game's code) */
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

static unsigned g_rng = 0x9e3779b9u;
static unsigned rnd(void) { g_rng ^= g_rng << 13; g_rng ^= g_rng >> 17; g_rng ^= g_rng << 5; return g_rng; }
static float frand(float a, float b) { return a + (b - a) * (float)(rnd() & 0xffff) / 65535.0f; }

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
static void play_custom(CInstance *s, int which, double pitch) { play(s, g_jeff_snd[which], pitch); }

static void blend(CInstance *s, int mode) {
    RValue r = rv_undef(); RValue a = rv_real(mode);
    F_GPUSetBlendMode(&r, s, s, 1, &a);
    rv_free(&r);
}
static void spr(CInstance *s, int a, float img, float x, float y, float xs, float ys, float rot, int col, float alpha) {
    int id = g_jeff_spr[a];
    if (id < 0) return;
    YYGML_draw_sprite_ext(s, id, img, x, y, xs, ys, rot, col, alpha);
}
static void camera_shake(double amount) {
    RValue cam = rv_real(OBJ_CAMERA);
    RValue v = rv_real(amount);
    YYGML_Variable_SetValue(&cam, g_VAR_camera_shake.id, ARRAY_INDEX_NONE, &v);
}

/* ------------------------------------------------------------------------------------------ */
/* assets                                                                                      */
/* ------------------------------------------------------------------------------------------ */
void jeff_load_assets(CInstance *s) {
    if (g_jeff_loaded) return;
    g_jeff_loaded = 1;
    for (int i = 0; i < A_COUNT; i++) {
        RValue r = rv_undef();
        RValue a[6];
        YYCreateString(&a[0], k_sprites[i].file);
        a[1] = rv_real(k_sprites[i].frames);
        a[2] = rv_bool(false);
        a[3] = rv_bool(false);
        a[4] = rv_real(k_sprites[i].ox);
        a[5] = rv_real(k_sprites[i].oy);
        F_SpriteAdd(&r, s, s, 6, a);
        g_jeff_spr[i] = (r.kind & KIND_MASK) == VALUE_UNDEFINED ? -1 : (int)rv_num(&r);
        rv_free(&r);
        rv_free(&a[0]);
    }
    for (int i = 0; i < S_COUNT; i++) {
        RValue r = rv_undef();
        RValue a;
        YYCreateString(&a, k_sounds[i]);
        F_AudioCreateStream(&r, s, s, 1, &a);
        g_jeff_snd[i] = (r.kind & KIND_MASK) == VALUE_UNDEFINED ? -1 : (int)rv_num(&r);
        rv_free(&r);
        rv_free(&a);
    }
    /* the character select screen previews characters with their object's sprite */
    if (g_jeff_spr[A_PREVIEW] >= 0) {
        RValue r = rv_undef();
        RValue a[2] = { rv_real(OBJ_JEFF), rv_real(g_jeff_spr[A_PREVIEW]) };
        F_ObjectSetSprite(&r, s, s, 2, a);
        rv_free(&r);
    }
}

/* ------------------------------------------------------------------------------------------ */
/* per-instance state                                                                          */
/* ------------------------------------------------------------------------------------------ */
static Jeff *slot(CInstance *s, bool create) {
    for (int i = 0; i < 8; i++) if (g_jeff[i].inst == s) return &g_jeff[i];
    if (!create) return 0;
    for (int i = 0; i < 8; i++) if (!g_jeff[i].inst) {
        Jeff *j = &g_jeff[i];
        char *p = (char *)j; for (unsigned k = 0; k < sizeof(Jeff); k++) p[k] = 0;
        j->inst = s; j->dir = 1; j->tgt_id = -1;
        return j;
    }
    /* table full (should never happen): recycle slot 7 */
    Jeff *j = &g_jeff[7];
    char *p = (char *)j; for (unsigned k = 0; k < sizeof(Jeff); k++) p[k] = 0;
    j->inst = s; j->dir = 1; j->tgt_id = -1;
    return j;
}

/* ------------------------------------------------------------------------------------------ */
/* hitboxes                                                                                    */
/* ------------------------------------------------------------------------------------------ */
/* scr_combo_normal(spr, mask, xoff, yoff, push, hforce, vforce, dmg, duration, ?, knock, alarm2,
 *                  hit_snd, hit_spr, hit_color)  - the game's own melee hit helper */
static void combo_normal(CInstance *s, CInstance *o, int sprite, int mask, double xoff, double yoff,
                         double push, double hforce, double vforce, double dmg, double dur, bool knock,
                         double alarm2, int hit_snd, int hit_spr, int color) {
    RValue v[15] = {
        rv_real(sprite), rv_real(mask), rv_real(xoff), rv_real(yoff), rv_real(push), rv_real(hforce),
        rv_real(vforce), rv_real(dmg), rv_real(dur), rv_real(35), rv_bool(knock), rv_real(alarm2),
        rv_real(hit_snd), rv_real(hit_spr), rv_real(color)
    };
    RValue *args[15];
    for (int i = 0; i < 15; i++) args[i] = &v[i];
    RValue ret = rv_undef();
    gml_Script_scr_combo_normal(s, o, &ret, 15, args);
    rv_free(&ret);
}

/* free-standing hitbox (o_mask_hit with can_follow = false) for projectiles / the special */
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

/* ------------------------------------------------------------------------------------------ */
/* events                                                                                      */
/* ------------------------------------------------------------------------------------------ */
void gml_Object_o_jeff_Create_0(CInstance *s, CInstance *o) {
    jeff_load_assets(s);
    gml_Object_o_parent_character_Create_0(s, o);        /* event_inherited() */
    slot(s, true);
    /* same variable set as o_plr_erbitobkr (Erbito Black Rose) */
    iset(s, &g_VAR_parent, 0);
    iset_b(s, &g_VAR_local_runleft, false);
    iset(s, &g_VAR_combo_next, -1);
    iset_b(s, &g_VAR_combo_nextcombo, false);
    iset_b(s, &g_VAR_has_voice, false);
    iset_b(s, &g_VAR_is_speaking, false);
    iset(s, &g_VAR_current_voice_audio, -1);
    iset(s, &g_VAR_img_voice, 0);
    iset_str(s, &g_VAR_char_name, "Jeff");
    iset(s, &g_VAR_stats_hp, 2300);
    iset(s, &g_VAR_stats_dmg, 46);
    iset(s, &g_VAR_stats_walkspd, 3.2);
    iset(s, &g_VAR_stats_airdashspd, 8.2);
    iset(s, &g_VAR_stats_runspd, 7.4);
    iset(s, &g_VAR_stats_jumpforce, -6.7);
    iset(s, &g_VAR_snd_jump, SND_JUMP);
    iset(s, &g_VAR_snd_transform, SND_JUMP);
    iset(s, &g_VAR_hp_draw_y, 62);
    iset(s, &g_VAR_hp_width, 40);
    iset(s, &g_VAR_hp_height, 5);
    iset(s, &g_VAR_energy_skill1_cost, 55);
    iset(s, &g_VAR_energy_skill2_cost, 45);
    iset(s, &g_VAR_spr_stand, g_jeff_spr[A_STAND]);
    iset(s, &g_VAR_spr_crouch, g_jeff_spr[A_CROUCH]);
    iset(s, &g_VAR_spr_charge, g_jeff_spr[A_CHARGE]);
    iset(s, &g_VAR_spr_run, g_jeff_spr[A_RUN]);
    iset(s, &g_VAR_spr_walk, g_jeff_spr[A_WALK]);
    iset(s, &g_VAR_spr_jump, g_jeff_spr[A_JUMP]);
    iset(s, &g_VAR_spr_fall, g_jeff_spr[A_FALL]);
    iset(s, &g_VAR_spr_defend, g_jeff_spr[A_DEFEND]);
    iset(s, &g_VAR_spr_fallen, g_jeff_spr[A_FALLEN]);
    iset(s, &g_VAR_spr_hurt, g_jeff_spr[A_HURT]);
    iset(s, &g_VAR_spr_hurtup, g_jeff_spr[A_HURTUP]);
    iset(s, &g_VAR_spr_hurtdown, g_jeff_spr[A_HURTDOWN]);
    iset(s, &g_VAR_spr_transform, -1);
    iset(s, &g_VAR_spr_mask_stand, SPR_MASK_STAND);
    iset(s, &g_VAR_spr_mask_crouch, SPR_MASK_CROUCH);
    bset(s, &g_VAR_sprite_index, g_jeff_spr[A_STAND]);
    bset(s, &g_VAR_mask_index, SPR_MASK_STAND);
    bset(s, &g_VAR_image_speed, 0.3);
    bset_i(s, &g_VAR_alarm, 0, 1);
    iset(s, &g_VAR_imgindex_aura, 0);
    iset(s, &g_VAR_img_index_aura, 8);
    iset(s, &g_VAR_ef_img_aura, 2);
}

/* alarm[0]: the controller exists now -> give it Jeff's HUD face (like Erbito's Alarm_0) */
void gml_Object_o_jeff_Alarm_0(CInstance *s, CInstance *o) {
    (void)o;
    if (!parent_ok(s) || g_jeff_spr[A_FACE] < 0) return;
    pset(s, &g_VAR_spr_face, g_jeff_spr[A_FACE]);
}

void gml_Object_o_jeff_Destroy_0(CInstance *s, CInstance *o) {
    Jeff *j = slot(s, false);
    if (j) j->inst = 0;
    gml_Object_o_parent_character_Destroy_0(s, o);
}

/* ------------------------------------------------------------------------------------------ */
/* combos: jab, cross, hook, uppercut  (combo_next 1-4 = attack A, 50-53 = attack B)           */
/* ------------------------------------------------------------------------------------------ */
static void start_skill1(CInstance *s, Jeff *j);
static void start_skill2(CInstance *s, Jeff *j);

static CInstance *find_target(CInstance *s, int *out_id);
static float facing(CInstance *s);

/* a short homing lunge so the punch connects (the CPU presses attack from ~50 px away): turns to an
   opponent right behind him and closes the gap over 5 frames, on top of the punch's own push */
static void jeff_home(CInstance *s, Jeff *j) {
    int tid = -1;
    j->home_t = 0;
    if (!parent_ok(s)) return;
    CInstance *e = find_target(s, &tid);
    if (!e) return;
    float dx = (float)(sget(e, &g_VAR_x) - sget(s, &g_VAR_x)), dy = (float)(sget(e, &g_VAR_y) - sget(s, &g_VAR_y));
    float adx = dx < 0 ? -dx : dx, ady = dy < 0 ? -dy : dy;
    if (adx > 170 || ady > 70) return;
    float dir = facing(s);
    if (dx * dir < 0) {
        if (adx > 70) return;
        dir = -dir;
        bset(s, &g_VAR_image_xscale, dir);
    }
    float gap = adx - 26;
    if (gap <= 1) return;
    if (gap > 120) gap = 120;
    j->home_dir = dir; j->home_v = gap / 5; j->home_t = 5;
}

static void jeff_combo(CInstance *s, CInstance *o, int step) {
    Jeff *j = slot(s, true);
    if ((step >= 1 && step <= 4) || (step >= 50 && step <= 53) || step == 10 || step == 60) jeff_home(s, j);
    bset(s, &g_VAR_image_speed, 0.3);
    iset_b(s, &g_VAR_combo_nextcombo, false);
    double dmg = parent_ok(s) ? pget(s, &g_VAR_plr_dmg) : 40;
    bool b = (step >= 50 && step < 100);              /* attack B: same punches, arcane violet hits */
    int col = b ? C_VIOLET : C_WHITE;
    double k = b ? 1.1 : 1.0;
    switch (step) {
    case 1: case 50:                                   /* JAB */
        iset(s, &g_VAR_combo_next, step + 1);
        combo_normal(s, o, g_jeff_spr[A_JAB], SPR_MASK16, 20, -27, 3, 3, -3, dmg * 0.85 * k, 5, false, 12, 1, SPR_HIT_1, col);
        play(s, SND_WOOSH1, 1.15);
        break;
    case 2: case 51:                                   /* CROSS */
        iset(s, &g_VAR_combo_next, step + 1);
        combo_normal(s, o, g_jeff_spr[A_CROSS], SPR_MASK16, 23, -27, 4, 4, -3, dmg * 1.0 * k, 5, false, 13, 1, SPR_HIT_1, col);
        play(s, SND_WOOSH2, 1.05);
        break;
    case 3: case 52:                                   /* HOOK */
        iset(s, &g_VAR_combo_next, step + 1);
        combo_normal(s, o, g_jeff_spr[A_HOOK], SPR_MASK24, 22, -31, 3, 6, -4, dmg * 1.15 * k, 6, false, 15, 1, SPR_HIT_3, col);
        play(s, SND_WOOSH3, 0.95);
        break;
    case 4: case 53:                                   /* UPPERCUT - launches */
        iset(s, &g_VAR_combo_next, -1);
        combo_normal(s, o, g_jeff_spr[A_UPPERCUT], SPR_MASK24, 16, -38, 2, 7, -12, dmg * 1.6 * k, 7, true, 24, 2, SPR_HIT_3, col);
        play(s, SND_STRONG2, 1.0);
        if (parent_ok(s) && pget(s, &g_VAR_is_onair) < 0.5) bset(s, &g_VAR_vspeed, -3.2);
        camera_shake(1);
        break;
    case 10: case 60:                                  /* crouching jab */
        iset(s, &g_VAR_combo_next, -1);
        combo_normal(s, o, g_jeff_spr[A_CROUCHPUNCH], SPR_MASK16, 21, -12, 2, 4, -2, dmg * 0.9 * k, 5, false, 14, 1, SPR_HIT_1, col);
        play(s, SND_WOOSH1, 1.2);
        break;
    case 11: case 61:                                  /* air punch */
        iset(s, &g_VAR_combo_next, -1);
        combo_normal(s, o, g_jeff_spr[A_AIRPUNCH], SPR_MASK16, 18, -20, 0, 4, 3, dmg * 1.0 * k, 5, false, 16, 1, SPR_HIT_1, col);
        play(s, SND_WOOSH2, 1.1);
        break;
    case 100:
        start_skill1(s, j);
        break;
    case 110:
        start_skill2(s, j);
        break;
    default:                                           /* unknown step: end the attack cleanly */
        iset(s, &g_VAR_combo_next, -1);
        bset_i(s, &g_VAR_alarm, 2, 1);
        break;
    }
}

/* alarm[3]: start of an attack (set by scr_plr_step with combo_next) */
void gml_Object_o_jeff_Alarm_3(CInstance *s, CInstance *o) {
    if (parent_ok(s)) pset_b(s, &g_VAR_is_attacking, true);
    jeff_combo(s, o, (int)iget(s, &g_VAR_combo_next));
}

/* alarm[2]: combo window over -> next hit or finish (native copy of scr_alarm2_combo) */
void gml_Object_o_jeff_Alarm_2(CInstance *s, CInstance *o) {
    double next = iget(s, &g_VAR_combo_next);
    RValue *nc = var_slot_r(s, g_VAR_combo_nextcombo.id);
    if (nc && BOOL_RValue(nc) && next > 0) {
        jeff_combo(s, o, (int)next);
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
/* skill 1 - Formic Arcana (runic ant swarm)                                                   */
/* ------------------------------------------------------------------------------------------ */
static float facing(CInstance *s) { return sget(s, &g_VAR_image_xscale) < 0 ? -1.0f : 1.0f; }

static void start_skill1(CInstance *s, Jeff *j) {
    j->move = MOVE_SKILL1; j->t = 0; j->dir = facing(s);
    iset(s, &g_VAR_combo_next, -1);
    bset_i(s, &g_VAR_alarm, 2, 42);                  /* holds is_attacking for the whole cast */
    bset(s, &g_VAR_sprite_index, g_jeff_spr[A_CAST1]);
    bset(s, &g_VAR_image_index, 0);
    bset(s, &g_VAR_image_speed, 0);
    bset(s, &g_VAR_hspeed, 0);
    play(s, SND_MAGICSTUN_CAST, 1.0);
}

static void skill1_step(CInstance *s, Jeff *j) {
    j->t++;
    int t = j->t;
    bset(s, &g_VAR_sprite_index, g_jeff_spr[A_CAST1]);
    bset(s, &g_VAR_image_index, t < 8 ? 0 : t < 16 ? 1 : t < 24 ? 2 : 3);
    bset(s, &g_VAR_hspeed, 0);
    if (t == 16) {
        j->sw_on = 1; j->sw_t = 0; j->sw_dir = j->dir;
        j->sw_x = (float)sget(s, &g_VAR_x) + j->dir * 22;
        j->sw_y = (float)sget(s, &g_VAR_y) - 6;
        play(s, SND_MAGIC3, 0.9);
        play_custom(s, S_SWARM, 1.0);
        camera_shake(1);
    }
    if (t >= 42) j->move = MOVE_NONE;
}

static void swarm_step(CInstance *s, Jeff *j) {
    if (j->sw_on) {
        j->sw_t++;
        float spd = 2.6f + (j->sw_t < 24 ? j->sw_t * 0.12f : 2.9f);
        j->sw_x += j->sw_dir * spd;
        if (j->sw_t % 5 == 0 && parent_ok(s)) {
            double dmg = pget(s, &g_VAR_plr_dmg);
            Hit h = { dmg * 0.34, j->sw_dir * 2.0, -1.5, 14, 4, 1.5, 1.2, SPR_MASK32, 1, 0, 1, 0, SPR_HIT_5, C_AMBER, 1 };
            spawn_hit(s, j->sw_x, j->sw_y - 8, &h);
        }
        if (j->sw_t >= 78) {
            j->sw_on = 0;
            j->burst_on = 1; j->burst_t = 0; j->burst_x = j->sw_x; j->burst_y = j->sw_y;
            if (parent_ok(s)) {
                double dmg = pget(s, &g_VAR_plr_dmg);
                Hit h = { dmg * 1.5, j->sw_dir * 9.0, -8.0, 30, 6, 1.6, 1.6, SPR_MASK64, 1, 1, 1, 1, SPR_HIT_3, C_AMBER, 2 };
                spawn_hit(s, j->burst_x, j->burst_y - 20, &h);
            }
            play(s, SND_DARKEXPLOSION, 1.1);
            camera_shake(2);
        }
    }
    if (j->burst_on && ++j->burst_t >= 32) j->burst_on = 0;
}

/* ------------------------------------------------------------------------------------------ */
/* skill 2 - Starlight Lance (beam from the snout, ends in a nova)                            */
/* ------------------------------------------------------------------------------------------ */
static void start_skill2(CInstance *s, Jeff *j) {
    j->move = MOVE_SKILL2; j->t = 0; j->dir = facing(s);
    iset(s, &g_VAR_combo_next, -1);
    bset_i(s, &g_VAR_alarm, 2, 82);
    bset(s, &g_VAR_sprite_index, g_jeff_spr[A_CAST2]);
    bset(s, &g_VAR_image_index, 0);
    bset(s, &g_VAR_image_speed, 0);
    bset(s, &g_VAR_hspeed, 0);
    play(s, SND_BALL_CHARGE, 1.0);
}

static float snout_x(CInstance *s, Jeff *j) { return (float)sget(s, &g_VAR_x) + j->dir * 27; }
static float snout_y(CInstance *s) { return (float)sget(s, &g_VAR_y) - 34; }

static void skill2_step(CInstance *s, Jeff *j) {
    j->t++;
    int t = j->t;
    bset(s, &g_VAR_sprite_index, g_jeff_spr[A_CAST2]);
    bset(s, &g_VAR_image_index, t < 10 ? 0 : t < 26 ? 1 : t < 32 ? 2 : 3);
    bset(s, &g_VAR_hspeed, 0);
    if (t == 26) {
        j->beam_on = 1; j->beam_t = 0; j->beam_dir = j->dir; j->beam_len = 0;
        j->beam_x = snout_x(s, j); j->beam_y = snout_y(s);
        play(s, SND_CYBERBEAM, 0.9);
        play_custom(s, S_BEAM, 1.0);
        camera_shake(2);
    }
    if (t >= 82) j->move = MOVE_NONE;
}

static void beam_step(CInstance *s, Jeff *j) {
    if (j->beam_on) {
        j->beam_t++;
        float target = 330.0f;
        j->beam_len = j->beam_len + (target - j->beam_len) * 0.35f;
        if (j->beam_t % 4 == 0 && j->beam_t <= 40 && parent_ok(s)) {
            double dmg = pget(s, &g_VAR_plr_dmg);
            float len = j->beam_len;
            Hit h = { dmg * 0.27, j->beam_dir * 1.5, -0.5, 10, 3, len / 64.0, 0.4, SPR_MASK64, 1, 0, 1, 0, SPR_HIT_5, C_CYAN, 1 };
            /* s_mask_hit_* sprites are centred: put the scaled mask on the middle of the beam */
            spawn_hit(s, j->beam_x + j->beam_dir * len * 0.5f, j->beam_y, &h);
        }
        if (j->beam_t == 44) {
            j->nova_on = 1; j->nova_t = 0;
            j->nova_x = j->beam_x + j->beam_dir * j->beam_len; j->nova_y = j->beam_y;
            if (parent_ok(s)) {
                double dmg = pget(s, &g_VAR_plr_dmg);
                Hit h = { dmg * 1.35, j->beam_dir * 10.0, -9.0, 30, 6, 1.5, 1.5, SPR_MASK64, 1, 1, 1, 1, SPR_HIT_3, C_CYAN, 2 };
                spawn_hit(s, j->nova_x, j->nova_y, &h);
            }
            play(s, SND_EXPLOSION_MEGA, 1.15);
            camera_shake(3);
        }
        if (j->beam_t >= 56) j->beam_on = 0;
    }
    if (j->nova_on && ++j->nova_t >= 36) j->nova_on = 0;
}

/* ------------------------------------------------------------------------------------------ */
/* special - Bone Breaker (shield + skill together)                                           */
/* ------------------------------------------------------------------------------------------ */
static CInstance *find_target(CInstance *s, int *out_id) {
    RValue me_team_rv = rv_undef();
    YYGML_Variable_GetValue(parent_of(s), g_VAR_plr_team.id, ARRAY_INDEX_NONE, &me_team_rv, false, false);
    double my_team = rv_num(&me_team_rv); rv_free(&me_team_rv);
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
        double d = (dx < 0 ? -dx : dx) + (dy < 0 ? -dy : dy) * 1.5;
        if (d < bestd && (dx < 0 ? -dx : dx) < 300 && (dy < 0 ? -dy : dy) < 140) { bestd = d; best = c; best_id = INT32_RValue(&id); }
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

/* the CPU never holds shield + skill together: when it presses skill with a full bar and the
   opponent in reach, it uses the Bone Breaker instead */
static bool cpu_wants_special(CInstance *s) {
    if (!parent_ok(s) || pget(s, &g_VAR_plr_controller) != 2 || pget(s, &g_VAR_keyp_special) < 0.5) return false;
    if (pget(s, &g_VAR_is_hurt) > 0.5 || pget(s, &g_VAR_is_fallen) > 0.5 || pget(s, &g_VAR_is_dead) > 0.5) return false;
    if (pget(s, &g_VAR_is_onair) > 0.5) return false;
    double e = pget(s, &g_VAR_plr_energy), emax = pget(s, &g_VAR_plr_maxenergy);
    double need = emax > 0 ? (emax < 100 ? emax : 100) : 100;
    if (e + 0.001 < need) return false;
    int tid = -1;
    return find_target(s, &tid) != 0;
}

static void pin_target(CInstance *s, Jeff *j) {
    CInstance *c = j->tgt_id >= 0 ? YYGML_FindInstance(j->tgt_id) : 0;
    if (!c) return;
    bset(c, &g_VAR_x, j->tgt_x);
    bset(c, &g_VAR_y, j->tgt_y);
    bset(c, &g_VAR_hspeed, 0);
    bset(c, &g_VAR_vspeed, 0);
    RValue cp = rv_undef(); RValue cid = rv_real(j->tgt_id);
    YYGML_Variable_GetValue(&cid, g_VAR_parent.id, ARRAY_INDEX_NONE, &cp, false, false);
    if (inst_exists_rv(s, &cp)) {
        RValue f = rv_bool(false);
        YYGML_Variable_SetValue(&cp, g_VAR_can_move.id, ARRAY_INDEX_NONE, &f);
        YYGML_Variable_SetValue(&cp, g_VAR_can_attack.id, ARRAY_INDEX_NONE, &f);
    }
    rv_free(&cp);
}

static void release_target(CInstance *s, Jeff *j) {
    if (j->tgt_id < 0) return;
    RValue cp = rv_undef(); RValue cid = rv_real(j->tgt_id);
    CInstance *c = YYGML_FindInstance(j->tgt_id);
    if (c) YYGML_Variable_GetValue(&cid, g_VAR_parent.id, ARRAY_INDEX_NONE, &cp, false, false);
    if (c && inst_exists_rv(s, &cp)) {
        RValue tr = rv_bool(true);
        YYGML_Variable_SetValue(&cp, g_VAR_can_move.id, ARRAY_INDEX_NONE, &tr);
        YYGML_Variable_SetValue(&cp, g_VAR_can_attack.id, ARRAY_INDEX_NONE, &tr);
    }
    rv_free(&cp);
}

static void special_finish_blow(CInstance *s, Jeff *j) {
    CInstance *c = j->tgt_id >= 0 ? YYGML_FindInstance(j->tgt_id) : 0;
    release_target(s, j);
    if (!c) return;
    /* the game's own hit pipeline (hurt anim, knockback, sound) ... */
    Hit h = { 999999, j->dir * 12.0, -10.0, 40, 6, 2.0, 2.0, SPR_MASK32, 1, 1, 0, 1, SPR_HIT_3, C_RED, 2 };
    spawn_hit(s, sget(c, &g_VAR_x), sget(c, &g_VAR_y) - 24, &h);
    /* ... and the HP itself goes straight to 0 */
    RValue cp = rv_undef(); RValue cid = rv_real(j->tgt_id);
    YYGML_Variable_GetValue(&cid, g_VAR_parent.id, ARRAY_INDEX_NONE, &cp, false, false);
    if (inst_exists_rv(s, &cp)) {
        RValue z = rv_real(0);
        YYGML_Variable_SetValue(&cp, g_VAR_plr_hp.id, ARRAY_INDEX_NONE, &z);
    }
    rv_free(&cp);
    j->impact_on = 1; j->impact_t = 0;
    j->impact_x = (float)sget(c, &g_VAR_x); j->impact_y = (float)sget(c, &g_VAR_y) - 28;
}

static void start_special(CInstance *s, Jeff *j) {
    /* consume the button so scr_plr_step doesn't also fire a skill this frame */
    pset_b(s, &g_VAR_keyp_special, false);
    double e = pget(s, &g_VAR_plr_energy), emax = pget(s, &g_VAR_plr_maxenergy);
    double need = emax > 0 ? (emax < 100 ? emax : 100) : 100;
    int tid = -1;
    CInstance *t = find_target(s, &tid);
    if (e + 0.001 < need || !t) {                     /* not enough energy / nobody in reach */
        j->fail_t = 24;
        play(s, SND_WOOSH3, 0.6);
        return;
    }
    pset(s, &g_VAR_plr_energy, e - need);
    j->move = MOVE_SPECIAL; j->t = 0; j->cut_t = 0; j->hit_done = 0;
    j->tgt_id = tid;
    j->tgt_x = (float)sget(t, &g_VAR_x); j->tgt_y = (float)sget(t, &g_VAR_y);
    j->start_x = (float)sget(s, &g_VAR_x);
    j->dir = j->tgt_x >= j->start_x ? 1.0f : -1.0f;
    bset(s, &g_VAR_image_xscale, j->dir);
    pset_b(s, &g_VAR_is_attacking, true);
    pset_b(s, &g_VAR_can_gethurt, false);           /* untouchable during the cutscene */
    iset(s, &g_VAR_combo_next, -1);
    bset_i(s, &g_VAR_alarm, 2, -1);
    j->old_depth = sget(s, &g_VAR_depth); j->depth_saved = 1;
    bset(s, &g_VAR_depth, -15000);                   /* our GUI cutscene draws over the HUD */
    bset(s, &g_VAR_sprite_index, g_jeff_spr[A_GRAB]);
    bset(s, &g_VAR_image_index, 0);
    bset(s, &g_VAR_image_speed, 0);
    bset(s, &g_VAR_hspeed, 0);
    bset(s, &g_VAR_vspeed, 0);
    play(s, SND_SUSPENSE, 1.0);
    camera_shake(2);
}

static void special_step(CInstance *s, Jeff *j) {
    j->t++;
    int t = j->t;
    bset(s, &g_VAR_hspeed, 0);
    bset(s, &g_VAR_vspeed, 0);
    pin_target(s, j);
    if (t <= SP_DASH) {                                 /* dash in */
        float goal = j->tgt_x - j->dir * 26;
        float x = j->start_x + (goal - j->start_x) * ((float)t / SP_DASH);
        bset(s, &g_VAR_x, x);
        bset(s, &g_VAR_sprite_index, g_jeff_spr[A_GRAB]);
        bset(s, &g_VAR_image_index, 0);
        if (t == SP_DASH) { play(s, SND_STRONG1, 0.8); camera_shake(2); }
        return;
    }
    if (t <= SP_DASH + SP_CUT) {                        /* cutscene (drawn in Draw_64) */
        j->cut_t = t - SP_DASH;
        bset(s, &g_VAR_sprite_index, g_jeff_spr[A_GRAB]);
        bset(s, &g_VAR_image_index, 1);
        int c = j->cut_t;
        if (c == 1) play(s, SND_THUNDER, 0.7);
        if (c == 40) { play_custom(s, S_CRACK1, 1.0); j->shake = 6; }
        if (c == 62) { play_custom(s, S_CRACK2, 1.0); j->shake = 7; }
        if (c == 84) { play_custom(s, S_CRACK3, 0.95); j->shake = 9; }
        if (c == 106) { play_custom(s, S_CRACK1, 0.75); play_custom(s, S_CRACK3, 0.8); j->shake = 12; }
        if (c == 128) { play_custom(s, S_KO, 1.0); j->shake = 14; }
        if (j->shake > 0) j->shake *= 0.86f;
        return;
    }
    if (!j->hit_done) {                                 /* the final blow: HP -> 0 */
        j->hit_done = 1;
        special_finish_blow(s, j);
        play(s, SND_WINLOSE_IMPACT, 1.0);
        play(s, SND_STRONG2, 0.7);
        camera_shake(4);
        if (j->depth_saved) { bset(s, &g_VAR_depth, j->old_depth); j->depth_saved = 0; }
        bset(s, &g_VAR_sprite_index, g_jeff_spr[A_UPPERCUT]);
        bset(s, &g_VAR_image_index, 2);
    }
    if (t == SP_DASH + SP_CUT + 12) {
        bset(s, &g_VAR_sprite_index, g_jeff_spr[A_WIN]);
        bset(s, &g_VAR_image_index, 0);
        bset(s, &g_VAR_image_speed, 0.12);
    }
    if (t >= SP_DASH + SP_CUT + SP_AFTER) {
        j->move = MOVE_NONE;
        pset_b(s, &g_VAR_can_gethurt, true);
        bset(s, &g_VAR_image_speed, 0.3);
        bset_i(s, &g_VAR_alarm, 2, 1);                 /* Alarm_2 ends is_attacking */
    }
}

static void special_abort(CInstance *s, Jeff *j) {
    release_target(s, j);
    if (j->depth_saved) { bset(s, &g_VAR_depth, j->old_depth); j->depth_saved = 0; }
    j->move = MOVE_NONE;
    if (parent_ok(s)) { pset_b(s, &g_VAR_can_gethurt, true); pset_b(s, &g_VAR_is_attacking, false); }
}

/* ------------------------------------------------------------------------------------------ */
/* step                                                                                        */
/* ------------------------------------------------------------------------------------------ */
void gml_Object_o_jeff_Step_0(CInstance *s, CInstance *o) {
    Jeff *j = slot(s, true);
    j->aura_t++;
    if (j->fail_t > 0) j->fail_t--;
    bool pok = parent_ok(s);

    if (j->move == MOVE_SPECIAL) {
        if (!pok) special_abort(s, j);
        else special_step(s, j);
        if (j->impact_on && ++j->impact_t >= 30) j->impact_on = 0;
        swarm_step(s, j);
        beam_step(s, j);
        return;
    }
    if (pok && j->move == MOVE_NONE && (special_pressed(s) || cpu_wants_special(s))) {
        start_special(s, j);
        if (j->move == MOVE_SPECIAL) return;
    }

    RValue ret = rv_undef();
    gml_Script_scr_plr_step(s, o, &ret, 0, 0);          /* the game's movement / input framework */
    rv_free(&ret);
    if (j->home_t > 0) {                                /* homing lunge of the current punch */
        j->home_t--;
        if (pok && pget(s, &g_VAR_is_hurt) < 0.5) bset(s, &g_VAR_hspeed, sget(s, &g_VAR_hspeed) + j->home_dir * j->home_v);
        else j->home_t = 0;
    }

    if (pok && (j->move == MOVE_SKILL1 || j->move == MOVE_SKILL2)) {
        if (pget(s, &g_VAR_is_hurt) > 0.5 || pget(s, &g_VAR_is_fallen) > 0.5) j->move = MOVE_NONE;   /* interrupted */
        else if (j->move == MOVE_SKILL1) skill1_step(s, j);
        else skill2_step(s, j);
    }
    swarm_step(s, j);
    beam_step(s, j);
    if (j->impact_on && ++j->impact_t >= 30) j->impact_on = 0;

    /* charge sound/effect, same call as Erbito Black Rose */
    RValue v[2] = { rv_real(0.6), rv_real(1) };
    RValue *args[2] = { &v[0], &v[1] };
    RValue r2 = rv_undef();
    gml_Script_scr_char_charge_effect(s, o, &r2, 2, args);
    rv_free(&r2);
}

/* ------------------------------------------------------------------------------------------ */
/* drawing                                                                                     */
/* ------------------------------------------------------------------------------------------ */
void gml_Object_o_jeff_Draw_0(CInstance *s, CInstance *o) {
    (void)o;
    Jeff *j = slot(s, true);
    float x = (float)sget(s, &g_VAR_x), y = (float)sget(s, &g_VAR_y);
    float xs = (float)sget(s, &g_VAR_image_xscale);
    bool pok = parent_ok(s);

    /* runic circle under Jeff while casting skill 1 (drawn behind him) */
    if (j->move == MOVE_SKILL1) {
        float a = j->t < 8 ? j->t / 8.0f : 1.0f;
        blend(s, 1);
        spr(s, A_S1_CIRCLE, (float)(j->aura_t / 2), x, y - 1, 1.0f + 0.1f * a, 1.0f, 0, C_WHITE, a);
        blend(s, 0);
    }
    /* charging aura */
    bool charging = pok && pget(s, &g_VAR_is_charging) > 0.5;
    if (charging) {
        blend(s, 1);
        spr(s, A_AURA, (float)(j->aura_t / 3), x, y, 1, 1, 0, C_WHITE, 0.85f);
        blend(s, 0);
    }

    YYGML_draw_self(s);

    if (j->fail_t > 0) {                                /* special needs a full energy bar */
        blend(s, 1);
        spr(s, A_S2_ORB, (float)(j->aura_t / 2), x, y - 62, 0.7f, 0.7f, 0, C_RED, j->fail_t / 24.0f);
        blend(s, 0);
    }
    if (charging) {
        blend(s, 1);
        spr(s, A_S1_SPARK, (float)(j->aura_t / 2), x + frand(-14, 14), y - frand(4, 50), 1, 1, 0, C_WHITE, 0.9f);
        blend(s, 0);
    }

    blend(s, 1);
    /* skill 2: snout orb while charging */
    if (j->move == MOVE_SKILL2 && j->t < 30) {
        float k = j->t / 26.0f; if (k > 1) k = 1;
        spr(s, A_S2_ORB, (float)(j->aura_t / 2), x + xs * 27, y - 34, 0.4f + 0.9f * k, 0.4f + 0.9f * k, 0, C_WHITE, 0.5f + 0.5f * k);
        for (int i = 0; i < 3; i++)
            spr(s, A_S1_SPARK, (float)((j->aura_t + i * 3) / 2), x + xs * 27 + frand(-30, 30) * (1 - k), y - 34 + frand(-26, 26) * (1 - k), 0.8f, 0.8f, 0, C_CYAN, 0.8f);
    }
    /* skill 1: the swarm + its burst */
    if (j->sw_on) {
        float img = (float)(j->sw_t / 2);
        spr(s, A_S1_SWARM, img, j->sw_x, j->sw_y, j->sw_dir, 1, 0, C_WHITE, 1);
        for (int i = 1; i <= 3; i++)
            spr(s, A_S1_SWARM, img + i, j->sw_x - j->sw_dir * 10 * i, j->sw_y, j->sw_dir * (1 - 0.15f * i), 1 - 0.15f * i, 0, C_AMBER, 0.45f / i);
        spr(s, A_S1_SPARK, (float)(j->sw_t / 2), j->sw_x + frand(-30, 30), j->sw_y - frand(0, 40), 1, 1, 0, C_AMBER, 1);
    }
    if (j->burst_on) {
        spr(s, A_S1_BURST, j->burst_t / 2.0f, j->burst_x, j->burst_y, j->sw_dir, 1, 0, C_WHITE, 1);
    }
    /* skill 2: the beam, its tip and the nova */
    if (j->beam_on) {
        float fade = j->beam_t > 44 ? 1.0f - (j->beam_t - 44) / 12.0f : 1.0f;
        float wob = 1.0f + 0.12f * (float)((j->beam_t % 4) < 2 ? 1 : -1);
        spr(s, A_S2_BEAM, (float)(j->beam_t / 2), j->beam_x, j->beam_y, j->beam_dir * j->beam_len / 32.0f, wob * fade, 0, C_WHITE, fade);
        spr(s, A_S2_TIP, (float)(j->beam_t / 2), j->beam_x + j->beam_dir * j->beam_len, j->beam_y, j->beam_dir, 1, 0, C_WHITE, fade);
        spr(s, A_S2_ORB, (float)(j->beam_t / 2), j->beam_x, j->beam_y, 1.2f, 1.2f, 0, C_WHITE, fade);
    }
    if (j->nova_on) {
        spr(s, A_S2_NOVA, j->nova_t / 2.25f, j->nova_x, j->nova_y, 1, 1, 0, C_WHITE, 1);
    }
    /* special: dash streaks and the KO impact */
    if (j->move == MOVE_SPECIAL && j->t <= SP_DASH) {
        spr(s, A_SP_DASH, (float)(j->t / 2), x, y, j->dir, 1, 0, C_WHITE, 1);
    }
    if (j->impact_on) {
        spr(s, A_SP_IMPACT, j->impact_t / 3.0f, j->impact_x, j->impact_y, j->dir, 1, 0, C_WHITE, 1);
    }
    blend(s, 0);
}

static double legacy0(CInstance *s, YYVAR *f) {
    RValue r = rv_undef();
    YYGML_CallLegacyFunction(s, s, &r, 0, f->id, 0);
    double d = rv_num(&r);
    rv_free(&r);
    return d;
}

/* GUI layer: the Bone Breaker cutscene */
void gml_Object_o_jeff_Draw_64(CInstance *s, CInstance *o) {
    (void)o;
    Jeff *j = slot(s, false);
    if (!j || j->move != MOVE_SPECIAL || j->t <= SP_DASH || j->t > SP_DASH + SP_CUT) return;
    int c = j->cut_t;
    float gw = (float)legacy0(s, &g_FUNC_display_get_gui_width);
    float gh = (float)legacy0(s, &g_FUNC_display_get_gui_height);
    if (gw < 16 || gh < 16) return;
    float sc = gw / CUT_W; if (gh / CUT_H < sc) sc = gh / CUT_H;
    float w = CUT_W * sc, h = CUT_H * sc;
    float ox = (gw - w) * 0.5f, oy = (gh - h) * 0.5f;
    float sx = 0, sy = 0;
    if (j->shake > 0.3f) { sx = frand(-j->shake, j->shake) * sc * 0.5f; sy = frand(-j->shake, j->shake) * sc * 0.5f; }

    /* panels: 36 frames over the cutscene (cut_a 0-11, cut_b 12-23, cut_c 24-35) */
    int f = (c * 36) / SP_CUT; if (f > 35) f = 35;
    int a = f < 12 ? A_CUT_A : f < 24 ? A_CUT_B : A_CUT_C;
    YYGML_draw_set_alpha(1);
    YYGML_draw_set_colour(0);
    YYGML_draw_rectangle(0, 0, gw, gh, false);
    spr(s, a, (float)(f % 12), ox + sx, oy + sy, sc, sc, 0, C_WHITE, 1);

    /* impact flashes on the bone breaks */
    int flash = 0;
    if ((c >= 40 && c < 44) || (c >= 62 && c < 66) || (c >= 84 && c < 88) || (c >= 106 && c < 111)) flash = 1;
    if (c >= 128 && c < 138) flash = 2;
    if (flash) {
        YYGML_draw_set_colour(flash == 2 ? C_WHITE : RGB(255, 240, 240));
        YYGML_draw_set_alpha(flash == 2 ? 0.9f - (c - 128) * 0.08f : 0.55f);
        YYGML_draw_rectangle(0, 0, gw, gh, false);
    }
    /* letterbox bars sliding in/out */
    float bar = h * 0.1f;
    float in = c < 10 ? c / 10.0f : (c > SP_CUT - 10 ? (SP_CUT - c) / 10.0f : 1.0f);
    YYGML_draw_set_alpha(1);
    YYGML_draw_set_colour(0);
    YYGML_draw_rectangle(0, 0, gw, oy + bar * in, false);
    YYGML_draw_rectangle(0, gh - oy - bar * in, gw, gh, false);
    YYGML_draw_set_colour(C_WHITE);
    YYGML_draw_set_alpha(1);
}
