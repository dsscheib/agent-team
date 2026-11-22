# FDM slicing workflow (OrcaSlicer example)

1. Install OrcaSlicer (or your chosen slicer) from the official release or Flathub and configure your exact printer profile.
2. Inspect firmware type, bed dimensions, nozzle diameter, start/end G-code, temperatures, and material profile.
3. Import exported STL and confirm the units are millimeters and orientation is correct.
4. Review supports, first-layer adhesion, wall count, minimum features, seam, time/material estimates.
5. Preview every layer and check for unsupported bridges, missing features, unwanted toolpaths and collisions.
6. Export G-code only after manual profile review; **do not upload or start a print unattended**.

OrcaSlicer provides a CLI in some distributions but packaging/path/options vary. This bootstrap intentionally does **not** generate or run unattended slicing commands. Validate your installed CLI and trusted profile before adding automated slicing.

Official CLI reference: https://github.com/OrcaSlicer/OrcaSlicer/wiki/cli_mode
