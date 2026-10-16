# SPDX-License-Identifier: Proprietary
# ReluLayer PX4 Mixer Barrier — Sprint 2 Host Build

cmake_minimum_required(VERSION 3.16)
project(px4_mixer_barrier CXX C)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Path to the relulayer-core static library built by cargo.
set(RELULAYER_CORE_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../10-kernel/relulayer-core")
set(RELULAYER_CORE_LIB "${RELULAYER_CORE_ROOT}/target/release/librelulayer_core.a")

if(NOT EXISTS "${RELULAYER_CORE_LIB}")
  message(FATAL_ERROR "librelulayer_core.a not found at ${RELULAYER_CORE_LIB}. Build it with: cargo build --release -p relulayer-core")
endif()

add_library(relulayer_core STATIC IMPORTED)
set_target_properties(relulayer_core PROPERTIES
  IMPORTED_LOCATION "${RELULAYER_CORE_LIB}"
  INTERFACE_INCLUDE_DIRECTORIES "${CMAKE_CURRENT_SOURCE_DIR}/include"
)

add_library(relulayer_barrier STATIC
  src/ReluLayerBarrier.cpp
)

target_include_directories(relulayer_barrier PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

target_link_libraries(relulayer_barrier PUBLIC relulayer_core)

add_executable(test_mixer_interceptor
  tests/test_mixer_interceptor.cpp
)

target_link_libraries(test_mixer_interceptor PRIVATE relulayer_barrier)

if(UNIX AND NOT APPLE)
  # Rust staticlib may pull in compiler builtins / math routines.
  target_link_libraries(test_mixer_interceptor PRIVATE m dl pthread)
endif()

enable_testing()
add_test(NAME mixer_interceptor_host COMMAND test_mixer_interceptor)
