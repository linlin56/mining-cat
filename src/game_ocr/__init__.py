# Video game / screen share OCR: captures a window, reads the text area with OCR,
# and pushes the screenshot + text to a local web page for sentence mining.
#
# capture/   per-OS window capture (Linux Wayland portal, macOS)
# settings   the selected window and areas, persisted in sources/game_ocr.json
# session    crops, OCR (reuses ocr_mining's engine and dedup helpers), change detection
# server     the local web page (aiohttp + websocket)
# cli        `python src/main.py game setup|serve`
#
# Nothing heavy is imported here: the GUI only needs `game_ocr.capture` and `game_ocr.settings`.
