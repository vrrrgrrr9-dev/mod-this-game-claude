/*
 * Integration hooks: how Jeff gets into the game.
 *
 *  1. InitLLVM (YYC startup): the Coco mod already appends its 36 event functions (table grows
 *     0xe41 -> 0xe65). We run after it and append Jeff's event functions at 0xe65+, which is what
 *     the o_jeff object we add to game.droid points its event CodeIds at.
 *  2. scr_menu_get_char(id): character id 1005 = Jeff (name, title, object, face, shop fields).
 *  3. character-select list: after the mod rebuilds global.charord we make sure 1005 is in it and
 *     mark global.char[1005] as owned.
 */
#include "yyc.h"
#include "jeff_assets.h"

#define JEFF_CHAR_ID 1005
#define OBJ_JEFF 685
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

static YYCodeFunc g_funcs[MOD_FUNC_COUNT + 16];
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
    add(&n, "gml_Object_o_jeff_Create_0", (void *)gml_Object_o_jeff_Create_0);   /* 0xe65 */
    add(&n, "gml_Object_o_jeff_Step_0", (void *)gml_Object_o_jeff_Step_0);       /* 0xe66 */
    add(&n, "gml_Object_o_jeff_Draw_0", (void *)gml_Object_o_jeff_Draw_0);       /* 0xe67 */
    add(&n, "gml_Object_o_jeff_Draw_64", (void *)gml_Object_o_jeff_Draw_64);     /* 0xe68 */
    add(&n, "gml_Object_o_jeff_Destroy_0", (void *)gml_Object_o_jeff_Destroy_0); /* 0xe69 */
    add(&n, "gml_Object_o_jeff_Alarm_0", (void *)gml_Object_o_jeff_Alarm_0);     /* 0xe6a */
    add(&n, "gml_Object_o_jeff_Alarm_2", (void *)gml_Object_o_jeff_Alarm_2);     /* 0xe6b */
    add(&n, "gml_Object_o_jeff_Alarm_3", (void *)gml_Object_o_jeff_Alarm_3);     /* 0xe6c */
    *(YYCodeFunc **)(vars + 0x28) = g_funcs;
    *(int *)(vars + 0x14) = n;
}

/* ---- scr_menu_get_char ---------------------------------------------------------------- */
static void put_num(CInstance *s, YYVAR *v, double d) { RValue *r = var_slot_w(s, v->id); rv_free(r); *r = rv_real(d); }
static void put_bool(CInstance *s, YYVAR *v, bool b) { RValue *r = var_slot_w(s, v->id); rv_free(r); *r = rv_bool(b); }
static void put_str(CInstance *s, YYVAR *v, const char *str) { RValue *r = var_slot_w(s, v->id); rv_free(r); YYCreateString(r, str); }

RValue *jeff_get_char(CInstance *s, CInstance *o, RValue *ret, int argc, RValue **args) {
    if (argc >= 1 && args && args[0] && (int)rv_num(args[0]) == JEFF_CHAR_ID && s) {
        jeff_load_assets(s);
        put_str(s, &g_VAR_char_name, "Jeff");
        put_str(s, &g_VAR_char_title, "The Bone Breaker");
        put_num(s, &g_VAR_char_obj, OBJ_JEFF);
        put_num(s, &g_VAR_char_face, g_jeff_spr[A_FACE]);
        put_num(s, &g_VAR_char_shop_back, SPR_SHOP_BACK_HERO);
        put_bool(s, &g_VAR_char_unlocked, true);
        put_bool(s, &g_VAR_char_bought, true);
        put_num(s, &g_VAR_char_stats_hp, 2300);
        put_num(s, &g_VAR_char_stats_dmg, 46);
        put_num(s, &g_VAR_char_stats_speed, 12);
        put_num(s, &g_VAR_char_stats_pwr, 70);
        put_num(s, &g_VAR_char_stats_combat, 88);
        put_num(s, &g_VAR_char_shop_price, 0);
        put_num(s, &g_VAR_char_shop_level, 0);
        put_num(s, &g_VAR_char_shop_needchar, -1);
        put_num(s, &g_VAR_char_shop_cond, 0);
        put_num(s, &g_VAR_char_shop_chall, 0);
        put_num(s, &g_VAR_char_price, 0);
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

static void jeff_charsel_add(void) {
    if (!g_pGlobal) return;
    RValue *ord = var_slot_r(g_pGlobal, g_VAR_charord.id);
    RValue *num = var_slot_r(g_pGlobal, g_VAR_chars_num.id);
    if (!ord || !num || (ord->kind & KIND_MASK) != VALUE_ARRAY) return;
    int n = (int)rv_num(num);
    if (n < 0 || n > 500) return;
    int found = 0;
    for (int i = 1; i <= n; i++)
        if ((int)gget_i(&g_VAR_charord, i) == JEFF_CHAR_ID) { found = 1; break; }
    if (!found) {
        for (int i = n; i >= 1; i--) gset_i(&g_VAR_charord, i + 1, gget_i(&g_VAR_charord, i));
        gset_i(&g_VAR_charord, 1, JEFF_CHAR_ID);
        RValue *w = var_slot_w(g_pGlobal, g_VAR_chars_num.id);
        rv_free(w);
        *w = rv_real(n + 1);
    }
    RValue *ch = var_slot_r(g_pGlobal, g_VAR_char.id);
    if (ch && (ch->kind & KIND_MASK) == VALUE_ARRAY) gset_i(&g_VAR_char, JEFF_CHAR_ID, 1);
}

/* replaces the two `bl mod_charsel_ext` calls inside the mod's charsel Create hook */
void jeff_charsel_ext(CInstance *s) {
    mod_charsel_ext(s);
    jeff_charsel_add();
}
