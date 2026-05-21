#!/usr/bin/env bash
set -euo pipefail

SOURCE_FILE="${1:-config/sudoers/kkgroup-mutual-rescue}"
TARGET_FILE="/etc/sudoers.d/kkgroup-mutual-rescue"

if [[ ! -f "$SOURCE_FILE" ]]; then
  echo "sudoers source file not found: $SOURCE_FILE" >&2
  exit 1
fi

tmp_file="$(mktemp)"
cp "$SOURCE_FILE" "$tmp_file"
chmod 0440 "$tmp_file"

if ! visudo -cf "$tmp_file"; then
  rm -f "$tmp_file"
  echo "sudoers validation failed; not installing" >&2
  exit 1
fi

install -o root -g root -m 0440 "$tmp_file" "$TARGET_FILE"
rm -f "$tmp_file"
visudo -cf "$TARGET_FILE"
echo "Installed $TARGET_FILE"
