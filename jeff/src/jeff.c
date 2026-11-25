/*
 * Jeff the anteater - a fighter for the WOTU "Coco" mod, in dark blue flame.
 *
 *  attack A: dark flame punches - jab -> cross -> hook -> flame flurry -> uppercut
 *  attack B: blue flame kicks   - front kick -> roundhouse -> spinning back kick -> axe kick
 *  down + attack A / B: crouching jab / flame sweep (trips)    air attack A / B: air punch / diving kick
 *  defend: crouches and blocks with both hands (spr_defend)
 *  skill 1 (skill button):  Meteor Shower - black holes tear open in the sky and rain meteors wrapped
 *                           in dark blue flame onto the ground in front of him
 *  skill 2 (down + skill):  Abyss Palm - his palm opens a black hole that drags the opponent in, then
 *                           his punch detonates it
 *  special (shield + skill together): Bone Breaker - grabs the nearest enemy, X-ray cutscene that
 *                                     breaks their bones, then their HP is set to 0
 *
 *  double-tap shield: switches his power, blue (dark flame) <-> red (the sun): he turns black from the
 *             feet up (the user's "dark Jeff": black body, glowing white eyes ringed in yellow, a white
 *             chest tag) - every body animation has a black copy that is swapped in when drawing
 *  red power: a sun sword and a sun shield - attack A sword (slash, rising slash, thrust, spin slash,
 *             solar cleave), attack B shield (bash, shield uppercut, shield charge, sun slam), skill 1
 *             Solar Flare (a crescent of sun fire), skill 2 Corona (the sun flares round him)
 *  double-tap skill (full bar):  RED BLACK HOLE cinematic - the opponent is pulled in and crushed: K.O.
 *  double-tap shield + double-tap skill together (full bar): HOLLOW PURPLE cinematic - he merges his
 *             red and blue, flicks it, a purple nuclear blast, he strikes a pose: K.O.
 *  (with a full bar a skill tap waits ~1/4 s to see whether it is a double tap)
 *
 * The flame: blue fire with darkness flowing inside it (pixel art, art/flame.py), drawn on whichever
 * fist / foot is "hot" in the current frame (per-frame table from the art build).
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
#define OBJ_PARENT_SOLID 425
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

#define SND_JUMP 190
#define SND_WOOSH1 465
#define SND_WOOSH2 466
#define SND_WOOSH3 467
#define SND_MAGIC3 203
#define SND_MAGICSTUN_CAST 206
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
#define C_FLAME  RGB(80, 170, 255)
#define C_RED    RGB(255, 60, 60)
#define C_SUN    RGB(255, 150, 40)
#define C_PURPLE RGB(200, 110, 255)
#define C_EYE    RGB(236, 246, 44)
#define JF_EYES  1       /* JeffFrame.flags: eyes open, front arm drawn over the body, back arm over */
#define JF_FOVER 2
#define JF_BOVER 4
#define SWORD_K   0.8f    /* the sun sword: 64 px sprite, grip at (6,10) -> 45 px blade at this scale */
#define SWORD_LEN 45.0f   /* (its angle per frame is JeffFrame.fa, from art/anims.py SWORD) */
#define SHIELD_K  0.55f

enum { MOVE_NONE, MOVE_SKILL1, MOVE_SKILL2, MOVE_SPECIAL, MOVE_FLURRY, MOVE_SWITCH, MOVE_CIN, MOVE_RSKILL1, MOVE_RSKILL2 };
enum { CIN_NONE, CIN_REDHOLE, CIN_PURPLE };
#define CIN_RED_DUR 170
#define CIN_RED_KO 118
#define CIN_PUR_DUR 200
#define CIN_PUR_KO 112
#define TAP_WINDOW 16

#define SP_DASH   14      /* frames of the dash toward the victim */
#define SP_CUT    156     /* cutscene length (frames) */
#define SP_AFTER  36      /* after the final blow */

#define N_MET 14
#define N_JFX 12
typedef struct { int on, t; float x, y, vx, vy; } Meteor;
typedef struct { int on, t, a, tpf, n, add, col; float x, y, xs, ys, rot; } JFx;

