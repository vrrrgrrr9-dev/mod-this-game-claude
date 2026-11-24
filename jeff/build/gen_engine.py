"""Resolve the engine symbols Jeff's code uses to absolute addresses inside libyoyo.so.

usage: gen_engine.py <libyoyo.so> <out engine.ld> <out engine_vars.h>
The injected blob is linked at a fixed VA inside the same .so, so a branch or ADRP from the
blob to these addresses stays correct whatever base Android loads the library at.
"""
import re, subprocess, sys

FUNCS = {  # C name -> mangled engine symbol
    'BOOL_RValue': '_Z11BOOL_RValuePK6RValue',
    'REAL_RValue_Ex': '_Z14REAL_RValue_ExPK6RValue',
    'INT32_RValue': '_Z12INT32_RValuePK6RValue',
    'FREE_RValue__Pre': '_Z16FREE_RValue__PreP6RValue',
    'YYCreateString': '_Z14YYCreateStringP6RValuePKc',
    'YYGML_Variable_GetValue': '_Z23YYGML_Variable_GetValueRK8YYRValueiiP6RValuebb',
    'YYGML_Variable_SetValue': '_Z23YYGML_Variable_SetValueRK8YYRValueiiP6RValue',
    'Variable_GetValue_Direct': '_Z24Variable_GetValue_DirectP12YYObjectBaseiiP6RValuebb',
    'Variable_SetValue_Direct': '_Z24Variable_SetValue_DirectP12YYObjectBaseiiP6RValue',
    'YYGML_FindInstance': '_Z18YYGML_FindInstancei',
    'YYGML_CallLegacyFunction': '_Z24YYGML_CallLegacyFunctionP9CInstanceS0_R8YYRValueiiPPS1_',
    'YYGML_draw_sprite_ext': '_Z21YYGML_draw_sprite_extP9CInstanceiffffffif',
    'YYGML_draw_self': '_Z15YYGML_draw_selfP9CInstance',
    'YYGML_draw_set_alpha': '_Z20YYGML_draw_set_alphaf',
    'YYGML_draw_set_colour': '_Z21YYGML_draw_set_colouri',
    'YYGML_draw_rectangle': '_Z20YYGML_draw_rectangleffffb',
    'F_SpriteAdd': '_Z11F_SpriteAddR6RValueP9CInstanceS2_iPS_',
    'F_SpriteExists': '_Z14F_SpriteExistsR6RValueP9CInstanceS2_iPS_',
    'F_AudioCreateStream': '_Z19F_AudioCreateStreamR6RValueP9CInstanceS2_iPS_',
    'F_AudioPlaySound': '_Z16F_AudioPlaySoundR6RValueP9CInstanceS2_iPS_',
    'F_AudioStopSound': '_Z16F_AudioStopSoundR6RValueP9CInstanceS2_iPS_',
    'F_AudioSoundPitch': '_Z17F_AudioSoundPitchR6RValueP9CInstanceS2_iPS_',
    'F_GPUSetBlendMode': '_Z17F_GPUSetBlendModeR6RValueP9CInstanceS2_iPS_',
    'F_InstanceCreateDepth': '_Z21F_InstanceCreateDepthR6RValueP9CInstanceS2_iPS_',
    'F_InstanceNumber': '_Z16F_InstanceNumberR6RValueP9CInstanceS2_iPS_',
    'F_InstanceFind': '_Z14F_InstanceFindR6RValueP9CInstanceS2_iPS_',
    'F_InstanceExists': '_Z16F_InstanceExistsR6RValueP9CInstanceS2_iPS_',
    'F_ObjectSetSprite': '_Z17F_ObjectSetSpriteR6RValueP9CInstanceS2_iPS_',
    'F_DrawCircle': '_Z12F_DrawCircleR6RValueP9CInstanceS2_iPS_',
    'F_DrawLineWidth': '_Z15F_DrawLineWidthR6RValueP9CInstanceS2_iPS_',
    'gml_Script_scr_plr_step': '_Z23gml_Script_scr_plr_stepP9CInstanceS0_R8YYRValueiPPS1_',
    'gml_Script_scr_combo_normal': '_Z27gml_Script_scr_combo_normalP9CInstanceS0_R8YYRValueiPPS1_',
    'gml_Script_scr_char_charge_effect': '_Z33gml_Script_scr_char_charge_effectP9CInstanceS0_R8YYRValueiPPS1_',
    'gml_Object_o_parent_character_Create_0': '_Z38gml_Object_o_parent_character_Create_0P9CInstanceS0_',
    'gml_Object_o_parent_character_Destroy_0': '_Z39gml_Object_o_parent_character_Destroy_0P9CInstanceS0_',
}
DATA = ['g_pGlobal', 'g_undefinedRV']
VARS = '''parent plr_child plr_hp plr_maxhp plr_energy plr_maxenergy plr_dmg plr_team plr_controller
is_dead is_hurt is_fallen is_onair is_attacking is_airattacking is_defending is_crouching is_charging
is_transforming can_move can_attack can_attack_reload can_gethurt can_loopspr can_use_skill
key_defend key_down key_up key_left key_right keyp_special keyp_action1 keyp_action2
combo_next combo_nextcombo leavecombo_penaltytime last_action local_runleft has_voice is_speaking
current_voice_audio img_voice char_name stats_hp stats_dmg stats_walkspd stats_airdashspd
stats_runspd stats_jumpforce snd_jump snd_transform hp_draw_y hp_width hp_height
energy_skill1_cost energy_skill2_cost spr_stand spr_crouch spr_charge spr_run spr_walk spr_jump
spr_fall spr_defend spr_fallen spr_hurt spr_hurtup spr_hurtdown spr_transform spr_mask_stand
spr_mask_crouch spr_face imgindex_aura img_index_aura ef_img_aura points_spd use_old_combos stamina
character_shadows x y sprite_index image_index image_speed image_xscale image_yscale image_alpha
hspeed vspeed alarm depth visible object_index id mask_index obj_parent xx yy hit_snd hit_color
hit_spr hforce vforce stats_duration stats_hits stuntime can_knock can_follow can_defend
can_hit_fallen can_hurt delay_hit hit_effect hit_snd_miss charord char chars_num char_title
char_obj char_face char_shop_back char_unlocked char_bought char_stats_hp char_stats_dmg
char_stats_speed char_stats_pwr char_stats_combat char_shop_price char_shop_level
char_shop_needchar char_shop_cond char_shop_chall char_price camera_shake cd_immunity
game_gm game_plrchar'''.split()
FUNCIDS = ['display_get_gui_width', 'display_get_gui_height', 'instance_exists']

