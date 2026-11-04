#!/bin/bash
# Eyemarchy README captures. Runs on an Omarchy machine and needs about two
# minutes of an untouched screen. Restores theme, wallpaper, language and
# workspace at the end, even if something fails.
#
#   .github/capture.sh [hero-theme] [other themes...]
set -u
export OMARCHY_PATH=${OMARCHY_PATH:-/usr/share/omarchy} LANG=C.UTF-8
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$UID}
export WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-$(ls "$XDG_RUNTIME_DIR" | grep -m1 -E '^wayland-[0-9]+$')}
export HYPRLAND_INSTANCE_SIGNATURE=${HYPRLAND_INSTANCE_SIGNATURE:-$(ls -t "$XDG_RUNTIME_DIR/hypr/" | head -1)}
export PATH=$OMARCHY_PATH/bin:$PATH

HERO=${1:-tokyo-night}
shift || true
THEMES=("$@")
(( ${#THEMES[@]} )) || THEMES=(catppuccin-latte gruvbox retro-82)

OUT=$HOME/.cache/eyemarchy-shots
rm -rf "$OUT"; mkdir -p "$OUT"
MON=$(hyprctl monitors -j | jq -r '[.[] | select(.focused)][0].name')
RES=$(hyprctl monitors -j | jq -r '[.[] | select(.focused)][0] | "\(.width)x\(.height)"')
S=omarchy-shell

prev_theme=$(cat ~/.local/state/omarchy/current/theme.name)
prev_bg_name=$(basename "$(readlink ~/.local/state/omarchy/current/background)")
prev_ws=$(hyprctl activeworkspace -j | jq -r .id)
prev_lang=$($S eyemarchy settingsJson | jq -r .language)
echo "theme=$prev_theme bg=$prev_bg_name ws=$prev_ws lang=$prev_lang" > "$OUT/restore.txt"

restore() {
  [[ -n ${rec:-} ]] && kill -INT "$rec" 2>/dev/null
  $S eyemarchy demo off >/dev/null 2>&1
  $S eyemarchy dismiss >/dev/null 2>&1
  $S eyemarchy configure language "$prev_lang" >/dev/null 2>&1
  timeout 40 omarchy theme set "$prev_theme" >/dev/null 2>&1
  sleep 2
  bg=~/.local/state/omarchy/current/theme/backgrounds/$prev_bg_name
  [[ -f $bg ]] && timeout 20 omarchy theme bg set "$bg" >/dev/null 2>&1
  hyprctl dispatch "hl.dsp.focus({ workspace = \"$prev_ws\" })" >/dev/null 2>&1
  echo restored
}
trap restore EXIT

ready() { for _ in $(seq 1 80); do $S eyemarchy state >/dev/null 2>&1 && return 0; sleep 0.25; done; return 1; }
press() { $S eyemarchy press "$1" >/dev/null; sleep "${2:-0.7}"; }

theme() {
  timeout 40 omarchy theme set "$1" >/dev/null 2>&1
  sleep 2; ready
  $S eyemarchy dismiss >/dev/null
  $S eyemarchy press Escape >/dev/null
  $S eyemarchy demo on >/dev/null
  sleep 3.5
}

# An empty workspace to work on, English text.
hyprctl dispatch 'hl.dsp.focus({ workspace = "9" })' >/dev/null
$S eyemarchy configure language en >/dev/null
sleep 1

for t in "${THEMES[@]}" "$HERO"; do
  theme "$t"
  grim -o "$MON" "$OUT/$t.png"
  echo "shot $t"
done

# The recording, on the hero theme.
gpu-screen-recorder -w "$MON" -s "$RES" -k auto -f 30 -fm cfr -cursor no \
  -fallback-cpu-encoding yes -o "$OUT/demo.mp4" >"$OUT/recorder.log" 2>&1 &
rec=$!
sleep 2.5
press Down 1.6          # the agent that needs you comes first
press Down; press Down; press Down 1.0
press Right 1.2         # now playing
press Space 1.0; press Space 1.2
press Right 1.0         # system
press Return 2.4        # what uses the CPU
press Down 0.8; press Down 1.4
press Escape 1.2
press Comma 1.8         # settings
press Down 0.6; press Down 0.6; press Down 1.4
grim -o "$MON" "$OUT/settings.png"
press Escape 1.5
kill -INT $rec; wait $rec 2>/dev/null; rec=
echo recorded
ls -la "$OUT"