typedef struct {
    CInstance *inst;
    int move, t;
    float dir;
    /* skill 1: meteor shower */
    int portals_on, portals_t; float portal_x[3], portal_y[3], ground_y;
    Meteor met[N_MET];
    /* skill 2: black hole */
    int bh_on, bh_t; float bh_x, bh_y;
    /* one-shot effects (bursts, kick arcs, craters) and the burning limbs */
    JFx fx[N_JFX];
    int last_hot;
    /* special */
    int tgt_id; float tgt_x, tgt_y, start_x; int cut_t, hit_done, depth_saved; double old_depth;
    int impact_on, impact_t; float impact_x, impact_y;
    float shake;
    int aura_t;
    int fail_t;
    int home_t; float home_v, home_dir;   /* homing lunge at the start of a punch / kick */
    /* power: 0 blue (dark flame), 1 red (the sun) */
    int power;
    /* input: shield / skill taps */
    int prev_def, def_t1, def_t2, sk_pending, sk_t1, sk_pending_def, sk_pending_down, sw_pending, sw_pending_t, sw_cool;
    /* cinematics */
    int cin; int cin_spr; float cin_img, cin_vk; int cin_done;
    /* red skills */
    int wave_on, wave_t, wave_hits; float wave_x, wave_y, wave_dir;
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

static float fabsf_(float v) { return v < 0 ? -v : v; }
static bool finite_(float v) { return v == v && v < 1e7f && v > -1e7f; }
static float atan2f_(float y, float x) {            /* small freestanding atan2 (radians) */
    float ax = fabsf_(x), ay = fabsf_(y);
    if (ax < 1e-6f && ay < 1e-6f) return 0;
    float a = ax > ay ? ay / ax : ax / ay, q = a * a;
    float r = ((-0.0464964749f * q + 0.15931422f) * q - 0.327622764f) * q * a + a;
    if (ay > ax) r = 1.5707963f - r;
    if (x < 0) r = 3.1415927f - r;
    return y < 0 ? -r : r;
}

static bool voice_playing(CInstance *s, double v) {
    if (v <= 0) return false;
    RValue r = rv_undef(); RValue a = rv_real(v);
    F_AudioIsPlaying(&r, s, s, 1, &a);
    bool b = rv_num(&r) > 0.5;
    rv_free(&r);
    return b;
}
static double play_v(CInstance *s, int snd, double pitch) {
    if (snd < 0) return 0;
    RValue r = rv_undef();
    RValue a[3] = { rv_real(snd), rv_real(10), rv_real(0) };
    F_AudioPlaySound(&r, s, s, 3, a);
    double v = (r.kind & KIND_MASK) == VALUE_UNDEFINED ? 0 : rv_num(&r);
    if (pitch != 1.0 && (r.kind & KIND_MASK) != VALUE_UNDEFINED) {
        RValue r2 = rv_undef();
        RValue b[2] = { r, rv_real(pitch) };
        F_AudioSoundPitch(&r2, s, s, 2, b);
        rv_free(&r2);
    }
    rv_free(&r);
    return v;
}
static void play(CInstance *s, int snd, double pitch) { play_v(s, snd, pitch); }
/* our sounds are OGG files opened with audio_create_stream (each playing copy decodes on its own
   thread): never two copies of the same one at once, at most 3 of ours alive */
static double g_jeff_voice[S_COUNT];
static void play_custom(CInstance *s, int which, double pitch) {
    if (which < 0 || which >= S_COUNT || g_jeff_snd[which] < 0) return;
    if (voice_playing(s, g_jeff_voice[which])) return;
    int alive = 0;
    for (int k = 0; k < S_COUNT; k++) if (voice_playing(s, g_jeff_voice[k])) alive++;
    if (alive >= 3) return;
    g_jeff_voice[which] = play_v(s, g_jeff_snd[which], pitch);
}

static void blend(CInstance *s, int mode) {
    RValue r = rv_undef(); RValue a = rv_real(mode);
    F_GPUSetBlendMode(&r, s, s, 1, &a);
    rv_free(&r);
}
static void spr(CInstance *s, int a, float img, float x, float y, float xs, float ys, float rot, int col, float alpha) {
    int id = g_jeff_spr[a];
    if (id < 0 || !finite_(x) || !finite_(y)) return;
    float k = k_sprites[a].half ? 0.5f : 1.0f;
    YYGML_draw_sprite_ext(s, id, img, x, y, xs * k, ys * k, rot, col, alpha);
}
static void camera_shake(double amount) {
    RValue cam = rv_real(OBJ_CAMERA);
    RValue v = rv_real(amount);
    YYGML_Variable_SetValue(&cam, g_VAR_camera_shake.id, ARRAY_INDEX_NONE, &v);
}
static float sx_(CInstance *s) { return (float)sget(s, &g_VAR_x); }
static float sy_(CInstance *s) { return (float)sget(s, &g_VAR_y); }

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
static void jeff_reset(Jeff *j, CInstance *s) {
    char *p = (char *)j; for (unsigned k = 0; k < sizeof(Jeff); k++) p[k] = 0;
    j->inst = s; j->dir = 1; j->tgt_id = -1; j->last_hot = -1;
}
static Jeff *slot(CInstance *s, bool create) {
    for (int i = 0; i < 8; i++) if (g_jeff[i].inst == s) return &g_jeff[i];
    if (!create) return 0;
    for (int i = 0; i < 8; i++) if (!g_jeff[i].inst) { jeff_reset(&g_jeff[i], s); return &g_jeff[i]; }
    jeff_reset(&g_jeff[7], s);                      /* table full (should never happen): recycle */
    return &g_jeff[7];
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
static float sinf_(float x) {                       /* small, bounded sine (radians) */
    if (!finite_(x)) return 0;
    x -= 6.2831853f * (float)(int)(x / 6.2831853f);
    if (x > 3.1415927f) x -= 6.2831853f;
    if (x < -3.1415927f) x += 6.2831853f;
    float x2 = x * x;
    return x * (1 - x2 / 6 * (1 - x2 / 20 * (1 - x2 / 42 * (1 - x2 / 72))));
}
static float cosf_(float x) { return sinf_(x + 1.5707963f); }

/* ------------------------------------------------------------------------------------------ */
/* events                                                                                      */
/* ------------------------------------------------------------------------------------------ */
void gml_Object_o_jeff_Create_0(CInstance *s, CInstance *o) {
    jeff_load_assets(s);
    gml_Object_o_parent_character_Create_0(s, o);        /* event_inherited() */
    jeff_reset(slot(s, true), s);                         /* fresh state even if a stale slot matched */
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
/* moves                                                                                       */
/* ------------------------------------------------------------------------------------------ */
static CInstance *find_target(CInstance *s, int *out_id);
static float facing(CInstance *s) { return sget(s, &g_VAR_image_xscale) < 0 ? -1.0f : 1.0f; }
static void start_skill1(CInstance *s, Jeff *j);
static void start_skill2(CInstance *s, Jeff *j);

static void show(CInstance *s, int a, float frame) {
    bset(s, &g_VAR_sprite_index, g_jeff_spr[a]);
    bset(s, &g_VAR_image_index, frame);
    bset(s, &g_VAR_image_speed, 0);
}
static void fx_at(Jeff *j, int a, float x, float y, float xs, float ys, float rot, int tpf, int add) {
    int best = 0;
    for (int i = 0; i < N_JFX; i++) { if (!j->fx[i].on) { best = i; break; } if (j->fx[i].t > j->fx[best].t) best = i; }
    JFx *f = &j->fx[best];
    f->on = 1; f->t = 0; f->a = a; f->tpf = tpf; f->n = k_sprites[a].frames; f->add = add; f->col = C_WHITE;
    f->x = x; f->y = y; f->xs = xs; f->ys = ys; f->rot = rot;
}
/* the same, tinted (the grey shock rings take the colour of the power) */
static void fx_tint(Jeff *j, int a, float x, float y, float xs, float ys, int tpf, int col) {
    fx_at(j, a, x, y, xs, ys, 0, tpf, 0);
    for (int i = 0; i < N_JFX; i++) if (j->fx[i].on && j->fx[i].t == 0 && j->fx[i].a == a && j->fx[i].x == x) j->fx[i].col = col;
}

/* a small step-in so the blow connects (the CPU attacks from ~50 px away): only for an opponent
   close in front, at most 40 px over 6 frames, on top of the move's own push */
static void jeff_home(CInstance *s, Jeff *j) {
    int tid = -1;
    j->home_t = 0;
    if (!parent_ok(s)) return;
    CInstance *e = find_target(s, &tid);
    if (!e) return;
    float dx = (float)(sget(e, &g_VAR_x) - sget(s, &g_VAR_x)), dy = (float)(sget(e, &g_VAR_y) - sget(s, &g_VAR_y));
    float adx = dx < 0 ? -dx : dx, ady = dy < 0 ? -dy : dy;
    if (adx > 90 || ady > 60) return;                  /* only an opponent close in front: no long dashes */
    float dir = facing(s);
    if (dx * dir < 0) {
        if (adx > 30) return;                          /* turns only when he is right behind */
        dir = -dir;
        bset(s, &g_VAR_image_xscale, dir);
    }
    float gap = adx - 30;
    if (gap <= 1) return;
    if (gap > 40) gap = 40;
    j->home_dir = dir; j->home_v = gap / 6; j->home_t = 6;
}

static int red_combo(CInstance *s, CInstance *o, Jeff *j, int step, double dmg);
static void flip_power(CInstance *s, Jeff *j);
static void jeff_combo(CInstance *s, CInstance *o, int step) {
    Jeff *j = slot(s, true);
    if (j->move == MOVE_FLURRY) j->move = MOVE_NONE;       /* the next blow takes over */
    if (j->move == MOVE_SWITCH) {                          /* attacking mid-transformation finishes it */
        if (j->t < 12) flip_power(s, j);
        j->move = MOVE_NONE;
    }
    if ((step >= 1 && step <= 5) || (step >= 50 && step <= 53) || step == 10 || step == 60) jeff_home(s, j);
    bset(s, &g_VAR_image_speed, 0.3);
    iset_b(s, &g_VAR_combo_nextcombo, false);
    double dmg = parent_ok(s) ? pget(s, &g_VAR_plr_dmg) : 40;
    j->dir = facing(s);
    float x = sx_(s), y = sy_(s), d = j->dir;
    if (j->power && red_combo(s, o, j, step, dmg)) return;
    switch (step) {
    /* --- attack A: dark flame punches ------------------------------------------------- */
    case 1:                                            /* JAB */
        iset(s, &g_VAR_combo_next, 2);
        combo_normal(s, o, g_jeff_spr[A_JAB], SPR_MASK16, 20, -27, 3, 3, -3, dmg * 0.85, 5, false, 12, 1, SPR_HIT_1, C_FLAME);
        play(s, SND_WOOSH1, 1.15);
        break;
    case 2:                                            /* CROSS */
        iset(s, &g_VAR_combo_next, 3);
        combo_normal(s, o, g_jeff_spr[A_CROSS], SPR_MASK16, 23, -27, 4, 4, -3, dmg * 1.0, 5, false, 13, 1, SPR_HIT_1, C_FLAME);
        play(s, SND_WOOSH2, 1.05);
        break;
    case 3:                                            /* HOOK */
        iset(s, &g_VAR_combo_next, 4);
        combo_normal(s, o, g_jeff_spr[A_HOOK], SPR_MASK24, 22, -31, 3, 6, -4, dmg * 1.15, 6, false, 15, 1, SPR_HIT_3, C_FLAME);
        play(s, SND_WOOSH3, 0.95);
        break;
    case 4:                                            /* FLAME FLURRY: a burst of burning punches */
        iset(s, &g_VAR_combo_next, 5);
        j->move = MOVE_FLURRY; j->t = 0;
        show(s, A_FLURRY, 0);
        bset_i(s, &g_VAR_alarm, 2, 26);
        play_custom(s, S_FLAME, 1.1);
        break;
    case 5:                                            /* UPPERCUT - launches */
        iset(s, &g_VAR_combo_next, -1);
        combo_normal(s, o, g_jeff_spr[A_UPPERCUT], SPR_MASK24, 16, -38, 2, 7, -12, dmg * 1.6, 7, true, 24, 2, SPR_HIT_3, C_FLAME);
        play(s, SND_STRONG2, 1.0);
        if (parent_ok(s) && pget(s, &g_VAR_is_onair) < 0.5) bset(s, &g_VAR_vspeed, -3.2);
        fx_at(j, A_JF_BURST, x + d * 18, y - 46, 0.7f, 0.7f, 0, 1, 0);
        camera_shake(1);
        break;
    /* --- attack B: blue flame kicks ---------------------------------------------------- */
    case 50:                                           /* FRONT KICK */
        iset(s, &g_VAR_combo_next, 51);
        combo_normal(s, o, g_jeff_spr[A_KICK1], SPR_MASK24, 26, -24, 4, 5, -3, dmg * 0.95, 6, false, 14, 1, SPR_HIT_1, C_FLAME);
        fx_at(j, A_JF_ARC, x + d * 6, y - 24, d, 0.8f, d * -50, 2, 0);
        play(s, SND_WOOSH2, 1.1);
        break;
    case 51:                                           /* ROUNDHOUSE */
        iset(s, &g_VAR_combo_next, 52);
        combo_normal(s, o, g_jeff_spr[A_KICK2], SPR_MASK24, 26, -40, 3, 6, -4, dmg * 1.05, 6, false, 15, 1, SPR_HIT_1, C_FLAME);
        fx_at(j, A_JF_ARC, x + d * 4, y - 36, d, 1, d * -10, 2, 0);
        play(s, SND_WOOSH3, 1.05);
        break;
    case 52:                                           /* SPINNING BACK KICK */
        iset(s, &g_VAR_combo_next, 53);
        combo_normal(s, o, g_jeff_spr[A_KICK3], SPR_MASK32, 28, -32, 4, 7, -5, dmg * 1.15, 7, false, 18, 1, SPR_HIT_3, C_FLAME);
        fx_at(j, A_JF_ARC, x, y - 32, -d, 1, d * 20, 2, 0);
        play(s, SND_WOOSH3, 0.9);
        break;
    case 53:                                           /* AXE KICK - heel comes down in flame (knockdown) */
        iset(s, &g_VAR_combo_next, -1);
        combo_normal(s, o, g_jeff_spr[A_KICK4], SPR_MASK32, 26, -18, 2, 6, 5, dmg * 1.6, 8, true, 26, 2, SPR_HIT_3, C_FLAME);
        fx_at(j, A_JF_ARC, x + d * 14, y - 34, d, 1, d * -80, 2, 0);
        play(s, SND_STRONG2, 0.85);
        break;
    /* --- crouch / air ---------------------------------------------------------------- */
    case 10:                                           /* crouching jab */
        iset(s, &g_VAR_combo_next, -1);
        combo_normal(s, o, g_jeff_spr[A_CROUCHPUNCH], SPR_MASK16, 21, -12, 2, 4, -2, dmg * 0.9, 5, false, 14, 1, SPR_HIT_1, C_FLAME);
        play(s, SND_WOOSH1, 1.2);
        break;
    case 60:                                           /* flame sweep (trips) */
        iset(s, &g_VAR_combo_next, -1);
        combo_normal(s, o, g_jeff_spr[A_CROUCHKICK], SPR_MASK24, 28, -8, 3, 4, -3, dmg * 0.95, 6, true, 16, 1, SPR_HIT_1, C_FLAME);
        fx_at(j, A_JF_ARC, x + d * 10, y - 6, d, 0.45f, d * -70, 2, 0);
        play(s, SND_WOOSH2, 1.2);
        break;
    case 11:                                           /* air punch */
        iset(s, &g_VAR_combo_next, -1);
        combo_normal(s, o, g_jeff_spr[A_AIRPUNCH], SPR_MASK16, 18, -20, 0, 4, 3, dmg * 1.0, 5, false, 16, 1, SPR_HIT_1, C_FLAME);
        play(s, SND_WOOSH2, 1.1);
        break;
    case 61:                                           /* diving flame kick */
        iset(s, &g_VAR_combo_next, -1);
        combo_normal(s, o, g_jeff_spr[A_AIRKICK], SPR_MASK24, 22, -8, 0, 5, 5, dmg * 1.1, 6, false, 16, 1, SPR_HIT_1, C_FLAME);
        bset(s, &g_VAR_vspeed, 5); bset(s, &g_VAR_hspeed, d * 4);
        play(s, SND_WOOSH3, 1.2);
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
    Jeff *j = slot(s, true);
    if (j->move == MOVE_FLURRY) j->move = MOVE_NONE;
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

static void flurry_step(CInstance *s, Jeff *j) {
    int t = ++j->t;
    show(s, A_FLURRY, (float)((t / 3) % 4));
    bset(s, &g_VAR_hspeed, t < 20 ? j->dir * 1.1 : 0);
    if (t % 4 == 2 && t < 22 && parent_ok(s)) {
        float y = sy_(s) - 28 + ((t / 4) % 2 ? -5 : 4);
        Hit h = { pget(s, &g_VAR_plr_dmg) * 0.3, j->dir * 1.6, -1, 10, 4, 1.3, 1.2, SPR_MASK24, 1, 0, 1, 0, SPR_HIT_1, C_FLAME, 1 };
        spawn_hit(s, sx_(s) + j->dir * 28, y, &h);
        play(s, (t / 4) % 2 ? SND_WOOSH1 : SND_WOOSH2, 1.3);
    }
    if (t >= 26) j->move = MOVE_NONE;
}

/* ------------------------------------------------------------------------------------------ */
/* skill 1 - Meteor Shower: black holes open in the sky and rain flaming meteors              */
/* ------------------------------------------------------------------------------------------ */
static void start_skill1(CInstance *s, Jeff *j) {
    j->move = MOVE_SKILL1; j->t = 0; j->dir = facing(s); j->ground_y = sy_(s);
    iset(s, &g_VAR_combo_next, -1);
    bset_i(s, &g_VAR_alarm, 2, 72);
    show(s, A_METEOR, 0);
    bset(s, &g_VAR_hspeed, 0);
    play(s, SND_MAGICSTUN_CAST, 0.8);
}
static void skill1_step(CInstance *s, Jeff *j) {
    int t = ++j->t;
    show(s, A_METEOR, (float)(t < 10 ? 0 : t < 16 ? 1 : t < 56 ? 2 : 3));
    bset(s, &g_VAR_hspeed, 0);
    if (t == 14) {
        float x = sx_(s), y = sy_(s);
        for (int k = 0; k < 3; k++) { j->portal_x[k] = x + j->dir * (70 + 85 * k); j->portal_y[k] = y - 150 - 14 * (k % 2); }
        j->portals_on = 1; j->portals_t = 0;
        play_custom(s, S_HOLE, 1.25);
        camera_shake(1);
    }
    if (t >= 18 && t <= 62 && t % 4 == 2) {
        int k = (t / 4) % 3;
        for (int i = 0; i < N_MET; i++) if (!j->met[i].on) {
            Meteor *m = &j->met[i];
            m->on = 1; m->t = 0;
            m->x = j->portal_x[k] + frand(-18, 18); m->y = j->portal_y[k] + 6;
            m->vx = j->dir * frand(1.8f, 3.6f); m->vy = frand(4.5f, 6.0f);
            break;
        }
        if (t % 12 == 2) play(s, SND_WOOSH3, 0.7);
    }
    if (t >= 72) { j->move = MOVE_NONE; bset(s, &g_VAR_image_speed, 0.3); }
}
static void meteors_step(CInstance *s, Jeff *j) {
    if (j->portals_on && ++j->portals_t > 72) j->portals_on = 0;
    for (int i = 0; i < N_MET; i++) {
        Meteor *m = &j->met[i];
        if (!m->on) continue;
        m->t++; m->vy += 0.2f; m->x += m->vx; m->y += m->vy;
        if (m->y < j->ground_y - 2 && m->t <= 90) continue;
        m->on = 0;                                    /* impact */
        float gx = m->x, gy = j->ground_y;
        if (parent_ok(s)) {
            Hit h = { pget(s, &g_VAR_plr_dmg) * 0.42, m->vx > 0 ? 3.0 : -3.0, -4.5, 16, 5, 1.6, 1.4, SPR_MASK32, 1, 0, 1, 0, SPR_HIT_3, C_FLAME, 1 };
            spawn_hit(s, gx, gy - 14, &h);
        }
        fx_at(j, A_JF_CRATER, gx, gy, 1, 1, 0, 2, 0);
        fx_at(j, A_JF_BURST, gx, gy - 10, 0.6f, 0.6f, 0, 1, 0);
        camera_shake(1);
        play_custom(s, S_METEOR, frand(0.9f, 1.15f));
    }
}

/* ------------------------------------------------------------------------------------------ */
/* skill 2 - Abyss Palm: a black hole that drags the opponent in, then his punch detonates it */
/* ------------------------------------------------------------------------------------------ */
static void start_skill2(CInstance *s, Jeff *j) {
    j->move = MOVE_SKILL2; j->t = 0; j->dir = facing(s);
    iset(s, &g_VAR_combo_next, -1);
    bset_i(s, &g_VAR_alarm, 2, 70);
    show(s, A_ABYSS, 0);
    bset(s, &g_VAR_hspeed, 0);
    play(s, SND_MAGIC3, 0.7);
}
static void hole_detonate(CInstance *s, Jeff *j) {
    if (parent_ok(s)) {
        Hit h = { pget(s, &g_VAR_plr_dmg) * 1.5, j->dir * 9.0, -8.0, 30, 7, 2.0, 2.0, SPR_MASK64, 1, 1, 1, 1, SPR_HIT_3, C_FLAME, 2 };
        spawn_hit(s, j->bh_x, j->bh_y, &h);
    }
    fx_at(j, A_JF_BURST, j->bh_x, j->bh_y, 1.3f, 1.3f, 0, 2, 0);
    j->bh_on = 0;
    camera_shake(4);
    play(s, SND_DARKEXPLOSION, 1.0);
}
static void skill2_step(CInstance *s, Jeff *j) {
    int t = ++j->t;
    show(s, A_ABYSS, (float)(t < 8 ? 0 : t < 50 ? 1 + ((t / 4) % 2) : 3));
    bset(s, &g_VAR_hspeed, (t >= 50 && t < 54) ? j->dir * 3.5 : 0);
    if (t == 10) {
        j->bh_on = 1; j->bh_t = 0;
        j->bh_x = sx_(s) + j->dir * 74; j->bh_y = sy_(s) - 34;
        play_custom(s, S_HOLE, 1.0);
        camera_shake(2);
    }
    if (t == 52 && j->bh_on) hole_detonate(s, j);
    if (t >= 70) { j->move = MOVE_NONE; bset(s, &g_VAR_image_speed, 0.3); }
}
/* drag every opponent near the hole toward it */
static void pull_toward(CInstance *s, float hx, float hy) {
    RValue me = rv_undef();
    YYGML_Variable_GetValue(parent_of(s), g_VAR_plr_team.id, ARRAY_INDEX_NONE, &me, false, false);
    double my_team = rv_num(&me); rv_free(&me);
    RValue n = rv_undef(); RValue a = rv_real(OBJ_PARENT_CHARACTER);
    F_InstanceNumber(&n, s, s, 1, &a);
    int cnt = (int)rv_num(&n); rv_free(&n);
    for (int i = 0; i < cnt && i < 16; i++) {
        RValue id = rv_undef(); RValue fa[2] = { rv_real(OBJ_PARENT_CHARACTER), rv_real(i) };
        F_InstanceFind(&id, s, s, 2, fa);
        int iid = INT32_RValue(&id);
        rv_free(&id);
        CInstance *c = YYGML_FindInstance(iid);
        if (!c || c == s) continue;
        RValue cp = rv_undef(); RValue cid = rv_real(iid);
        YYGML_Variable_GetValue(&cid, g_VAR_parent.id, ARRAY_INDEX_NONE, &cp, false, false);
        bool ok = inst_exists_rv(s, &cp);
        double team = ok ? get_rv(&cp, &g_VAR_plr_team, ARRAY_INDEX_NONE) : my_team;
        rv_free(&cp);
        if (!ok || team == my_team) continue;
        float ex = (float)sget(c, &g_VAR_x), ey = (float)sget(c, &g_VAR_y) - 30;
        float dx = hx - ex, dy = hy - ey;
        if (fabsf_(dx) > 150 || fabsf_(dy) > 100) continue;
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
static void hole_step(CInstance *s, Jeff *j) {
    if (!j->bh_on) return;
    int t = ++j->bh_t;
    if (parent_ok(s)) {
        pull_toward(s, j->bh_x, j->bh_y);
        if (t % 8 == 4) {
            Hit h = { pget(s, &g_VAR_plr_dmg) * 0.18, 0, -1, 12, 3, 1.4, 1.4, SPR_MASK64, 1, 0, 1, 0, SPR_HIT_5, C_FLAME, 1 };
            spawn_hit(s, j->bh_x, j->bh_y, &h);
        }
    }
    if (t > 70) hole_detonate(s, j);                   /* he was interrupted: it collapses by itself */
}

/* ------------------------------------------------------------------------------------------ */
/* the burning fists / feet                                                                    */
/* ------------------------------------------------------------------------------------------ */
static const JeffFrame *jeff_frame(CInstance *s, int *anim) {
    int sp = (int)sget(s, &g_VAR_sprite_index);
    for (int a = 0; a < A_COUNT; a++)
        if (k_jeff_meta_first[a] >= 0 && g_jeff_spr[a] == sp) {
            int f = (int)sget(s, &g_VAR_image_index), n = k_sprites[a].frames;
            if (f < 0) f = 0;
            if (anim) *anim = a;
            return &k_jeff_meta[k_jeff_meta_first[a] + f % n];
        }
    return 0;
}
static void jfx_step(Jeff *j) {
    for (int i = 0; i < N_JFX; i++) if (j->fx[i].on && ++j->fx[i].t >= j->fx[i].n * j->fx[i].tpf) j->fx[i].on = 0;
}
/* each time a new burning frame starts: the flame flares where the blow lands */
static void limb_step(CInstance *s, Jeff *j) {
    int anim = -1;
    const JeffFrame *m = jeff_frame(s, &anim);
    if (!m || !(m->hot & 7)) { j->last_hot = -1; return; }
    int key = (int)(m - k_jeff_meta);
    if (key == j->last_hot) return;
    j->last_hot = key;
    float x = sx_(s), y = sy_(s), xs = facing(s);
    float px = x + xs * (m->hot & 4 ? m->kx : m->hot & 1 ? m->fx : m->bx);
    float py = y + (m->hot & 4 ? m->ky : m->hot & 1 ? m->fy : m->by);
    if (j->power && !(m->hot & 4) && (m->hot & 1)) {   /* the sun sword: sparks fly off the blade */
        float an = m->fa * 0.0174533f;
        px += xs * SWORD_LEN * 0.7f * cosf_(an); py += SWORD_LEN * 0.7f * sinf_(an);
    }
    fx_at(j, j->power ? A_JS_BURST : A_JF_BURST, px + xs * 6, py, 0.4f, 0.4f, 0, 1, 0);
    if (anim == A_KICK4 && m->ky > -12) {             /* the axe kick's heel hits the ground */
        fx_at(j, A_JF_CRATER, px, y, 0.8f, 0.8f, 0, 2, 0);
        camera_shake(2);
    }
    if (anim == A_RB4 && m->by > -16) {               /* the sun slam: the shield hits the ground */
        fx_at(j, A_JS_BURST, px, y - 8, 0.9f, 0.7f, 0, 1, 0);
        fx_tint(j, A_CIN_RING, px, y, 0.45f, 0.45f, 2, C_SUN);
        camera_shake(3);
    }
    play_custom(s, S_FLAME, 0.9 + frand(0, 0.3f));
}

/* ------------------------------------------------------------------------------------------ */
/* red power: the sun                                                                          */
/* ------------------------------------------------------------------------------------------ */
static void pin_target(CInstance *s, Jeff *j);
static void release_target(CInstance *s, Jeff *j);
static void start_special(CInstance *s, Jeff *j);
static bool is_cpu(CInstance *s) { return parent_ok(s) && pget(s, &g_VAR_plr_controller) == 2; }

static void set_power_sprites(CInstance *s, Jeff *j) {
    iset(s, &g_VAR_spr_stand, g_jeff_spr[j->power ? A_RSTAND : A_STAND]);
    iset(s, &g_VAR_spr_defend, g_jeff_spr[j->power ? A_RDEFEND : A_DEFEND]);
}
static void flip_power(CInstance *s, Jeff *j) {
    j->power ^= 1;
    set_power_sprites(s, j);
    int face = g_jeff_spr[j->power ? A_FACE_D : A_FACE];   /* the HUD portrait changes with him */
    if (face >= 0 && parent_ok(s)) pset(s, &g_VAR_spr_face, face);
    fx_at(j, j->power ? A_JS_BURST : A_JF_BURST, sx_(s), sy_(s) - 30, 1.1f, 1.1f, 0, 1, 0);
    camera_shake(2);
}
/* the transformation: blue fire spins up round him, turns red and bursts (or back again) */
static void start_switch(CInstance *s, Jeff *j) {
    j->move = MOVE_SWITCH; j->t = 0;
    j->sw_cool = is_cpu(s) ? 600 : 30;
    show(s, A_POWER, 0);
    bset(s, &g_VAR_hspeed, 0);
    if (j->power) fx_at(j, A_JF_AURA, sx_(s), sy_(s) + 2, 1, 1, 0, 3, 0);     /* the sun goes out, blue fire returns */
    else fx_at(j, A_JS_SWIRL, sx_(s), sy_(s) + 2, 1, 1, 0, 2, 0);             /* blue fire spins up and turns to sun */
    play_custom(s, S_POWER, j->power ? 0.85 : 1.0);
}
static void switch_step(CInstance *s, Jeff *j) {
    int t = ++j->t;
    show(s, A_POWER, (float)(t < 10 ? 0 : t < 18 ? 1 : 2));
    bset(s, &g_VAR_hspeed, 0);
    if (t == 12) flip_power(s, j);
    if (t >= 26) { j->move = MOVE_NONE; bset(s, &g_VAR_image_speed, 0.3); }
}

static void start_rskill1(CInstance *s, Jeff *j);
static void start_rskill2(CInstance *s, Jeff *j);
/* the red combos: attack A = the sun sword, attack B = the sun shield (1 if handled) */
static int red_combo(CInstance *s, CInstance *o, Jeff *j, int step, double dmg) {
    float x = sx_(s), y = sy_(s), d = j->dir;
    switch (step) {
    case 1:                                            /* slash */
        iset(s, &g_VAR_combo_next, 2);
        combo_normal(s, o, g_jeff_spr[A_RS1], SPR_MASK32, 26, -30, 3, 4, -3, dmg * 0.95, 6, false, 13, 1, SPR_HIT_3, C_SUN);
        fx_at(j, A_JS_ARC, x + d * 8, y - 30, d, 0.8f, d * -10, 2, 0);
        play(s, SND_WOOSH2, 1.05);
        return 1;
    case 2:                                            /* rising slash */
        iset(s, &g_VAR_combo_next, 3);
        combo_normal(s, o, g_jeff_spr[A_RS2], SPR_MASK32, 24, -40, 2, 3, -6, dmg * 1.0, 6, false, 13, 1, SPR_HIT_3, C_SUN);
        fx_at(j, A_JS_ARC, x + d * 10, y - 34, d, 0.8f, d * -70, 2, 0);
        play(s, SND_WOOSH3, 1.1);
        return 1;
    case 3:                                            /* thrust */
        iset(s, &g_VAR_combo_next, 4);
        combo_normal(s, o, g_jeff_spr[A_RS3], SPR_MASK32, 34, -28, 5, 6, -2, dmg * 1.15, 6, false, 15, 1, SPR_HIT_3, C_SUN);
        fx_at(j, A_JS_TRAIL, x + d * 58, y - 30, d * 0.9f, 0.9f, 0, 1, 0);
        play(s, SND_WOOSH1, 0.9);
        return 1;
    case 4:                                            /* spin slash */
        iset(s, &g_VAR_combo_next, 5);
        combo_normal(s, o, g_jeff_spr[A_RS4], SPR_MASK32, 26, -30, 3, 5, -4, dmg * 1.1, 7, false, 16, 1, SPR_HIT_3, C_SUN);
        fx_at(j, A_JS_ARC, x, y - 30, -d, 1.1f, d * 30, 2, 0);
        fx_at(j, A_JS_ARC, x + d * 6, y - 30, d, 1.0f, d * -20, 2, 0);
        play(s, SND_WOOSH3, 0.95);
        return 1;
    case 5:                                            /* solar cleave: the sun comes down (knockdown) */
        iset(s, &g_VAR_combo_next, -1);
        combo_normal(s, o, g_jeff_spr[A_RS5], SPR_MASK64, 26, -30, 2, 8, -10, dmg * 1.7, 8, true, 26, 2, SPR_HIT_3, C_SUN);
        fx_at(j, A_JS_ARC, x + d * 12, y - 40, d, 1.2f, d * -80, 2, 0);
        play(s, SND_STRONG2, 0.9);
        return 1;
    case 50:                                           /* shield bash */
        iset(s, &g_VAR_combo_next, 51);
        combo_normal(s, o, g_jeff_spr[A_RB1], SPR_MASK32, 22, -28, 5, 7, -3, dmg * 0.95, 6, false, 14, 1, SPR_HIT_3, C_SUN);
        play(s, SND_STRONG1, 1.1);
        return 1;
    case 51:                                           /* shield uppercut - launches */
        iset(s, &g_VAR_combo_next, 52);
        combo_normal(s, o, g_jeff_spr[A_RB2], SPR_MASK32, 20, -36, 2, 3, -9, dmg * 1.05, 6, false, 15, 1, SPR_HIT_3, C_SUN);
        play(s, SND_WOOSH2, 0.9);
        return 1;
    case 52:                                           /* shield charge */
        iset(s, &g_VAR_combo_next, 53);
        combo_normal(s, o, g_jeff_spr[A_RB3], SPR_MASK32, 24, -28, 8, 8, -3, dmg * 1.1, 8, false, 18, 1, SPR_HIT_3, C_SUN);
        fx_at(j, A_JS_TRAIL, x + d * 30, y - 28, d, 1.2f, 0, 1, 0);
        play(s, SND_WOOSH3, 0.8);
        return 1;
    case 53:                                           /* sun slam: shield driven into the ground (knockdown) */
        iset(s, &g_VAR_combo_next, -1);
        combo_normal(s, o, g_jeff_spr[A_RB4], SPR_MASK64, 20, -12, 2, 6, -7, dmg * 1.6, 8, true, 28, 2, SPR_HIT_3, C_SUN);
        play(s, SND_STRONG2, 0.8);
        return 1;
    case 100: start_rskill1(s, j); return 1;
    case 110: start_rskill2(s, j); return 1;
    }
    return 0;
}

/* red skill 1 - Solar Flare: the sword sends a crescent of sun fire across the screen */
static void start_rskill1(CInstance *s, Jeff *j) {
    j->move = MOVE_RSKILL1; j->t = 0; j->dir = facing(s);
    iset(s, &g_VAR_combo_next, -1);
    bset_i(s, &g_VAR_alarm, 2, 48);
    show(s, A_METEOR, 1);
    bset(s, &g_VAR_hspeed, 0);
    play(s, SND_MAGICSTUN_CAST, 1.1);
}
static void rskill1_step(CInstance *s, Jeff *j) {
    int t = ++j->t;
    show(s, A_METEOR, (float)(t < 8 ? 1 : t < 18 ? 2 : 3));
    bset(s, &g_VAR_hspeed, 0);
    if (t == 18) {
        j->wave_on = 1; j->wave_t = 0; j->wave_hits = 0; j->wave_dir = j->dir;
        j->wave_x = sx_(s) + j->dir * 30; j->wave_y = sy_(s) - 34;
        play_custom(s, S_FLAME, 0.8);
        camera_shake(1);
    }
    if (t >= 48) { j->move = MOVE_NONE; bset(s, &g_VAR_image_speed, 0.3); }
}
static void wave_step(CInstance *s, Jeff *j) {
    if (!j->wave_on) return;
    int t = ++j->wave_t;
    j->wave_x += j->wave_dir * 7.5f;
    if (t % 6 == 3 && j->wave_hits < 5 && parent_ok(s)) {
        Hit h = { pget(s, &g_VAR_plr_dmg) * 0.32, j->wave_dir * 3.0, -2, 12, 4, 1.2, 2.0, SPR_MASK32, 1, 0, 1, 0, SPR_HIT_3, C_SUN, 1 };
        spawn_hit(s, j->wave_x, j->wave_y, &h);
        j->wave_hits++;
    }
    if (t >= 40) { fx_at(j, A_JS_BURST, j->wave_x, j->wave_y, 0.8f, 0.8f, 0, 1, 0); j->wave_on = 0; }
}
/* red skill 2 - Corona: the sun on his shield flares and blasts everything around him away */
static void start_rskill2(CInstance *s, Jeff *j) {
    j->move = MOVE_RSKILL2; j->t = 0; j->dir = facing(s);
    iset(s, &g_VAR_combo_next, -1);
    bset_i(s, &g_VAR_alarm, 2, 46);
    show(s, A_ABYSS, 0);
    bset(s, &g_VAR_hspeed, 0);
    play(s, SND_MAGIC3, 1.2);
}
static void rskill2_step(CInstance *s, Jeff *j) {
    int t = ++j->t;
    show(s, A_ABYSS, (float)(t < 8 ? 0 : t < 30 ? 1 + ((t / 4) % 2) : 3));
    bset(s, &g_VAR_hspeed, 0);
    float x = sx_(s), y = sy_(s);
    if (t == 12) {
        fx_at(j, A_JS_BURST, x, y - 30, 1.7f, 1.7f, 0, 1, 0);
        if (parent_ok(s)) {
            for (int k = -1; k <= 1; k += 2) {
                Hit h = { pget(s, &g_VAR_plr_dmg) * 1.2, k * 8.0, -7.0, 28, 6, 1.6, 1.8, SPR_MASK64, 1, 1, 1, 1, SPR_HIT_3, C_SUN, 2 };
                spawn_hit(s, x + k * 34, y - 30, &h);
            }
        }
        camera_shake(3);
        play(s, SND_EXPLOSION_MEGA, 1.2);
    }
    if (t == 12 || t == 16 || t == 20) fx_tint(j, A_CIN_RING, x, y, 0.6f + (t - 12) * 0.08f, 0.6f, 2, C_SUN);
    if (t >= 46) { j->move = MOVE_NONE; bset(s, &g_VAR_image_speed, 0.3); }
}

/* ------------------------------------------------------------------------------------------ */
/* cinematics: RED BLACK HOLE (double-tap skill) and HOLLOW PURPLE (double-tap shield + skill) */
/* ------------------------------------------------------------------------------------------ */
static double bar_need(CInstance *s) {
    double emax = pget(s, &g_VAR_plr_maxenergy);
    return emax > 0 ? (emax < 100 ? emax : 100) : 100;
}
static bool full_bar(CInstance *s) { return parent_ok(s) && pget(s, &g_VAR_plr_energy) + 0.001 >= bar_need(s); }

float scyther_sprite_scale(int sprite_id);
static void start_cinematic(CInstance *s, Jeff *j, int kind) {
    int tid = -1;
    CInstance *t = find_target(s, &tid);
    pset_b(s, &g_VAR_keyp_special, false);
    if (!full_bar(s) || !t) { j->fail_t = 24; play(s, SND_WOOSH3, 0.6); return; }
    pset(s, &g_VAR_plr_energy, pget(s, &g_VAR_plr_energy) - bar_need(s));
    j->move = MOVE_CIN; j->cin = kind; j->t = 0; j->cin_done = 0;
    j->tgt_id = tid; j->tgt_x = (float)sget(t, &g_VAR_x); j->tgt_y = (float)sget(t, &g_VAR_y); j->start_x = sx_(s);
    j->dir = j->tgt_x >= sx_(s) ? 1.0f : -1.0f;
    bset(s, &g_VAR_image_xscale, j->dir);
    j->cin_spr = (int)sget(t, &g_VAR_sprite_index); j->cin_img = (float)sget(t, &g_VAR_image_index);
    j->cin_vk = scyther_sprite_scale(j->cin_spr);         /* Scyther's sprites are 2x density */
    pset_b(s, &g_VAR_is_attacking, true);
    pset_b(s, &g_VAR_can_gethurt, false);               /* untouchable during the cinematic */
    iset(s, &g_VAR_combo_next, -1);
    bset_i(s, &g_VAR_alarm, 2, -1);
    j->old_depth = sget(s, &g_VAR_depth); j->depth_saved = 1;
    bset(s, &g_VAR_depth, -15000);                       /* the GUI cinematic draws over the HUD */
    bset(s, &g_VAR_hspeed, 0); bset(s, &g_VAR_vspeed, 0);
    show(s, kind == CIN_PURPLE ? A_PURPLE : A_METEOR, kind == CIN_PURPLE ? 0 : 1);
    play(s, SND_SUSPENSE, 1.0);
    play_custom(s, kind == CIN_PURPLE ? S_POWER : S_HOLE, kind == CIN_PURPLE ? 0.8 : 0.7);
}
/* the blow that ends it: K.O. */
static void cin_finish(CInstance *s, Jeff *j) {
    CInstance *c = j->tgt_id >= 0 ? YYGML_FindInstance(j->tgt_id) : 0;
    release_target(s, j);
    j->cin_done = 1;
    if (!c) return;
    float cx = (float)sget(c, &g_VAR_x), cy = (float)sget(c, &g_VAR_y);
    Hit h = { 999999, j->dir * 12.0, -10.0, 40, 6, 2.0, 2.0, SPR_MASK64, 1, 1, 0, 1, SPR_HIT_3, j->cin == CIN_PURPLE ? C_PURPLE : C_SUN, 2 };
    spawn_hit(s, cx, cy - 24, &h);
    RValue cp = rv_undef(); RValue cid = rv_real(j->tgt_id);
    YYGML_Variable_GetValue(&cid, g_VAR_parent.id, ARRAY_INDEX_NONE, &cp, false, false);
    if (inst_exists_rv(s, &cp)) {
        RValue z = rv_real(0);
        YYGML_Variable_SetValue(&cp, g_VAR_plr_hp.id, ARRAY_INDEX_NONE, &z);
    }
    rv_free(&cp);
    /* what is left of the blast in the fight itself, seen as the cinematic fades */
    if (j->cin == CIN_PURPLE) fx_at(j, A_HP_NUKE, cx, cy, 0.7f, 0.7f, 0, 3, 0);
    else fx_at(j, A_JS_BURST, cx, cy - 30, 1.4f, 1.4f, 0, 2, 0);
    camera_shake(5);
}
static void cin_step(CInstance *s, Jeff *j) {
    int t = ++j->t;
    bset(s, &g_VAR_hspeed, 0); bset(s, &g_VAR_vspeed, 0);
    if (!j->cin_done) pin_target(s, j);
    int dur = j->cin == CIN_PURPLE ? CIN_PUR_DUR : CIN_RED_DUR, ko = j->cin == CIN_PURPLE ? CIN_PUR_KO : CIN_RED_KO;
    if (t >= dur - 12) show(s, A_POSE, 1);              /* he holds his pose as the fight comes back */
    else if (j->cin == CIN_PURPLE) {
        show(s, A_PURPLE, (float)(t < 40 ? 0 : t < 70 ? 1 : t < 96 ? 2 : 3));
        if (t == 72) play(s, SND_MAGIC3, 1.3);
        if (t == 80) play_custom(s, S_HOLE, 1.6);
        if (t == 96) play(s, SND_WOOSH3, 0.7);
        if (t == 106) { play_custom(s, S_NUKE, 1.0); play(s, SND_EXPLOSION_MEGA, 0.8); j->shake = 14; }
    } else {
        show(s, A_METEOR, (float)(t < 20 ? 1 : 2));
        if (t == 50) play(s, SND_THUNDER, 0.6);
        if (t == ko) { play_custom(s, S_NUKE, 1.3); play(s, SND_DARKEXPLOSION, 0.8); j->shake = 10; }
    }
    if (j->shake > 0) j->shake *= 0.92f;
    if (t == ko) play(s, SND_WINLOSE_IMPACT, 1.0);
    if (t == dur - 12) cin_finish(s, j);                /* the K.O. lands as the fight comes back */
    if (t >= dur) {
        if (!j->cin_done) cin_finish(s, j);
        if (j->depth_saved) { bset(s, &g_VAR_depth, j->old_depth); j->depth_saved = 0; }
        j->move = MOVE_NONE; j->cin = CIN_NONE;
        pset_b(s, &g_VAR_can_gethurt, true);
        bset(s, &g_VAR_image_speed, 0.3);
        bset_i(s, &g_VAR_alarm, 2, 1);
    }
}

/* the player's taps: double-tap shield = switch power; with a full bar a skill tap waits a moment -
   a second skill tap = RED BLACK HOLE, a second tap with a shield double tap = HOLLOW PURPLE, one
   tap with the shield held = Bone Breaker, one tap alone = the normal skill (handed back to the game) */
static void input_step(CInstance *s, Jeff *j) {
    int now = j->aura_t;
    bool def = pget(s, &g_VAR_key_defend) > 0.5;
    if (def && !j->prev_def) {
        j->def_t2 = j->def_t1; j->def_t1 = now;
        if (j->def_t2 > 0 && now - j->def_t2 <= TAP_WINDOW && j->sw_cool == 0) { j->sw_pending = 1; j->sw_pending_t = now; }
    }
    j->prev_def = def;
    bool free_ = j->move == MOVE_NONE && pget(s, &g_VAR_is_hurt) < 0.5 && pget(s, &g_VAR_is_fallen) < 0.5;
    bool tap = !is_cpu(s) && pget(s, &g_VAR_keyp_special) > 0.5;
    if (j->sk_pending == 2) {                           /* both skill taps in: is the shield's second tap coming? */
        if (tap) pset_b(s, &g_VAR_keyp_special, false);
        if (j->sw_pending) { j->sk_pending = 0; j->sw_pending = 0; start_cinematic(s, j, CIN_PURPLE); }
        else if (now - j->sk_t1 > 8) { j->sk_pending = 0; start_cinematic(s, j, CIN_REDHOLE); }
        return;
    }
    if (tap && free_ && full_bar(s) && pget(s, &g_VAR_is_onair) < 0.5) {
        pset_b(s, &g_VAR_keyp_special, false);            /* hold the tap back for a moment */
        if (j->sk_pending && now - j->sk_t1 <= TAP_WINDOW) {
            bool dbl = j->sw_pending || (j->def_t2 > 0 && j->def_t1 - j->def_t2 <= TAP_WINDOW && now - j->def_t1 <= 20);
            if (!dbl && (def || (j->def_t1 > 0 && now - j->def_t1 <= TAP_WINDOW))) { j->sk_pending = 2; j->sk_t1 = now; return; }
            j->sk_pending = 0; j->sw_pending = 0;
            start_cinematic(s, j, dbl ? CIN_PURPLE : CIN_REDHOLE);
            return;
        }
        j->sk_pending = 1; j->sk_t1 = now; j->sk_pending_def = def;
        j->sk_pending_down = pget(s, &g_VAR_key_down) > 0.5;
        return;
    }
    if (j->sk_pending && now - j->sk_t1 > TAP_WINDOW) {   /* just one tap */
        j->sk_pending = 0; j->sw_pending = 0;
        if (!free_) return;                              /* he was hit meanwhile: the tap is lost */
        if (j->sk_pending_def) start_special(s, j);       /* shield + skill: Bone Breaker */
        else {                                           /* the normal skill: the game's framework sees the tap now */
            pset_b(s, &g_VAR_keyp_special, true);
            if (j->sk_pending_down) pset_b(s, &g_VAR_key_down, true);
        }
        return;
    }
    if (j->sw_pending && !j->sk_pending && now - j->sw_pending_t > 10) {
        j->sw_pending = 0;
        if (free_) start_switch(s, j);
    }
}

/* ------------------------------------------------------------------------------------------ */
/* special - Bone Breaker                                                                      */
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
    j->move = MOVE_NONE; j->cin = CIN_NONE;
    if (parent_ok(s)) { pset_b(s, &g_VAR_can_gethurt, true); pset_b(s, &g_VAR_is_attacking, false); }
}
/* ------------------------------------------------------------------------------------------ */
/* step                                                                                        */
/* ------------------------------------------------------------------------------------------ */
void gml_Object_o_jeff_Step_0(CInstance *s, CInstance *o) {
    Jeff *j = slot(s, true);
    j->aura_t++;
    if (j->fail_t > 0) j->fail_t--;
    if (j->sw_cool > 0) j->sw_cool--;
    bool pok = parent_ok(s);

    if (j->move == MOVE_SPECIAL || j->move == MOVE_CIN) {   /* cutscenes run on their own */
        if (!pok) special_abort(s, j);
        else if (j->move == MOVE_SPECIAL) special_step(s, j);
        else cin_step(s, j);
        if (j->impact_on && ++j->impact_t >= 30) j->impact_on = 0;
        meteors_step(s, j); hole_step(s, j); wave_step(s, j); jfx_step(j);
        return;
    }
    if (pok) {
        input_step(s, j);
        if (j->move == MOVE_SPECIAL || j->move == MOVE_CIN) return;
    }
    if (pok && j->move == MOVE_NONE) {
        if (special_pressed(s)) start_special(s, j);
        else if (cpu_wants_special(s)) {                 /* the CPU picks one of his three finishers */
            int r = (int)(rnd() % 3u);
            if (r == 0) start_special(s, j);
            else start_cinematic(s, j, r == 1 ? CIN_REDHOLE : CIN_PURPLE);
        }
        if (j->move == MOVE_SPECIAL || j->move == MOVE_CIN) return;
    }

    RValue ret = rv_undef();
    gml_Script_scr_plr_step(s, o, &ret, 0, 0);          /* the game's movement / input framework */
    rv_free(&ret);
    if (j->home_t > 0) {                                /* homing lunge of the current blow */
        j->home_t--;
        if (pok && pget(s, &g_VAR_is_hurt) < 0.5) bset(s, &g_VAR_hspeed, sget(s, &g_VAR_hspeed) + j->home_dir * j->home_v);
        else j->home_t = 0;
    }

    if (pok && j->move != MOVE_NONE) {
        if (pget(s, &g_VAR_is_hurt) > 0.5 || pget(s, &g_VAR_is_fallen) > 0.5) j->move = MOVE_NONE;   /* interrupted */
        else switch (j->move) {
        case MOVE_SKILL1: skill1_step(s, j); break;
        case MOVE_SKILL2: skill2_step(s, j); break;
        case MOVE_FLURRY: flurry_step(s, j); break;
        case MOVE_SWITCH: switch_step(s, j); break;
        case MOVE_RSKILL1: rskill1_step(s, j); break;
        case MOVE_RSKILL2: rskill2_step(s, j); break;
        default: break;
        }
    }
    meteors_step(s, j);
    hole_step(s, j);
    wave_step(s, j);
    jfx_step(j);
    limb_step(s, j);
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
static int body_anim_of(int sp) {
    if (sp < 0) return -1;
    for (int a = 0; a < JEFF_BODY_N; a++) if (g_jeff_spr[a] == sp) return a;
    return -1;
}
static const JeffFrame *meta_of(int a, float img) {
    if (a < 0 || a >= JEFF_BODY_N || k_jeff_meta_first[a] < 0) return 0;
    int f = finite_(img) ? (int)img : 0, n = k_sprites[a].frames;
    if (f < 0) f = 0;
    return &k_jeff_meta[k_jeff_meta_first[a] + f % n];
}
/* part of one of our sprites (the transformation reveals the new form row by row) */
static void spr_part(CInstance *s, int a, float img, float l, float t, float w, float h, float x, float y,
                     float xs, float ys, int col, float alpha) {
    int id = g_jeff_spr[a];
    if (id < 0 || !finite_(x) || !finite_(y) || w < 1 || h < 1) return;
    RValue r = rv_undef();
    RValue v[12] = { rv_real(id), rv_real(img), rv_real(l), rv_real(t), rv_real(w), rv_real(h), rv_real(x), rv_real(y),
                     rv_real(xs), rv_real(ys), rv_real(col), rv_real(alpha) };
    F_DrawSpritePartExt(&r, s, s, 12, v);
    rv_free(&r);
}
/* the sun sword in his front hand (along the arm), the sun shield on his back hand; k = scale */
static void draw_sword(CInstance *s, Jeff *j, const JeffFrame *m, float x, float y, float f, float k, float alpha) {
    spr(s, A_JS_SWORD, (float)((j->aura_t / 3) % 6), x + f * m->fx * k, y + m->fy * k,
        f * SWORD_K * k, SWORD_K * k, -m->fa * f, C_WHITE, alpha);
}
static void draw_shield(CInstance *s, Jeff *j, const JeffFrame *m, float x, float y, float f, float k, float alpha) {
    spr(s, A_JS_SHIELD, (float)((j->aura_t / 3) % 8), x + f * m->bx * k, y + m->by * k,
        f * SHIELD_K * k, SHIELD_K * k, 0, C_WHITE, alpha);
}
/* the black form's eyes glow */
static void draw_eyes(CInstance *s, Jeff *j, const JeffFrame *m, float x, float y, float f, float k, float alpha) {
    if (!(m->flags & JF_EYES) || alpha <= 0.02f) return;
    float a = (0.5f + 0.12f * sinf_(j->aura_t * 0.21f)) * alpha;
    blend(s, 1);
    spr(s, A_JD_GLOW, 0, x + f * m->elx * k, y + m->ely * k, 0.62f * k, 0.62f * k, 0, C_EYE, a);
    spr(s, A_JD_GLOW, 0, x + f * m->erx * k, y + m->ery * k, 0.62f * k, 0.62f * k, 0, C_EYE, a);
    blend(s, 0);
}

void gml_Object_o_jeff_Draw_0(CInstance *s, CInstance *o) {
    (void)o;
    Jeff *j = slot(s, true);
    float x = sx_(s), y = sy_(s);
    float xs = (float)sget(s, &g_VAR_image_xscale);
    float f = xs < 0 ? -1.0f : 1.0f;
    bool pok = parent_ok(s);
    bool charging = pok && pget(s, &g_VAR_is_charging) > 0.5;
    bool red = j->power != 0;

    /* meteor shower: the black holes torn open in the sky */
    if (j->portals_on) {
        float a = j->portals_t < 10 ? j->portals_t / 10.0f : (j->portals_t > 60 ? (72 - j->portals_t) / 12.0f : 1.0f);
        if (a < 0) a = 0;
        for (int k = 0; k < 3; k++)
            spr(s, A_JF_PORTAL, (float)((j->portals_t / 3 + k) % 8), j->portal_x[k], j->portal_y[k], 0.45f + 0.35f * a, 0.45f + 0.35f * a, 0, C_WHITE, a);
    }
    /* black hole: the far half of its flame disk, behind Jeff */
    float g = 0;
    if (j->bh_on) {
        g = j->bh_t < 10 ? 0.3f + 0.7f * j->bh_t / 10.0f : 1.0f;
        spr(s, A_JF_BHRING_B, (float)((j->bh_t / 3) % 8), j->bh_x, j->bh_y, g * 0.75f, g * 0.75f, 0, C_WHITE, 1);
    }
    /* flame aura while charging or calling a skill (sun fire in the red form) */
    if (charging || j->move == MOVE_SKILL1 || j->move == MOVE_SKILL2 || j->move == MOVE_RSKILL1 || j->move == MOVE_RSKILL2)
        spr(s, red ? A_JS_AURA : A_JF_AURA, (float)((j->aura_t / 3) % 8), x, y + 2, f, 1, 0, C_WHITE, 0.9f);
    /* Corona: the sun on his shield swells before it flares */
    if (j->move == MOVE_RSKILL2 && j->t < 14) {
        blend(s, 1);
        spr(s, A_JS_GLOW, 0, x, y - 30, 0.5f + j->t * 0.1f, 0.5f + j->t * 0.1f, 0, C_WHITE, 0.8f);
        blend(s, 0);
    }

    int sp = (int)sget(s, &g_VAR_sprite_index);
    int a = body_anim_of(sp);
    float img = (float)sget(s, &g_VAR_image_index);
    const JeffFrame *m = meta_of(a, img);

    /* the transformation: the new form rises from his feet to the tips of his ears */
    bool base_dark = red, to_dark = false;
    float rise = -1;
    if (j->move == MOVE_SWITCH) {
        bool from_dark = j->t < 12 ? red : !red;
        base_dark = from_dark; to_dark = !from_dark;
        rise = (j->t - 4) / 16.0f;
        if (rise < 0) rise = 0;
        if (rise > 1) rise = 1;
    }
    float wa = red ? 1.0f : 0.0f;                         /* sword and shield fade in / out with it */
    if (rise >= 0) wa = to_dark ? rise : 1 - rise;
    float ea = base_dark ? 1.0f : 0.0f;                   /* the eyes light when the black reaches them */
    if (rise >= 0) ea = to_dark ? (rise - 0.8f) * 5 : (rise < 0.75f ? 1.0f : 0.0f);

    if (m && wa > 0.02f) {
        if (!(m->flags & JF_BOVER)) draw_shield(s, j, m, x, y, f, 1, wa);
        if (!(m->flags & JF_FOVER)) draw_sword(s, j, m, x, y, f, 1, wa);
    }
    if (a >= 0 && base_dark && g_jeff_spr[A_DARK0 + a] >= 0) {
        bset(s, &g_VAR_sprite_index, g_jeff_spr[A_DARK0 + a]);   /* the black copy, for this draw only */
        YYGML_draw_self(s);
        bset(s, &g_VAR_sprite_index, sp);
    } else {
        YYGML_draw_self(s);
    }
    if (a >= 0 && rise > 0) {
        float top = 72 - rise * 68;
        if (top < 0) top = 0;
        spr_part(s, to_dark ? A_DARK0 + a : a, img, 0, top, 96, 72 - top, x - 48 * f, y + top - 71, f, 1, C_WHITE, 1);
        if (rise < 1) {                                   /* a band of fire at the edge */
            float by = y + top - 71;
            int fl = to_dark ? A_JS_FIST : A_JF_FIST;
            for (int i = -1; i <= 1; i++)
                spr(s, fl, (float)((j->aura_t / 2 + i + 1) % 8), x + i * 10, by + 4, 0.42f, 0.42f, 90, C_WHITE, 1);
            blend(s, 1);
            spr(s, to_dark ? A_JS_GLOW : A_JF_GLOW, 0, x, by, 0.9f, 0.35f, 0, C_WHITE, 0.85f);
            blend(s, 0);
        }
    }
    if (m && wa > 0.02f) {
        if (m->flags & JF_BOVER) draw_shield(s, j, m, x, y, f, 1, wa);
        if (m->flags & JF_FOVER) draw_sword(s, j, m, x, y, f, 1, wa);
    }
    if (m && ea > 0.02f) draw_eyes(s, j, m, x, y, f, 1, ea > 1 ? 1 : ea);

    /* the burning blows of this frame */
    if (m && (m->hot & 7)) {
        for (int b = 0; b < 3; b++) {
            if (!(m->hot & (1 << b))) continue;
            float px = x + f * (b == 0 ? m->fx : b == 1 ? m->bx : m->kx);
            float py = y + (b == 0 ? m->fy : b == 1 ? m->by : m->ky);
            if (red && b == 0) {                          /* the sun sword's blade blazes */
                float an = m->fa * 0.0174533f;
                float tx = px + f * SWORD_LEN * cosf_(an), ty = py + SWORD_LEN * sinf_(an);
                spr(s, A_JS_TRAIL, (float)((j->aura_t / 2) % 6), tx, ty, f * 0.6f, 0.55f, -m->fa * f, C_WHITE, 0.9f);
                blend(s, 1);
                spr(s, A_JS_GLOW, 0, (px + tx) * 0.5f, (py + ty) * 0.5f, 0.9f, 0.45f, -m->fa * f, C_WHITE, 0.75f);
                blend(s, 0);
                continue;
            }
            if (red && b == 1) {                          /* the sun shield flares */
                spr(s, A_JS_FIST, (float)((j->aura_t / 2) % 8), px, py, f * 0.9f, 0.9f, 0, C_WHITE, 1);
                blend(s, 1);
                spr(s, A_JS_GLOW, 0, px, py, 0.75f, 0.75f, 0, C_WHITE, 0.8f);
                blend(s, 0);
                continue;
            }
            spr(s, red ? A_JS_TRAIL : A_JF_TRAIL, (float)((j->aura_t / 2) % 6), px, py, f * 0.7f, 0.7f, 0, C_WHITE, 0.9f);
            spr(s, red ? A_JS_FIST : A_JF_FIST, (float)((j->aura_t / 2) % 8), px, py, f, 1, 0, C_WHITE, 1);
            blend(s, 1);
            spr(s, red ? A_JS_GLOW : A_JF_GLOW, 0, px, py, 0.45f, 0.45f, 0, C_WHITE, 0.8f);
            blend(s, 0);
        }
    }
    /* black hole: core, near half of the disk, rocks spiralling in */
    if (j->bh_on) {
        spr(s, A_JF_BH, (float)((j->bh_t / 3) % 8), j->bh_x, j->bh_y, g, g, 0, C_WHITE, 1);
        for (int i = 0; i < 5; i++) {
            float ph = (float)((j->bh_t * 3 + i * 18) % 90) / 90.0f;
            float ang = i * 1.26f + ph * 6.0f, rr = 70 * (1 - ph) + 8;
            spr(s, A_JF_ROCK, (float)((j->bh_t / 3 + i) % 8), j->bh_x + rr * cosf_(ang), j->bh_y + rr * 0.4f * sinf_(ang), 1, 1, 0, C_WHITE, g);
        }
        spr(s, A_JF_BHRING_F, (float)((j->bh_t / 3) % 8), j->bh_x, j->bh_y, g * 0.75f, g * 0.75f, 0, C_WHITE, 1);
    }
    /* meteors, pointing along their fall */
    for (int i = 0; i < N_MET; i++) {
        Meteor *mt = &j->met[i];
        if (!mt->on) continue;
        float rot = -atan2f_(mt->vy, mt->vx) * 57.29578f;
        spr(s, A_JF_METEOR, (float)((mt->t / 2) % 8), mt->x, mt->y, 1, 1, rot, C_WHITE, 1);
        blend(s, 1);
        spr(s, A_JF_GLOW, 0, mt->x, mt->y, 0.5f, 0.5f, 0, C_WHITE, 0.7f);
        blend(s, 0);
    }
    /* Solar Flare: the crescent of sun fire */
    if (j->wave_on) {
        float wa2 = j->wave_t > 32 ? (40 - j->wave_t) / 8.0f : 1.0f;
        spr(s, A_JS_WAVE, (float)((j->wave_t / 2) % 8), j->wave_x, j->wave_y, j->wave_dir, 1, 0, C_WHITE, wa2);
        blend(s, 1);
        spr(s, A_JS_GLOW, 0, j->wave_x - j->wave_dir * 6, j->wave_y, 0.7f, 1.2f, 0, C_WHITE, 0.7f * wa2);
        blend(s, 0);
    }
    /* one-shot effects: bursts, kick arcs, craters, rings */
    for (int i = 0; i < N_JFX; i++) {
        JFx *fx = &j->fx[i];
        if (!fx->on) continue;
        if (fx->add) blend(s, 1);
        spr(s, fx->a, (float)(fx->t / fx->tpf), fx->x, fx->y, fx->xs, fx->ys, fx->rot, fx->col, 1);
        if (fx->add) blend(s, 0);
    }
    if (j->fail_t > 0) {                                /* the finishers need a full energy bar */
        blend(s, 1);
        spr(s, A_JF_GLOW, 0, x, y - 62, 0.6f, 0.6f, 0, C_RED, j->fail_t / 24.0f);
        blend(s, 0);
    }
    /* special: dash streaks and the KO impact */
    if (j->move == MOVE_SPECIAL && j->t <= SP_DASH)
        spr(s, A_SP_DASH, (float)(j->t / 2), x, y, j->dir, 1, 0, C_WHITE, 1);
    if (j->impact_on) {
        blend(s, 1);
        spr(s, A_SP_IMPACT, j->impact_t / 3.0f, j->impact_x, j->impact_y, j->dir, 1, 0, C_WHITE, 1);
        blend(s, 0);
    }
}

static double legacy0(CInstance *s, YYVAR *f) {
    RValue r = rv_undef();
    YYGML_CallLegacyFunction(s, s, &r, 0, f->id, 0);
    double d = rv_num(&r);
    rv_free(&r);
    return d;
}

/* ------------------------------------------------------------------------------------------ */
/* the cinematics (GUI layer, a 320x180 stage scaled to the screen)                            */
/* ------------------------------------------------------------------------------------------ */
static float sstep(float a, float b, float t) {
    float u = (t - a) / (b - a);
    if (u < 0) u = 0;
    if (u > 1) u = 1;
    return u * u * (3 - 2 * u);
}
static void gui_fill(float gw, float gh, int col, float alpha) {
    if (alpha <= 0.01f) return;
    YYGML_draw_set_colour(col);
    YYGML_draw_set_alpha(alpha > 1 ? 1 : alpha);
    YYGML_draw_rectangle(0, 0, gw, gh, false);
}
/* Jeff on the cinematic stage: feet at (X, Y), facing right, k = scale */
static void cin_jeff(CInstance *s, Jeff *j, int a, int frame, float X, float Y, float k, bool dark, float alpha) {
    spr(s, dark ? A_DARK0 + a : a, (float)frame, X, Y, k, k, 0, C_WHITE, alpha);
    const JeffFrame *m = meta_of(a, (float)frame);
    if (dark && m) draw_eyes(s, j, m, X, Y, 1, k, alpha);
}
/* the opponent as they were when it started (their own sprite), facing Jeff */
static void cin_victim(CInstance *s, Jeff *j, float X, float Y, float xs, float ys, float rot, float alpha) {
    if (j->cin_spr < 0 || alpha <= 0.01f) return;
    YYGML_draw_sprite_ext(s, j->cin_spr, j->cin_img, X, Y, -xs * j->cin_vk, ys * j->cin_vk, rot, C_WHITE, alpha);
}

static void draw_cinematic(CInstance *s, Jeff *j) {
    float gw = (float)legacy0(s, &g_FUNC_display_get_gui_width);
    float gh = (float)legacy0(s, &g_FUNC_display_get_gui_height);
    if (gw < 16 || gh < 16) return;
    float P = gw / CUT_W; if (gh / CUT_H < P) P = gh / CUT_H;
    float ox = (gw - CUT_W * P) * 0.5f, oy = (gh - CUT_H * P) * 0.5f;
    if (j->shake > 0.3f) { ox += frand(-j->shake, j->shake) * P * 0.5f; oy += frand(-j->shake, j->shake) * P * 0.5f; }
#define GX(v) (ox + (v) * P)
#define GY(v) (oy + (v) * P)
    int t = j->t;
    bool redc = j->cin == CIN_REDHOLE;
    int dur = redc ? CIN_RED_DUR : CIN_PUR_DUR, ko = redc ? CIN_RED_KO : CIN_PUR_KO;
    float A = t > dur - 12 ? (dur - t) / 12.0f : 1.0f;   /* fades back to the fight at the end */
    if (A < 0) A = 0;
    bool dark = redc || j->power;                        /* the red black hole is the black form's */

    gui_fill(gw, gh, 0, A);
    spr(s, A_CIN_BG, redc ? 0 : 1, GX(0), GY(0), P, P, 0, C_WHITE, A);

    if (redc) {
        /* RED BLACK HOLE: a sun-fire black hole opens over the opponent and swallows them */
        float HX = 222, HY = 74;
        float gr = sstep(8, 56, (float)t) * (1 - 0.8f * sstep(102, (float)ko, (float)t));
        if (t < ko) {
            float d = (0.35f + 0.8f * gr) * P, c = (0.2f + 0.62f * gr) * P;
            spr(s, A_RBH_DISK_B, (float)((t / 3) % 8), GX(HX), GY(HY), d, d, 0, C_WHITE, A);
            spr(s, A_RBH_CORE, (float)((t / 3) % 8), GX(HX), GY(HY), c, c, 0, C_WHITE, A);
        }
        float u = sstep(26, 104, (float)t);              /* pulled up, stretched thin, spun */
        if (t < 110)
            cin_victim(s, j, GX(238 + (HX - 238) * u), GY(150 + (HY + 16 - 150) * u),
                       1.6f * P * (1 - 0.72f * u), 1.6f * P * (1 + 1.4f * u), u * u * 620, A * (1 - sstep(94, 108, (float)t)));
        for (int i = 0; i < 7 && t < ko; i++) {          /* rubble torn off the ground, spiralling in */
            float ph = (float)((t * 2 + i * 37) % 120) / 120.0f;
            float ang = i * 0.9f + ph * 7.0f, rr = (96 * (1 - ph) + 10) * (0.4f + 0.6f * gr);
            spr(s, A_JF_ROCK, (float)((t / 3 + i) % 8), GX(HX + rr * cosf_(ang)), GY(HY + rr * 0.45f * sinf_(ang)),
                P * 1.3f, P * 1.3f, 0, C_SUN, A * gr);
        }
        if (t < ko) {
            float d = (0.35f + 0.8f * gr) * P;
            spr(s, A_RBH_DISK_F, (float)((t / 3) % 8), GX(HX), GY(HY), d, d, 0, C_WHITE, A);
        }
        bool posed = t >= ko + 8;
        cin_jeff(s, j, posed ? A_POSE : A_METEOR, posed ? (t < ko + 30 ? 0 : 1) : (t < 22 ? 1 : 2), GX(78), GY(150), 1.6f * P, dark, A);
        if (!posed) {                                    /* the hand that holds it open */
            const JeffFrame *m = meta_of(A_METEOR, t < 22 ? 1.0f : 2.0f);
            if (m) {
                blend(s, 1);
                spr(s, A_JS_GLOW, 0, GX(78 + m->fx * 1.6f), GY(150 + m->fy * 1.6f), 0.5f * P, 0.5f * P, 0, C_WHITE, A * (0.6f + 0.3f * gr));
                blend(s, 0);
            }
        }
        if (t >= ko) {                                   /* it collapses: the sun bursts out */
            int e = t - ko;
            blend(s, 1);
            if (e < 30) spr(s, A_JS_BURST, (float)(e / 3), GX(HX), GY(HY), 2.4f * P, 2.4f * P, 0, C_WHITE, A);
            spr(s, A_JS_GLOW, 0, GX(HX), GY(HY), (1.5f + e * 0.12f) * P, (1.5f + e * 0.12f) * P, 0, C_WHITE, A * (1 - e / 52.0f));
            blend(s, 0);
            for (int r = 0; r < 2; r++) {
                int er = e - r * 6;
                if (er < 0 || er > 36) continue;
                float rs = (0.5f + er * 0.06f) * P;
                spr(s, A_CIN_RING, (float)((er / 3) % 8), GX(HX), GY(HY + 6), rs, rs, 0, C_SUN, A * (1 - er / 36.0f));
            }
        }
        if (t < 6) gui_fill(gw, gh, C_WHITE, (6 - t) / 6.0f * A);
        if (t >= ko && t < ko + 8) gui_fill(gw, gh, C_WHITE, (ko + 8 - t) / 8.0f * A);
    } else {
        /* HOLLOW PURPLE: blue in one hand, red in the other, merged, flicked - a purple nuclear blast */
        float JX = 92, JY = 150, k = 1.7f;
        if (t > 150) k += 0.3f * sstep(150, 178, (float)t);      /* push in on the pose */
        int ja = t < 150 ? A_PURPLE : A_POSE;
        int jf = t < 150 ? (t < 40 ? 0 : t < 70 ? 1 : t < 96 ? 2 : 3) : 1;
        if (t < 112) cin_victim(s, j, GX(262), GY(150), 1.6f * P, 1.6f * P, 0, A);
        cin_jeff(s, j, ja, jf, GX(JX), GY(JY), k * P, dark, A);
        const JeffFrame *m = meta_of(A_PURPLE, (float)(jf > 3 ? 3 : jf));
        if (t < 96 && m) {
            float bx = JX + m->bx * k, by = JY + m->by * k, fx = JX + m->fx * k, fy = JY + m->fy * k;
            float og = sstep(0, 20, (float)t), pul = 1 + 0.08f * sinf_(t * 0.5f);
            if (t < 72) {
                float o2 = og * pul * 1.1f * P;
                float mx = t < 40 ? 0 : sstep(40, 72, (float)t) * 0.5f;  /* drifting together */
                float bx2 = bx + (fx - bx) * mx * 0.6f, fx2 = fx + (bx - fx) * mx * 0.6f;
                spr(s, A_HP_ORB_B, (float)((t / 2) % 8), GX(bx2), GY(by), o2, o2, 0, C_WHITE, A);
                spr(s, A_HP_ORB_R, (float)((t / 2) % 8), GX(fx2), GY(fy), o2, o2, 0, C_WHITE, A);
                blend(s, 1);
                spr(s, A_JF_GLOW, 0, GX(bx2), GY(by), 0.9f * og * P, 0.9f * og * P, 0, C_WHITE, A * 0.7f);
                spr(s, A_JS_GLOW, 0, GX(fx2), GY(fy), 0.9f * og * P, 0.9f * og * P, 0, C_WHITE, A * 0.7f);
                blend(s, 0);
            } else {
                float mx = (bx + fx) * 0.5f, my = (by + fy) * 0.5f;
                float pg = (0.8f + 0.8f * sstep(72, 94, (float)t)) * pul * P;
                spr(s, A_HP_ORB_P, (float)((t / 2) % 8), GX(mx), GY(my), pg, pg, 0, C_WHITE, A);
                blend(s, 1);
                spr(s, A_JD_GLOW, 0, GX(mx), GY(my), 3.2f * pg, 3.2f * pg, 0, C_PURPLE, A * 0.65f);
                blend(s, 0);
            }
        }
        if (t >= 96 && t < 110) {                        /* the flick */
            const JeffFrame *m3 = meta_of(A_PURPLE, 3);
            float sx0 = JX + (m3 ? m3->fx : 30) * k, sy0 = JY + (m3 ? m3->fy : -30) * k;
            float u = (t - 96) / 10.0f;
            if (u > 1) u = 1;
            for (int i = 3; i >= 0; i--) {
                float uu = u - i * 0.08f;
                if (uu < 0) continue;
                float ps = 1.6f * P * (1 - i * 0.16f);
                spr(s, A_HP_ORB_P, (float)((t / 2 + i) % 8), GX(sx0 + (262 - sx0) * uu), GY(sy0 + (124 - sy0) * uu), ps, ps, 0, C_WHITE, A * (1 - i * 0.22f));
            }
        }
        if (t >= 106) {                                  /* the blast */
            int e = t - 106, nf = e / 4;
            if (nf > 11) nf = 11;
            float na = e > 44 ? 1 - (e - 44) / 18.0f : 1.0f;    /* the cloud thins out */
            if (na < 0) na = 0;
            spr(s, A_HP_NUKE, (float)nf, GX(262), GY(152), 1.3f * P, 1.3f * P, 0, C_WHITE, A * na);
            blend(s, 1);                                         /* the ground keeps glowing */
            spr(s, A_JD_GLOW, 0, GX(262), GY(150), 7.0f * P, 1.6f * P, 0, C_PURPLE, A * 0.6f * (1 - sstep(50, 94, (float)e)));
            blend(s, 0);
            for (int r = 0; r < 3; r++) {
                int er = e - r * 5;
                if (er < 0 || er > 40) continue;
                float rs = (0.5f + er * 0.075f) * P;
                spr(s, A_CIN_RING, (float)((er / 3) % 8), GX(262), GY(150), rs, rs, 0, C_PURPLE, A * (1 - er / 40.0f));
            }
            blend(s, 1);
            spr(s, A_JD_GLOW, 0, GX(262), GY(110), (4 + e * 0.08f) * P, (4 + e * 0.08f) * P, 0, C_PURPLE, A * (1 - sstep(0, 70, (float)e)) * 0.8f);
            blend(s, 0);
        }
        if (t >= 72 && t < 78) gui_fill(gw, gh, C_PURPLE, (78 - t) / 6.0f * 0.5f * A);
        if (t >= 106 && t < 118) gui_fill(gw, gh, C_WHITE, (118 - t) / 12.0f * A);
    }
    /* letterbox bars */
    float h = CUT_H * P, bar = h * 0.1f;
    float in = t < 10 ? t / 10.0f : (t > dur - 10 ? (dur - t) / 10.0f : 1.0f);
    if (in < 0) in = 0;
    YYGML_draw_set_alpha(A);
    YYGML_draw_set_colour(0);
    YYGML_draw_rectangle(0, 0, gw, oy + bar * in, false);
    YYGML_draw_rectangle(0, gh - oy - bar * in, gw, gh, false);
    YYGML_draw_set_colour(C_WHITE);
    YYGML_draw_set_alpha(1);
#undef GX
#undef GY
}

void gml_Object_o_jeff_Draw_64(CInstance *s, CInstance *o) {
    (void)o;
    Jeff *j = slot(s, false);
    if (!j) return;
    if (j->move == MOVE_CIN) { draw_cinematic(s, j); return; }
    if (j->move != MOVE_SPECIAL || j->t <= SP_DASH || j->t > SP_DASH + SP_CUT) return;
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
