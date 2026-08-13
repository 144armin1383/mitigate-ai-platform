#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

MIN_FREE_GB="${MITIGATE_MIN_FREE_DISK_GB:-12}"
LOW_MEMORY_THRESHOLD_GB="${MITIGATE_LOW_MEMORY_THRESHOLD_GB:-8}"
REQUIRED_SWAP_GB="${MITIGATE_REQUIRED_SWAP_GB:-4}"
PRIMARY_SWAPFILE="${MITIGATE_SWAPFILE:-/swapfile}"
EXTRA_SWAPFILE="${MITIGATE_EXTRA_SWAPFILE:-/swapfile.mitigate}"

[[ "$EUID" -eq 0 ]] || {
    echo "ERROR: Run with sudo/root." >&2
    exit 1
}

FREE_KB="$(df -Pk / | awk 'NR==2 {print $4}')"
REQUIRED_FREE_KB=$((MIN_FREE_GB * 1024 * 1024))

if (( FREE_KB < REQUIRED_FREE_KB )); then
    echo "ERROR: Insufficient disk space." >&2
    exit 20
fi

RAM_KB="$(awk '/MemTotal:/ {print $2}' /proc/meminfo)"
SWAP_KB="$(awk '/SwapTotal:/ {print $2}' /proc/meminfo)"

LOW_MEMORY_KB=$((LOW_MEMORY_THRESHOLD_GB * 1024 * 1024))

# Allow small filesystem/accounting differences around nominal swap size.
MIN_ACCEPTABLE_SWAP_KB=$((REQUIRED_SWAP_GB * 1024 * 1024 * 95 / 100))

echo "RAM_MIB=$((RAM_KB / 1024))"
echo "SWAP_MIB=$((SWAP_KB / 1024))"
echo "FREE_DISK_GB=$((FREE_KB / 1024 / 1024))"

create_swap() {
    local file="$1"
    local size_gb="$2"

    if swapon --show=NAME --noheadings | grep -qx "$file"; then
        return 0
    fi

    if [[ ! -f "$file" ]]; then
        fallocate -l "${size_gb}G" "$file"
        chmod 600 "$file"
        mkswap "$file" >/dev/null
    fi

    swapon "$file"

    if ! grep -qE "^${file}[[:space:]]" /etc/fstab; then
        printf '%s none swap sw 0 0\n' "$file" >> /etc/fstab
    fi
}

if (( RAM_KB < LOW_MEMORY_KB && SWAP_KB < MIN_ACCEPTABLE_SWAP_KB )); then
    if ! swapon --show=NAME --noheadings | grep -qx "$PRIMARY_SWAPFILE"; then
        echo "Creating primary ${REQUIRED_SWAP_GB}GB swap."
        create_swap "$PRIMARY_SWAPFILE" "$REQUIRED_SWAP_GB"
    else
        echo "Existing swap is insufficient; adding supplemental swap."
        create_swap "$EXTRA_SWAPFILE" "$REQUIRED_SWAP_GB"
    fi
fi

echo "HOST_RESOURCE_PREFLIGHT=OK"
