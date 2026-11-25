/*
 * Integration hooks: how Jeff and Black Holing Scyther get into the game.
 *
 *  1. InitLLVM (YYC startup): the Coco mod already appends its 36 event functions (table grows
 *     0xe41 -> 0xe65). We run after it and append Jeff's event functions at 0xe65.. and Scyther's
 *     at 0xe6d.. and Grey's at 0xe76.., which is what the o_jeff / o_scyther / o_grey objects we add
 *     to game.droid point at.
 *  2. scr_menu_get_char(id): 1005 = Jeff, 1006 = Scyther, 1007 = Grey (name, title, object, face...).
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
#define GREY_CHAR_ID 1007
#define OBJ_GREY 687
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

/* Grey's events (grey.c) */
void gml_Object_o_grey_Create_0(CInstance *, CInstance *);
void gml_Object_o_grey_Step_0(CInstance *, CInstance *);
void gml_Object_o_grey_Draw_0(CInstance *, CInstance *);
void gml_Object_o_grey_Draw_64(CInstance *, CInstance *);
void gml_Object_o_grey_Draw_72(CInstance *, CInstance *);
void gml_Object_o_grey_Destroy_0(CInstance *, CInstance *);
void gml_Object_o_grey_Alarm_0(CInstance *, CInstance *);
void gml_Object_o_grey_Alarm_2(CInstance *, CInstance *);
void gml_Object_o_grey_Alarm_3(CInstance *, CInstance *);
void grey_load_assets(CInstance *s);
int grey_face_sprite(void);

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
    add(&n, "gml_Object_o_grey_Create_0", (void *)gml_Object_o_grey_Create_0);       /* 0xe76 */
    add(&n, "gml_Object_o_grey_Step_0", (void *)gml_Object_o_grey_Step_0);           /* 0xe77 */
    add(&n, "gml_Object_o_grey_Draw_0", (void *)gml_Object_o_grey_Draw_0);           /* 0xe78 */
    add(&n, "gml_Object_o_grey_Draw_64", (void *)gml_Object_o_grey_Draw_64);         /* 0xe79 */
    add(&n, "gml_Object_o_grey_Destroy_0", (void *)gml_Object_o_grey_Destroy_0);     /* 0xe7a */
    add(&n, "gml_Object_o_grey_Alarm_0", (void *)gml_Object_o_grey_Alarm_0);         /* 0xe7b */
    add(&n, "gml_Object_o_grey_Alarm_2", (void *)gml_Object_o_grey_Alarm_2);         /* 0xe7c */
    add(&n, "gml_Object_o_grey_Alarm_3", (void *)gml_Object_o_grey_Alarm_3);         /* 0xe7d */
    add(&n, "gml_Object_o_grey_Draw_72", (void *)gml_Object_o_grey_Draw_72);         /* 0xe7e */
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
    if (s && id == GREY_CHAR_ID) {
        grey_load_assets(s);
        put_char(s, "Grey", "The Glitch", OBJ_GREY, grey_face_sprite(), 2200, 47, 14, 90, 99);
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
        if (obj == OBJ_JEFF || obj == OBJ_SCYTHER || obj == OBJ_GREY) gset_i(&g_VAR_game_plrchar, i, -1);
    }
}

/* replaces the two `bl mod_charsel_ext` calls inside the mod's charsel Create hook */
void jeff_charsel_ext(CInstance *s) {
    mod_charsel_ext(s);
    if (!g_pGlobal) return;
    if (online_mode()) { clear_mod_picks(); return; }
    charsel_add(GREY_CHAR_ID);               /* each insert goes to the front: Jeff, Scyther, Grey, ... */
    charsel_add(SCY_CHAR_ID);
    charsel_add(JEFF_CHAR_ID);
}

/* ---------------------------------------------------------------------------------------------
 * Cheats: local fights only.
 *
 * The Coco build's Cheats dialog (Java, com.coco.transfer.ModSettings) has nine switches: Infinite
 * Mana, No Skill Cooldown, Chicken Characters, Infinite Money, Everything Unlocked, Infinite XP,
 * Infinite HP & One-Tap KO, Absolute Immunity, Infinite Dash & Jump. They are bits 0..8 of one word
 * in the mod's data (0x3060000, default 0x1f), written only by the JNI method
 * TransferBridge.nativeSetCheats and read by every cheat in the mod's native code.
 *
 * We keep the player's choice ourselves and make the word the game reads 0 while in online / LAN
 * play (global.game_gm == 2), and the choice otherwise:
 *  - nativeSetCheats (0x3055e50) branches to jeff_cheats_set. It runs on the Android UI thread, so
 *    it touches no game state: it stores the choice and applies it unless the game thread last saw
 *    online mode;
 *  - every frame, before the game runs it, RunnerJNILib.Process (0xaeb6a4) goes through
 *    jeff_process_hook, which re-applies the choice for the current mode (jeff_frame);
 *  - the pause menu's Cheats button is not drawn while online (jeff_cheat_button_pause). The one in
 *    the settings menu stays: switches flipped there apply in local fights.
 * ------------------------------------------------------------------------------------------- */
