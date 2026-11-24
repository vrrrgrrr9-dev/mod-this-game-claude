/*
 * Integration hooks: how Jeff and Black Holing Scyther get into the game.
 *
 *  1. InitLLVM (YYC startup): the Coco mod already appends its 36 event functions (table grows
 *     0xe41 -> 0xe65). We run after it and append Jeff's event functions at 0xe65.. and Scyther's
 *     at 0xe6d.., which is what the o_jeff / o_scyther objects we add to game.droid point at.
 *  2. scr_menu_get_char(id): 1005 = Jeff, 1006 = Scyther (name, title, object, face, shop fields).
 *  3. character-select list: after the mod rebuilds global.charord we make sure both are in it and
 *     owned. Offline modes only: in online/LAN character select (global.game_gm == 2) they are left
 *     out and a leftover pick is cleared, because the other player's game doesn't have them.
 */
#include "yyc.h"
#include "jeff_assets.h"

#define JEFF_CHAR_ID 1005
#define OBJ_JEFF 685
#define SCY_CHAR_ID 1006
#define OBJ_SCYTHER 686
#define SPR_SHOP_BACK_HERO 766
#define MOD_FUNC_COUNT 0xe65        /* table size after the Coco mod's own hook */

typedef struct { const char *name; void *func; void *gscript; } YYCodeFunc;   /* 24 bytes */

/* existing mod functions (absolute addresses, see jeff.ld) */
void mod_initllvm_hook(void *vars);
RValue *mod_get_char_hook(CInstance *s, CInstance *o, RValue *ret, int argc, RValue **args);
void mod_charsel_ext(CInstance *s);

/* Jeff's events (jeff.c) */
void gml_Object_o_jeff_Create_0(CInstance *, CInstance *);
void gml_Object_o_jeff_Step_0(CInstance *, CInstance *);
void gml_Object_o_jeff_Draw_0(CInstance *, CInstance *);
void gml_Object_o_jeff_Draw_64(CInstance *, CInstance *);
void gml_Object_o_jeff_Destroy_0(CInstance *, CInstance *);
void gml_Object_o_jeff_Alarm_0(CInstance *, CInstance *);
void gml_Object_o_jeff_Alarm_2(CInstance *, CInstance *);
void gml_Object_o_jeff_Alarm_3(CInstance *, CInstance *);
void jeff_load_assets(CInstance *s);
extern int g_jeff_spr[A_COUNT];

/* Scyther's events (scyther.c) */
void gml_Object_o_scyther_Create_0(CInstance *, CInstance *);
void gml_Object_o_scyther_Step_0(CInstance *, CInstance *);
void gml_Object_o_scyther_Draw_0(CInstance *, CInstance *);
void gml_Object_o_scyther_Draw_64(CInstance *, CInstance *);
void gml_Object_o_scyther_Draw_72(CInstance *, CInstance *);
void gml_Object_o_scyther_Destroy_0(CInstance *, CInstance *);
void gml_Object_o_scyther_Alarm_0(CInstance *, CInstance *);
void gml_Object_o_scyther_Alarm_2(CInstance *, CInstance *);
void gml_Object_o_scyther_Alarm_3(CInstance *, CInstance *);
void scyther_load_assets(CInstance *s);
extern int g_scy_spr[];
#define SCY_FACE_INDEX scyther_face_index()
int scyther_face_index(void);

static YYCodeFunc g_funcs[MOD_FUNC_COUNT + 32];
int g_jeff_func_base = -1;     /* 0xe65 when everything went as planned (for debugging) */

static void add(int *n, const char *name, void *fn) {
    g_funcs[*n].name = name;
    g_funcs[*n].func = fn;
    g_funcs[*n].gscript = 0;
    (*n)++;
}

