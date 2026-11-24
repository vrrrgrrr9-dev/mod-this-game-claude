/*
 * Minimal interface to the GameMaker YYC runtime inside libyoyo.so (Warriors of the Universe).
 *
 * Everything here is resolved to absolute addresses by build/gen_engine.py and linked into a
 * blob that lives in a new segment of the same libyoyo.so, so calls/ADRP stay PC-relative.
 * Layouts were taken from the game's own compiled code (see analysis/ notes).
 */
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

typedef struct RValue {
    union { double val; int64_t v64; int32_t v32; void *ptr; };
    uint32_t flags;
    uint32_t kind;
} RValue;

enum {
    VALUE_REAL = 0, VALUE_STRING = 1, VALUE_ARRAY = 2, VALUE_PTR = 3, VALUE_UNDEFINED = 5,
    VALUE_OBJECT = 6, VALUE_INT32 = 7, VALUE_INT64 = 10, VALUE_BOOL = 13, VALUE_REF = 15,
};
#define ARRAY_INDEX_NONE ((int)0x80000000)
#define KIND_MASK 0x00ffffffu

typedef struct CInstance CInstance;             /* opaque; vtable pointer at offset 0 */
typedef struct { const char *name; int32_t id; int32_t pad; } YYVAR;   /* g_VAR_* / g_FUNC_* */

typedef void (*GML_Event)(CInstance *self, CInstance *other);
typedef RValue *(*GML_Script)(CInstance *self, CInstance *other, RValue *ret, int argc, RValue **args);
typedef void (*GML_Builtin)(RValue *ret, CInstance *self, CInstance *other, int argc, RValue *args);

/* ---- engine functions (addresses from engine.ld) ---- */
bool   BOOL_RValue(const RValue *v);
double REAL_RValue_Ex(const RValue *v);
int    INT32_RValue(const RValue *v);
void   FREE_RValue__Pre(RValue *v);
void   YYCreateString(RValue *v, const char *s);
void   YYGML_Variable_GetValue(const RValue *inst, int var, int idx, RValue *out, bool a, bool b);
void   YYGML_Variable_SetValue(const RValue *inst, int var, int idx, RValue *val);
void   Variable_GetValue_Direct(CInstance *inst, int var, int idx, RValue *out, bool a, bool b);
void   Variable_SetValue_Direct(CInstance *inst, int var, int idx, RValue *val);
CInstance *YYGML_FindInstance(int id);
RValue *YYGML_CallLegacyFunction(CInstance *self, CInstance *other, RValue *ret, int argc, int fid, RValue **args);
void   YYGML_draw_sprite_ext(CInstance *self, int spr, float img, float x, float y, float xs, float ys,
                             float rot, int col, float alpha);
void   YYGML_draw_self(CInstance *self);
void   YYGML_draw_set_alpha(float a);
void   YYGML_draw_set_colour(int c);
void   YYGML_draw_rectangle(float x1, float y1, float x2, float y2, bool outline);

void F_SpriteAdd(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_SpriteExists(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_AudioCreateStream(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_AudioPlaySound(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_AudioStopSound(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_AudioSoundPitch(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_GPUSetBlendMode(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_InstanceCreateDepth(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_InstanceNumber(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_InstanceFind(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_InstanceExists(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_ObjectSetSprite(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_DrawCircle(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_DrawLineWidth(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_ViewGetCamera(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_CameraGetViewX(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_CameraGetViewY(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_CameraGetViewWidth(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_CameraGetViewHeight(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_LayerGetAll(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_LayerGetAllElements(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_LayerGetElementType(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_LayerSetVisible(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_PlaceMeeting(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_CollisionPoint(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_DrawSpriteStretchedExt(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_LayerGetDepth(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_DrawSpritePartExt(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_DrawSpritePos(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_DrawPrimitiveBegin(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_DrawVertexColor(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);
void F_DrawPrimitiveEnd(RValue *r, CInstance *s, CInstance *o, int n, RValue *a);

RValue *gml_Script_scr_plr_step(CInstance *s, CInstance *o, RValue *ret, int argc, RValue **args);
RValue *gml_Script_scr_combo_normal(CInstance *s, CInstance *o, RValue *ret, int argc, RValue **args);
RValue *gml_Script_scr_char_charge_effect(CInstance *s, CInstance *o, RValue *ret, int argc, RValue **args);
void gml_Object_o_parent_character_Create_0(CInstance *s, CInstance *o);
void gml_Object_o_parent_character_Destroy_0(CInstance *s, CInstance *o);

extern CInstance *g_pGlobal;
extern RValue g_undefinedRV;
#include "engine_vars.h"

/* ---- RValue helpers ---- */
#define NEEDS_FREE(k) ((1u << ((k) & 0x1f)) & 0x46u)   /* string / array / object, as YYC does */

static inline RValue rv_real(double d) { RValue r; r.val = d; r.flags = 0; r.kind = VALUE_REAL; return r; }
static inline RValue rv_bool(bool b) { RValue r; r.val = b ? 1.0 : 0.0; r.flags = 0; r.kind = VALUE_BOOL; return r; }
static inline RValue rv_undef(void) { RValue r; r.v64 = 0; r.flags = 0; r.kind = VALUE_UNDEFINED; return r; }
static inline RValue rv_inst(CInstance *i) { RValue r; r.ptr = i; r.flags = 0; r.kind = VALUE_OBJECT; return r; }
static inline void rv_free(RValue *r) { if (NEEDS_FREE(r->kind)) FREE_RValue__Pre(r); r->kind = VALUE_UNDEFINED; r->v64 = 0; }

static inline double rv_num(const RValue *r) {
    uint32_t k = r->kind & KIND_MASK;
    if (k == VALUE_REAL || k == VALUE_BOOL) return r->val;
    if (k == VALUE_UNDEFINED) return 0.0;
    if (k == VALUE_INT32) return (double)r->v32;
    if (k == VALUE_INT64) return (double)r->v64;
    return REAL_RValue_Ex(r);
}

/* instance variable slot (read / write) through the CInstance vtable, exactly like YYC code */
static inline RValue *var_slot_r(CInstance *inst, int id) {
    RValue *(*f)(CInstance *, int) = (*(RValue *(***)(CInstance *, int))inst)[2];
    return f(inst, id);
}
static inline RValue *var_slot_w(CInstance *inst, int id) {
    RValue *(*f)(CInstance *, int) = (*(RValue *(***)(CInstance *, int))inst)[3];
    return f(inst, id);
}
