/*
 * Minimal Cortex-M7 startup file for STM32H7 HIL target builds.
 * Provides the vector table and Reset_Handler.
 *
 * This file is intentionally small; production flight software should use the
 * vendor CMSIS startup file for the exact MCU part number.
 */

    .syntax unified
    .cpu cortex-m7
    .fpu fpv5-d16
    .thumb

    .section .vectors, "a", %progbits
    .type __vectors, %object
    .size __vectors, .-__vectors

__vectors:
    .word _estack           /* Top of stack */
    .word Reset_Handler     /* Reset Handler */
    .word Default_Handler   /* NMI */
    .word Default_Handler   /* HardFault */
    .word Default_Handler   /* MemManage */
    .word Default_Handler   /* BusFault */
    .word Default_Handler   /* UsageFault */
    .word 0                 /* Reserved */
    .word 0                 /* Reserved */
    .word 0                 /* Reserved */
    .word 0                 /* Reserved */
    .word Default_Handler   /* SVC */
    .word Default_Handler   /* DebugMon */
    .word 0                 /* Reserved */
    .word Default_Handler   /* PendSV */
    .word Default_Handler   /* SysTick */

    .section .text.Reset_Handler, "ax", %progbits
    .weak Reset_Handler
    .type Reset_Handler, %function

Reset_Handler:
    /* Load data section from flash to RAM */
    ldr r0, =_sdata
    ldr r1, =_edata
    ldr r2, =_sidata
    b   2f
1:
    ldr r3, [r2], #4
    str r3, [r0], #4
2:
    cmp r0, r1
    blo 1b

    /* Zero bss */
    ldr r0, =_sbss
    ldr r1, =_ebss
    movs r2, #0
    b   4f
3:
    str r2, [r0], #4
4:
    cmp r0, r1
    blo 3b

    /* Call main */
    bl main
    b Default_Handler

    .size Reset_Handler, .-Reset_Handler

    .section .text.Default_Handler, "ax", %progbits
    .weak Default_Handler
    .type Default_Handler, %function

Default_Handler:
    b Default_Handler

    .size Default_Handler, .-Default_Handler

    /* Stack top at end of RAM */
    .section .stack, "aw", %nobits
    .equ Stack_Size, 0x00010000
_estack:
    .space Stack_Size