def main():
    so, ld_out, h_out = sys.argv[1:4]
    nm = subprocess.run(['nm', '-D', '--defined-only', so], capture_output=True, text=True).stdout
    addr = {}
    for l in nm.splitlines():
        p = l.split()
        if len(p) == 3:
            addr[p[2]] = int(p[0], 16)
    lines, missing = [], []
    for c, m in FUNCS.items():
        if m in addr: lines.append(f'{c} = 0x{addr[m]:x};')
        else: missing.append(m)
    for s in DATA:
        if s in addr: lines.append(f'{s} = 0x{addr[s]:x};')
        else: missing.append(s)
    hdr = ['/* generated by gen_engine.py - engine variable / function-id structs */', '#pragma once']
    for v in VARS:
        s = 'g_VAR_' + v
        if s in addr:
            lines.append(f'{s} = 0x{addr[s]:x};'); hdr.append(f'extern YYVAR {s};')
        else: missing.append(s)
    for f in FUNCIDS:
        s = 'g_FUNC_' + f
        if s in addr:
            lines.append(f'{s} = 0x{addr[s]:x};'); hdr.append(f'extern YYVAR {s};')
        else: missing.append(s)
    if missing:
        print('MISSING:', missing); sys.exit(1)
    open(ld_out, 'w').write('/* generated */\n' + '\n'.join(lines) + '\n')
    open(h_out, 'w').write('\n'.join(hdr) + '\n')
    print('resolved', len(lines), 'symbols')

if __name__ == '__main__':
    main()
