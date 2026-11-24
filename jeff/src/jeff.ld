/* Jeff's code is linked at a fixed VA inside libyoyo.so (two new PT_LOAD segments added by
 * build/elfpatch.py). Engine symbols come from the generated engine.ld. */
ENTRY(jeff_initllvm)
INCLUDE engine.ld

/* functions of the existing Coco mod we chain to */
mod_initllvm_hook = 0x3000000;
mod_get_char_hook = 0x3044a70;
mod_charsel_ext   = 0x3043880;

PHDRS {
    text PT_LOAD FLAGS(5);
    data PT_LOAD FLAGS(6);
}

SECTIONS {
    . = 0x3600000;
    /* room for the relocated program header table (written by elfpatch.py) */
    .phdrs : { BYTE(0); . += 0x3ff; } :text
    .text : { *(.text .text.*) } :text
    .rodata : { *(.rodata .rodata.* .srodata*) } :text
    . = 0x3700000;
    .data : { *(.data .data.*) } :data
    .bss : { *(.bss .bss.* COMMON) } :data
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.ARM.*) }
}
