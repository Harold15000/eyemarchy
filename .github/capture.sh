#!/bin/bash
# Eyemarchy README captures. Runs on the Omarchy laptop, needs ~2 minutes of
# an untouched screen. Restores theme, wallpaper and workspace at the end.
set -u
export OMARCHY_PATH=/usr/share/omarchy XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1 LANG=C.UTF-8
export PATH=$OMARCHY_PATH/bin:$PATH
export HYPRLAND_INSTANCE_SIGNATURE=$(ls -t "$XDG_RUNTIME_DIR/hypr/" | head -1)

OUT=$HOME/.cache/eyemarchy-shots
rm -rf "$OUT"; mkdir -p "$OUT"
MON=$(hyprctl monitors -j | jq -r '.[0].name')
S=omarchy-shell

prev_theme=$(cat ~/.local/state/omarchy/current/theme.name)
prev_bg=$(readlink ~/.local/state/omarchy/current/background)
prev_ws=$(hyprctl activeworkspace -j | jq -r .id)
echo "theme=$prev_theme ws=$prev_ws bg=$prev_bg" > "$OUT/restore.txt"

restore() {
  $S eyemarchy demo off >/dev/null 2>&1
  $S eyemarchy dismiss >/dev/null 2>&1
  omarchy theme set "$prev_theme" >/dev/null 2>&1
  sleep 2
  [[ -n $prev_bg && -f $prev_bg ]] && omarchy theme bg set "$prev_bg" >/dev/null 2>&1
  hyprctl dispatch "hl.dsp.focus({ workspace = \"$prev_ws\" })" >/dev/null 2>&1
  echo restored
}
trap restore EXIT

ready() { for _ in $(seq 1 60); do $S eyemarchy state >/dev/null 2>&1 && return 0; sleep 0.25; done; return 1; }
press() { $S eyemarchy press "$1" >/dev/null; sleep "${2:-0.7}"; }

# An empty workspace to work on.
hyprctl dispatch 'hl.dsp.focus({ workspace = "9" })' >/dev/null
sleep 1

shot() {
  local theme=$1
  omarchy theme set "$theme" >/dev/null 2>&1
  sleep 2; ready
  $S eyemarchy dismiss >/dev/null
  $S eyemarchy demo on >/dev/null
  sleep 3.5
  grim -o "$MON" "$OUT/$theme.png"
  echo "shot $theme"
}

for t in catppuccin-latte osaka-jade everforest tokyo-night; do shot "$t"; done

# The recording, on the hero theme.
gpu-screen-recorder -w "$MON" -f 30 -o "$OUT/demo.mp4" >/dev/null 2>&1 &
rec=$!
sleep 2.5
press Down 1.4          # the agent that needs you
press Down; press Down; press Down
press Right 1.2         # now playing
press Space 1.0; press Space 1.0
press Right 1.0         # system
press Return 2.2        # what uses the CPU
press Down; press Down 1.2
press Escape 1.0
press Comma 1.8         # settings
press Down; press Down; press Down 1.2
grim -o "$MON" "$OUT/settings.png"
press Escape 1.5
kill -INT $rec; wait $rec 2>/dev/null
echo recorded
