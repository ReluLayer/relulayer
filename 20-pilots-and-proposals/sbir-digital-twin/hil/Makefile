# ReluLayer C HIL Driver Harness Makefile
# Host (x86_64) regression build and ARM embedded cross-compile stub.

ROOT        := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))/..
HIL_DIR     := $(ROOT)/hil
INCLUDE_DIR := $(ROOT)/include

# Host staticlib produced by `cargo build -p relulayer-ffi --release`
HOST_LIB    := $(ROOT)/target/release/librelulayer_ffi.a

# ARM staticlib produced by `cargo build --target thumbv7em-none-eabihf -p relulayer-ffi --release`
ARM_LIB     := $(ROOT)/target/thumbv7em-none-eabihf/release/librelulayer_ffi.a

CC_HOST     := gcc
CFLAGS      := -Wall -Wextra -Werror -I$(INCLUDE_DIR) -O2

.PHONY: all host arm clean run

all: host

host: $(HIL_DIR)/relulayer_hil_host

$(HIL_DIR)/relulayer_hil_host: $(HIL_DIR)/relulayer_hil.c $(HOST_LIB) $(INCLUDE_DIR)/relulayer.h
	$(CC_HOST) $(CFLAGS) $< $(HOST_LIB) -o $@ -lm

arm: $(HIL_DIR)/relulayer_hil.elf

$(HIL_DIR)/relulayer_hil.elf: $(HIL_DIR)/relulayer_hil.c $(HIL_DIR)/syscalls.c $(HIL_DIR)/startup_stm32h7.S $(ARM_LIB) $(INCLUDE_DIR)/relulayer.h
	@if ! command -v arm-none-eabi-gcc >/dev/null 2>&1; then \
		echo "ERROR: arm-none-eabi-gcc not installed. Install gcc-arm-none-eabi to build the ARM HIL binary." ; \
		exit 1 ; \
	fi
	arm-none-eabi-gcc $(CFLAGS) -mcpu=cortex-m7 -mthumb -mfloat-abi=hard -mfpu=fpv5-d16 \
		-T$(HIL_DIR)/stm32h7.ld -nostartfiles -Wl,--gc-sections -Wl,--no-warn-execstack \
		$(HIL_DIR)/relulayer_hil.c $(HIL_DIR)/syscalls.c $(HIL_DIR)/startup_stm32h7.S $(ARM_LIB) -o $@ \
		-Wl,--start-group -lc -lm -lnosys -Wl,--end-group

run: host
	$(HIL_DIR)/relulayer_hil_host

clean:
	rm -f $(HIL_DIR)/relulayer_hil_host $(HIL_DIR)/relulayer_hil.elf
