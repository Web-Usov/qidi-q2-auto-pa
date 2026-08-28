# Install / upgrade / rollback

This guide is for the QIDI Q2 environment validated during the project.

## Expected Q2 paths

```text
Klipper source: /home/mks/klipper
Klippy venv:    /home/qidi/klippy-env
printer.cfg:    /home/mks/printer_data/config/printer.cfg
captures:       /home/mks/printer_data/autopa/captures
run results:    /home/mks/printer_data/autopa/apa-runs
Moonraker:      http://127.0.0.1
```

If your Q2 differs, set `KLIPPER_ROOT`, `KLIPPY_ENV` and/or `PRINTER_CFG` when running the installer and review the code before proceeding.

## 1. Prepare `printer.cfg`

The production protocol requires an explicitly configured composite-extrusion guard:

```ini
[extruder]
# existing extruder settings...
max_extrude_cross_section: 320
```

A higher existing value also passes.

Read `SAFETY.md` first: this weakens a genuine Klipper protection. `install.sh` deliberately refuses to edit it for you.

## 2. Checkout production branch

On a machine that can reach the repository:

```bash
git clone -b production https://github.com/Web-Usov/qidi-q2-auto-pa.git
cd qidi-q2-auto-pa
```

If the Q2 itself cannot access GitHub, copy the `production` working tree to it with `scp`/`rsync`; the runtime has no GitHub dependency after installation.

## 3. Run installer

On the Q2:

```bash
chmod +x install.sh
./install.sh
```

The installer checks before changing files:

- QIDI Klipper paths exist;
- the Klippy Python environment exists;
- NumPy imports successfully;
- `printer.cfg` exists;
- `[extruder] max_extrude_cross_section >= 320`.

It then:

1. backs up existing AutoPA runtime, `q2_loadcell.py` and `printer.cfg`;
2. installs `runtime/autopa/` to `/home/mks/klipper/klippy/extras/autopa/`;
3. installs `runtime/klipper/q2_loadcell.py` to Klipper extras;
4. installs `config/q2-autopa.cfg` beside `printer.cfg`;
5. adds `[include q2-autopa.cfg]` only if that include is not already present;
6. creates capture/run directories.

It does not restart Klipper unless called with `--restart`.

## 4. Restart and verify

```bash
sudo systemctl restart klipper
```

Wait for Klipper to become ready, then:

```bash
/home/qidi/klippy-env/bin/python tools/q2_apa_pipeline.py preflight
```

Also verify from the printer console that these commands exist:

```text
QPA_SENSOR_TEST
AUTOPA_SWEEP
```

`AUTOPA_DECAY` is intentionally not part of the production APA runtime.

## Configuration installed

`q2-autopa.cfg` contains:

```ini
[q2_loadcell]
poll_hz: 40
samples_per_second: 40
tare_time: 0.35

[autopa]
capture_dir: /home/mks/printer_data/autopa/captures
profile_path: /home/mks/printer_data/autopa/profiles.json
save_captures: True
sweep_min_segment_samples: 12
sweep_min_segment_rate_hz: 35
```

Do not replace your complete QIDI `printer.cfg` with a research snapshot from `master`.

## Upgrade

Pull/copy a newer `production` tree and run `./install.sh` again. Every install creates timestamped backups before replacing the runtime.

Re-run `preflight` after the Klipper restart before calibration.

## Rollback

The installer prints the timestamp of its backups. To rollback, stop Klipper, restore the matching timestamped files, and restart.

Example pattern:

```bash
sudo systemctl stop klipper
rm -rf /home/mks/klipper/klippy/extras/autopa
mv /home/mks/klipper/klippy/extras/autopa.pre-q2-apa-<timestamp> \
   /home/mks/klipper/klippy/extras/autopa
cp /home/mks/klipper/klippy/extras/q2_loadcell.py.pre-q2-apa-<timestamp> \
   /home/mks/klipper/klippy/extras/q2_loadcell.py
cp /home/mks/printer_data/config/printer.cfg.pre-q2-apa-<timestamp> \
   /home/mks/printer_data/config/printer.cfg
sudo systemctl start klipper
```

If there was no previous AutoPA installation, remove the installed `autopa` directory, `q2_loadcell.py`, and the include line/config file instead of restoring nonexistent backups.

## Dependency note

The estimator is NumPy-only. The production installer does **not** automatically download Python packages from the internet. If NumPy is absent, installation stops so the dependency can be handled explicitly in the QIDI Klippy environment rather than silently changing it.
