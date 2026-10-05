/*
 * Minimal linker script for STM32H7xx (Cortex-M7) HIL target builds.
 * Adjust memory regions for the specific flight controller (Pixhawk 6X, STM32H743).
 *
 * STM32H743: 2 MB flash @ 0x0800_0000, 1 MB RAM (864 KB main + 192 KB DTCM + 64 KB ITCM).
 * This script keeps only the main AXI SRAM region for simplicity.
 */

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 2048K
    RAM (rwx)   : ORIGIN = 0x24000000, LENGTH = 512K
}

ENTRY(Reset_Handler)

SECTIONS
{
    .text :
    {
        KEEP(*(.vectors))
        *(.text*)
        *(.rodata*)
        . = ALIGN(4);
    } > FLASH

    .data :
    {
        . = ALIGN(4);
        _sdata = .;
        *(.data*)
        . = ALIGN(4);
        _edata = .;
    } > RAM AT > FLASH

    _sidata = LOADADDR(.data);

    .bss :
    {
        . = ALIGN(4);
        _sbss = .;
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        _ebss = .;
        _end = .;
        PROVIDE(end = .);
    } > RAM

    /DISCARD/ :
    {
        *(.comment)
        *(.ARM.attributes)
    }
}
