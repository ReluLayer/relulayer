# ReluLayer™ STM32H7 HIL Harness Makefile
# Bare-Metal ARM Cortex-M7 cross-compilation and host regression test.

HIL_DIR      := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
REPO_ROOT    := $(abspath $(HIL_DIR)/../../..)
EMBEDDED_DIR := $(abspath $(HIL_DIR)/../embedded)
INCLUDE_DIR  := $(EMBEDDED_DIR)/include
CORE_TARGET  := $(REPO_ROOT)/10-kernel/relulayer-core/target

# ARM Cortex-M target archive
ARM_LIB      := $(EMBEDDED_DIR)/arm/librelulayer_core.a

# Resolve host archive: test standard release first, then explicit triple
HOST_LIB_STANDARD := $(CORE_TARGET)/release/librelulayer_core.a
HOST_LIB_TRIPLE   := $(CORE_TARGET)/x86_64-unknown-linux-gnu/release/librelulayer_core.a

ifneq ($(wildcard $(HOST_LIB_STANDARD)),)
    HOST_LIB := $(HOST_LIB_STANDARD)
else ifneq ($(wildcard $(HOST_LIB_TRIPLE)),)
    HOST_LIB := $(HOST_LIB_TRIPLE)
else
    # Default fallback if not yet compiled
    HOST_LIB := $(HOST_LIB_STANDARD)
endif

CC_HOST      := gcc
CC_ARM       := arm-none-eabi-gcc
SIZE_ARM     := arm-none-eabi-size

CFLAGS_COMMON := -Wall -Wextra -I$(INCLUDE_DIR) -O2
CFLAGS_ARM    := $(CFLAGS_COMMON) -mcpu=cortex-m7 -mthumb -mfloat-abi=hard -mfpu=fpv5-d16 \
                 -ffunction-sections -fdata-sections

LDFLAGS_ARM   := -T$(HIL_DIR)/stm32h7.ld -nostartfiles -Wl,--gc-sections -Wl,--no-warn-execstack \
                 -L$(EMBEDDED_DIR)/arm -lrelulayer_core \
                 -Wl,--start-group -lc -lm -lnosys -Wl,--end-group

.PHONY: all arm host clean run

all: arm

arm: $(HIL_DIR)/relulayer_hil.elf

$(HIL_DIR)/relulayer_hil.elf: $(HIL_DIR)/relulayer_hil.c $(HIL_DIR)/syscalls.c $(HIL_DIR)/startup_stm32h7.S $(ARM_LIB) $(INCLUDE_DIR)/relulayer.h
	@if ! command -v $(CC_ARM) >/dev/null 2>&1; then \
		echo "ERROR: $(CC_ARM) not installed. Install gcc-arm-none-eabi."; \
		exit 1; \
	fi
	$(CC_ARM) $(CFLAGS_ARM) $(HIL_DIR)/relulayer_hil.c $(HIL_DIR)/syscalls.c $(HIL_DIR)/startup_stm32h7.S $(LDFLAGS_ARM) -o $@
	@echo ""
	@echo "=== STM32H7 ELF Memory Map Footprint ==="
	$(SIZE_ARM) $@

host: $(HIL_DIR)/relulayer_hil_host

$(HIL_DIR)/relulayer_hil_host: $(HIL_DIR)/relulayer_hil.c $(HOST_LIB) $(INCLUDE_DIR)/relulayer.h
	$(CC_HOST) $(CFLAGS_COMMON) $< $(HOST_LIB) -lpthread -ldl -lm -o $@

run: host
	$(HIL_DIR)/relulayer_hil_host

clean:
	rm -f $(HIL_DIR)/relulayer_hil_host $(HIL_DIR)/relulayer_hil.elf