/* order == CodeId order used by build/droidpatch.py (0xe65 + index) */
void jeff_initllvm(char *vars) {
    mod_initllvm_hook(vars);
    int n = *(int *)(vars + 0x14);
    YYCodeFunc *old = *(YYCodeFunc **)(vars + 0x28);
    if (n != MOD_FUNC_COUNT || !old) return;           /* unexpected: leave the game untouched */
    for (int i = 0; i < n; i++) g_funcs[i] = old[i];
    g_jeff_func_base = n;
    add(&n, "gml_Object_o_jeff_Create_0", (void *)gml_Object_o_jeff_Create_0);       /* 0xe65 */
    add(&n, "gml_Object_o_jeff_Step_0", (void *)gml_Object_o_jeff_Step_0);           /* 0xe66 */
    add(&n, "gml_Object_o_jeff_Draw_0", (void *)gml_Object_o_jeff_Draw_0);           /* 0xe67 */
    add(&n, "gml_Object_o_jeff_Draw_64", (void *)gml_Object_o_jeff_Draw_64);         /* 0xe68 */
    add(&n, "gml_Object_o_jeff_Destroy_0", (void *)gml_Object_o_jeff_Destroy_0);     /* 0xe69 */
    add(&n, "gml_Object_o_jeff_Alarm_0", (void *)gml_Object_o_jeff_Alarm_0);         /* 0xe6a */
    add(&n, "gml_Object_o_jeff_Alarm_2", (void *)gml_Object_o_jeff_Alarm_2);         /* 0xe6b */
    add(&n, "gml_Object_o_jeff_Alarm_3", (void *)gml_Object_o_jeff_Alarm_3);         /* 0xe6c */
    add(&n, "gml_Object_o_scyther_Create_0", (void *)gml_Object_o_scyther_Create_0); /* 0xe6d */
    add(&n, "gml_Object_o_scyther_Step_0", (void *)gml_Object_o_scyther_Step_0);     /* 0xe6e */
    add(&n, "gml_Object_o_scyther_Draw_0", (void *)gml_Object_o_scyther_Draw_0);     /* 0xe6f */
    add(&n, "gml_Object_o_scyther_Draw_64", (void *)gml_Object_o_scyther_Draw_64);   /* 0xe70 */
    add(&n, "gml_Object_o_scyther_Draw_72", (void *)gml_Object_o_scyther_Draw_72);   /* 0xe71 */
    add(&n, "gml_Object_o_scyther_Destroy_0", (void *)gml_Object_o_scyther_Destroy_0); /* 0xe72 */
    add(&n, "gml_Object_o_scyther_Alarm_0", (void *)gml_Object_o_scyther_Alarm_0);   /* 0xe73 */
    add(&n, "gml_Object_o_scyther_Alarm_2", (void *)gml_Object_o_scyther_Alarm_2);   /* 0xe74 */
    add(&n, "gml_Object_o_scyther_Alarm_3", (void *)gml_Object_o_scyther_Alarm_3);   /* 0xe75 */
    *(YYCodeFunc **)(vars + 0x28) = g_funcs;
    *(int *)(vars + 0x14) = n;
}

/* ---- scr_menu_get_char ---------------------------------------------------------------- */
static void put_num(CInstance *s, YYVAR *v, double d) { RValue *r = var_slot_w(s, v->id); rv_free(r); *r = rv_real(d); }
static void put_bool(CInstance *s, YYVAR *v, bool b) { RValue *r = var_slot_w(s, v->id); rv_free(r); *r = rv_bool(b); }
static void put_str(CInstance *s, YYVAR *v, const char *str) { RValue *r = var_slot_w(s, v->id); rv_free(r); YYCreateString(r, str); }

static void put_char(CInstance *s, const char *name, const char *title, int obj, int face,
                     int hp, int dmg, int spd, int pwr, int combat) {
    put_str(s, &g_VAR_char_name, name);
    put_str(s, &g_VAR_char_title, title);
    put_num(s, &g_VAR_char_obj, obj);
    put_num(s, &g_VAR_char_face, face);
    put_num(s, &g_VAR_char_shop_back, SPR_SHOP_BACK_HERO);
    put_bool(s, &g_VAR_char_unlocked, true);
    put_bool(s, &g_VAR_char_bought, true);
    put_num(s, &g_VAR_char_stats_hp, hp);
    put_num(s, &g_VAR_char_stats_dmg, dmg);
    put_num(s, &g_VAR_char_stats_speed, spd);
    put_num(s, &g_VAR_char_stats_pwr, pwr);
    put_num(s, &g_VAR_char_stats_combat, combat);
    put_num(s, &g_VAR_char_shop_price, 0);
    put_num(s, &g_VAR_char_shop_level, 0);
    put_num(s, &g_VAR_char_shop_needchar, -1);
    put_num(s, &g_VAR_char_shop_cond, 0);
    put_num(s, &g_VAR_char_shop_chall, 0);
    put_num(s, &g_VAR_char_price, 0);
}

