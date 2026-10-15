#!/usr/bin/env bash

echo "================================================================================"
echo "          RELULAYER DIGITAL TWIN ENVIRONMENT DIAGNOSTIC REPORT          "
echo "================================================================================"
echo ""

echo "### 1. System & Architecture Information"
echo "- OS / Kernel: $(uname -sr)"
echo "- WSL Version / Distro: $(cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '"')"
echo "- CPU Info: $(lscpu | grep "Model name" | sed 's/Model name:[ \t]*//')"
echo "- Architecture: $(uname -m)"
echo ""

echo "### 2. NVIDIA GPU & CUDA Acceleration Status"
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,driver_version,memory.total,memory.free --format=csv,noheader
else
    echo "❌ nvidia-smi not found in PATH"
fi
echo ""

echo "### 3. Local Ollama LLM Service Status"
if command -v ollama &> /dev/null; then
    echo "- Ollama Version: $(ollama --version)"
else
    echo "❌ Ollama not found in WSL"
fi
echo ""

echo "### 4. Rust Toolchain & Target Architecture Check"
if command -v rustc &> /dev/null; then
    echo "- Rustc Version: $(rustc --version)"
    echo "- Cargo Version: $(cargo --version)"
    echo "- Installed Compilation Targets:"
    rustup target list | grep "(installed)" | sed 's/^/  * /'
    echo "- Installed Rust Components:"
    rustup component list | grep "(installed)" | sed 's/^/  * /'
    echo "- Cbindgen CLI: $(command -v cbindgen &>/dev/null && cbindgen --version || echo '❌ Not installed')"
else
    echo "❌ Rust toolchain not installed"
fi
echo ""

echo "### 5. Python Environment & Core Packages"
if command -v python3 &> /dev/null; then
    echo "- Python Version: $(python3 --version)"
    echo "- Checking Python Libraries:"
    python3 -c "
libs = ['numpy', 'scipy', 'matplotlib', 'pandas', 'maturin', 'torch']
for lib in libs:
    try:
        m = __import__(lib)
        ver = getattr(m, '__version__', 'Installed')
        print(f'  * {lib}: {ver}')
    except ImportError:
        print(f'  * {lib}: ❌ NOT INSTALLED')
"
else
    echo "❌ Python3 not found"
fi
echo ""

echo "### 6. C/C++ Build System & Simulation Toolchain"
echo "- GCC: $(gcc --version 2>/dev/null | head -n1 || echo '❌ Not installed')"
echo "- Clang: $(clang --version 2>/dev/null | head -n1 || echo '❌ Not installed')"
echo "- CMake: $(cmake --version 2>/dev/null | head -n1 || echo '❌ Not installed')"
echo ""

echo "================================================================================"
echo "                              END OF DIAGNOSTIC REPORT                          "
echo "================================================================================"
