#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

MIN_FREE_GB="${MITIGATE_MIN_FREE_DISK_GB:-12}"
LOW_MEMORY_THRESHOLD_GB="${MITIGATE_LOW_MEMORY_THRESHOLD_GB:-8}"
REQUIRED_SWAP_GB="${MITIGATE_REQUIRED_SWAP_GB:-4}"
SWAPFILE="${MITIGATE_SWAPFILE:-/swapfile}"

[[ "$EUID" -eq 0 ]] || {
    echo "ERROR: Run with sudo/root." >&2
    exit 1
}

FREE_KB="$(df -Pk / | awk 'NR==2 {print $4}')"
FREE_GB=$((FREE_KB / 1024 / 1024))

if (( FREE_GB < MIN_FREE_GB )); then
    echo "ERROR: Only ${FREE_GB}GB free disk; ${MIN_FREE_GB}GB required." >&2
    exit 20
fi

RAM_KB="$(awk '/MemTotal:/ {print $2}' /proc/meminfo)"
RAM_GB=$(((RAM_KB + 1024 * 1024 - 1) / 1024 / 1024))

SWAP_KB="$(awk '/SwapTotal:/ {print $2}' /proc/meminfo)"
SWAP_GB=$((SWAP_KB / 1024 / 1024))

echo "RAM_GB=$RAM_GB"
echo "SWAP_GB=$SWAP_GB"
echo "FREE_DISK_GB=$FREE_GB"

if (( RAM_GB < LOW_MEMORY_THRESHOLD_GB && SWAP_GB < REQUIRED_SWAP_GB )); then
    echo "Creating ${REQUIRED_SWAP_GB}GB permanent swap."

    if swapon --show=NAME --noheadings | grep -qx "$SWAPFILE"; then
        swapoff "$SWAPFILE"
    fi

    rm -f "$SWAPFILE"
    fallocate -l "${REQUIRED_SWAP_GB}G" "$SWAPFILE"
    chmod 600 "$SWAPFILE"
    mkswap "$SWAPFILE" >/dev/null
    swapon "$SWAPFILE"

    if ! grep -qE "^${SWAPFILE}[[:space:]]" /etc/fstab; then
        printf '%s none swap sw 0 0\n' "$SWAPFILE" >> /etc/fstab
    fi
fi

echo "HOST_RESOURCE_PREFLIGHT=OK"