RValue *jeff_get_char(CInstance *s, CInstance *o, RValue *ret, int argc, RValue **args) {
    int id = (argc >= 1 && args && args[0]) ? (int)rv_num(args[0]) : -1;
    if (s && id == JEFF_CHAR_ID) {
        jeff_load_assets(s);
        put_char(s, "Jeff", "The Bone Breaker", OBJ_JEFF, g_jeff_spr[A_FACE], 2300, 46, 12, 70, 88);
        if (ret) { rv_free(ret); *ret = rv_undef(); }
        return ret;
    }
    if (s && id == SCY_CHAR_ID) {
        scyther_load_assets(s);
        put_char(s, "Black Holing Scyther", "Reaper of Realities", OBJ_SCYTHER, g_scy_spr[SCY_FACE_INDEX], 2250, 48, 13, 86, 94);
        if (ret) { rv_free(ret); *ret = rv_undef(); }
        return ret;
    }
    return mod_get_char_hook(s, o, ret, argc, args);
}

/* ---- character select list ------------------------------------------------------------- */
static double gget_i(YYVAR *v, int idx) {
    RValue g = rv_inst(g_pGlobal), r = rv_undef();
    YYGML_Variable_GetValue(&g, v->id, idx, &r, false, false);
    double d = rv_num(&r);
    rv_free(&r);
    return d;
}
static void gset_i(YYVAR *v, int idx, double d) {
    RValue g = rv_inst(g_pGlobal), r = rv_real(d);
    YYGML_Variable_SetValue(&g, v->id, idx, &r);
}

static void charsel_add(int char_id) {
    if (!g_pGlobal) return;
    RValue *ord = var_slot_r(g_pGlobal, g_VAR_charord.id);
    RValue *num = var_slot_r(g_pGlobal, g_VAR_chars_num.id);
    if (!ord || !num || (ord->kind & KIND_MASK) != VALUE_ARRAY) return;
    int n = (int)rv_num(num);
    if (n < 0 || n > 500) return;
    int found = 0;
    for (int i = 1; i <= n; i++)
        if ((int)gget_i(&g_VAR_charord, i) == char_id) { found = 1; break; }
    if (!found) {
        for (int i = n; i >= 1; i--) gset_i(&g_VAR_charord, i + 1, gget_i(&g_VAR_charord, i));
        gset_i(&g_VAR_charord, 1, char_id);
        RValue *w = var_slot_w(g_pGlobal, g_VAR_chars_num.id);
        rv_free(w);
        *w = rv_real(n + 1);
    }
    RValue *ch = var_slot_r(g_pGlobal, g_VAR_char.id);
    if (ch && (ch->kind & KIND_MASK) == VALUE_ARRAY) gset_i(&g_VAR_char, char_id, 1);
}

#define GM_ONLINE 2              /* global.game_gm set by the main menu's Online button (LAN is under it) */
#define ONLINE_SLOTS 2           /* online is 1v1: game_plrchar[1] = this player, [2] = the opponent */

static int online_mode(void) {
    RValue *gm = g_pGlobal ? var_slot_r(g_pGlobal, g_VAR_game_gm.id) : 0;
    return gm && (int)rv_num(gm) == GM_ONLINE;
}

/* A pick of one of our fighters left over from an offline match must not be carried into an online
   match. -1 is "nothing picked", the same value the Coco mod uses to clear an unavailable character. */
static void clear_mod_picks(void) {
    RValue *pc = var_slot_r(g_pGlobal, g_VAR_game_plrchar.id);
    if (!pc || (pc->kind & KIND_MASK) != VALUE_ARRAY) return;
    for (int i = 1; i <= ONLINE_SLOTS; i++) {
        int obj = (int)gget_i(&g_VAR_game_plrchar, i);
        if (obj == OBJ_JEFF || obj == OBJ_SCYTHER) gset_i(&g_VAR_game_plrchar, i, -1);
    }
}

/* replaces the two `bl mod_charsel_ext` calls inside the mod's charsel Create hook */
void jeff_charsel_ext(CInstance *s) {
    mod_charsel_ext(s);
    if (!g_pGlobal) return;
    if (online_mode()) { clear_mod_picks(); return; }
    charsel_add(SCY_CHAR_ID);                /* each insert goes to the front: Jeff, Scyther, ... */
    charsel_add(JEFF_CHAR_ID);
}