#define CHEAT_BITS 0x1ffu                    /* the nine switches (nativeSetCheats masks the same) */
#define COCO_CHEATS_DEFAULT 0x1fu            /* the word's value in the Coco build (checked by elfpatch) */
extern unsigned coco_cheat_word;             /* jeff.ld: the mod's cheat word */
static unsigned g_cheats_user = COCO_CHEATS_DEFAULT;   /* what the player picked */
int g_cheats_online;                         /* online as last seen by the game thread (read by the shim below) */

static void cheats_put(unsigned v) { __atomic_store_n(&coco_cheat_word, v, __ATOMIC_RELEASE); }

/* JNI: void TransferBridge.nativeSetCheats(int) - the dialog's switches */
void jeff_cheats_set(void *env, void *cls, int mask) {
    (void)env; (void)cls;
    unsigned m = (unsigned)mask & CHEAT_BITS;
    __atomic_store_n(&g_cheats_user, m, __ATOMIC_RELEASE);
    cheats_put(__atomic_load_n(&g_cheats_online, __ATOMIC_ACQUIRE) ? 0 : m);
}

/* once a frame, on the game thread, before the frame's events run */
void jeff_frame(void) {
    int on = online_mode();
    __atomic_store_n(&g_cheats_online, on, __ATOMIC_RELEASE);
    cheats_put(on ? 0 : __atomic_load_n(&g_cheats_user, __ATOMIC_ACQUIRE));
}

/* RunnerJNILib.Process entry: its first instruction (str d10, [sp, #-0x80]!) is replaced by a branch
   here. Keep every argument register, run jeff_frame, then do that instruction and carry on. */
__asm__(
    "    .text\n"
    "    .global jeff_process_hook\n"
    "    .type jeff_process_hook, %function\n"
    "    .p2align 2\n"
    "jeff_process_hook:\n"
    "    stp x29, x30, [sp, #-0xa0]!\n"
    "    mov x29, sp\n"
    "    stp x0, x1, [sp, #0x10]\n"
    "    stp x2, x3, [sp, #0x20]\n"
    "    stp x4, x5, [sp, #0x30]\n"
    "    stp x6, x7, [sp, #0x40]\n"
    "    stp d0, d1, [sp, #0x50]\n"
    "    stp d2, d3, [sp, #0x60]\n"
    "    stp d4, d5, [sp, #0x70]\n"
    "    stp d6, d7, [sp, #0x80]\n"
    "    str x8, [sp, #0x90]\n"
    "    bl jeff_frame\n"
    "    ldr x8, [sp, #0x90]\n"
    "    ldp d6, d7, [sp, #0x80]\n"
    "    ldp d4, d5, [sp, #0x70]\n"
    "    ldp d2, d3, [sp, #0x60]\n"
    "    ldp d0, d1, [sp, #0x50]\n"
    "    ldp x6, x7, [sp, #0x40]\n"
    "    ldp x4, x5, [sp, #0x30]\n"
    "    ldp x2, x3, [sp, #0x20]\n"
    "    ldp x0, x1, [sp, #0x10]\n"
    "    ldp x29, x30, [sp], #0xa0\n"
    "    str d10, [sp, #-0x80]!\n"          /* the instruction the branch replaced */
    "    b runner_process_cont\n"           /* Process + 4 */
    "    .size jeff_process_hook, .-jeff_process_hook\n"
    "\n"
    /* the pause menu's Cheats button (a call to the mod's button routine): skipped while online.
       Only x16 (a call-scratch register) is used, so the button's arguments pass through untouched. */
    "    .global jeff_cheat_button_pause\n"
    "    .type jeff_cheat_button_pause, %function\n"
    "    .p2align 2\n"
    "jeff_cheat_button_pause:\n"
    "    adrp x16, g_cheats_online\n"
    "    ldr w16, [x16, :lo12:g_cheats_online]\n"
    "    cbnz w16, 1f\n"
    "    b coco_cheat_button\n"
    "1:  ret\n"
    "    .size jeff_cheat_button_pause, .-jeff_cheat_button_pause\n"
);
