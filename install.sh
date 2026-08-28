#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KLIPPER_ROOT="${KLIPPER_ROOT:-/home/mks/klipper}"
KLIPPY_ENV="${KLIPPY_ENV:-/home/qidi/klippy-env}"
PRINTER_CFG="${PRINTER_CFG:-/home/mks/printer_data/config/printer.cfg}"
CONFIG_DIR="$(dirname "$PRINTER_CFG")"
STAMP="$(date +%Y%m%d-%H%M%S)"
RESTART=0

if [[ "${1:-}" == "--restart" ]]; then RESTART=1; fi

for p in "$KLIPPER_ROOT/klippy/extras" "$KLIPPY_ENV/bin/python" "$PRINTER_CFG"; do
  [[ -e "$p" ]] || { echo "missing required QIDI path: $p" >&2; exit 2; }
done

"$KLIPPY_ENV/bin/python" - <<'PY'
import numpy
print("numpy", numpy.__version__)
PY

# The validated WOBBLE=0.14 protocol needs a deliberately enlarged Klipper
# composite-extrusion guard. Never edit this safety setting silently.
MAX_XSEC="$($KLIPPY_ENV/bin/python - "$PRINTER_CFG" <<'PY'
import re, sys
p=sys.argv[1]
section=None
value=None
for raw in open(p, encoding='utf-8', errors='ignore'):
    line=raw.split('#',1)[0].strip()
    if not line: continue
    m=re.match(r'^\[([^]]+)\]$', line)
    if m:
        section=m.group(1).strip().lower(); continue
    if section=='extruder' and ':' in line:
        k,v=line.split(':',1)
        if k.strip().lower()=='max_extrude_cross_section':
            try: value=float(v.strip())
            except ValueError: pass
print('' if value is None else value)
PY
)"

if [[ -z "$MAX_XSEC" ]]; then
  echo "[extruder] max_extrude_cross_section is not explicitly configured." >&2
  echo "Production APA requires >= 320 for the validated in-air protocol." >&2
  echo "Read docs/SAFETY.md before changing this Klipper safety guard." >&2
  exit 3
fi
"$KLIPPY_ENV/bin/python" - "$MAX_XSEC" <<'PY'
import sys
v=float(sys.argv[1])
if v < 320:
    raise SystemExit("max_extrude_cross_section %.3f is below production requirement 320" % v)
print("max_extrude_cross_section", v, "OK")
PY

mkdir -p "$CONFIG_DIR" /home/mks/printer_data/autopa/captures /home/mks/printer_data/autopa/apa-runs

if [[ -e "$KLIPPER_ROOT/klippy/extras/autopa" ]]; then
  cp -a "$KLIPPER_ROOT/klippy/extras/autopa" "$KLIPPER_ROOT/klippy/extras/autopa.pre-q2-apa-$STAMP"
fi
if [[ -e "$KLIPPER_ROOT/klippy/extras/q2_loadcell.py" ]]; then
  cp -a "$KLIPPER_ROOT/klippy/extras/q2_loadcell.py" "$KLIPPER_ROOT/klippy/extras/q2_loadcell.py.pre-q2-apa-$STAMP"
fi
cp -a "$PRINTER_CFG" "$PRINTER_CFG.pre-q2-apa-$STAMP"

rm -rf "$KLIPPER_ROOT/klippy/extras/autopa"
cp -a "$ROOT/runtime/autopa" "$KLIPPER_ROOT/klippy/extras/autopa"
cp -a "$ROOT/runtime/klipper/q2_loadcell.py" "$KLIPPER_ROOT/klippy/extras/q2_loadcell.py"
cp -a "$ROOT/config/q2-autopa.cfg" "$CONFIG_DIR/q2-autopa.cfg"

if ! grep -Eq '^\s*\[include\s+q2-autopa\.cfg\]\s*$' "$PRINTER_CFG"; then
  printf '\n# QIDI Q2 load-cell AutoPA\n[include q2-autopa.cfg]\n' >> "$PRINTER_CFG"
fi

chmod +x "$ROOT/tools/q2_apa_pipeline.py" "$ROOT/tools/q2_apa_analysis.py" || true

echo "Installed Q2 APA runtime. Backup: $PRINTER_CFG.pre-q2-apa-$STAMP"
if (( RESTART )); then
  sudo systemctl restart klipper
  echo "Klipper restart requested. Run tools/q2_apa_pipeline.py preflight after it is ready."
else
  echo "Restart Klipper before calibration (for example: sudo systemctl restart klipper)."
fi
