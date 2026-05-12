# crack-programs

User programs for the [CRACK](https://github.com/alunmorris/crack) ESP32-S2 AI device.

## Installing programs

On the device, open the model menu and press **r** to open the file picker. Run
`getprog.py` to browse and download programs from this repository directly to the device.

## Adding your own programs

1. Fork this repo
2. Add your `.py` file
3. Add an entry to `manifest.json`:
   ```json
   {"file": "yourprogram.py", "desc": "Short description"}
   ```
4. Submit a pull request

## Writing programs

See `docs/user_programs.md` in the main CRACK repo for the full API reference —
available globals, ANSI escapes, monospaced terminal, GPIO, and network access.
