import sys
from typing import Callable

from game_ocr import capture
from game_ocr.capture import CaptureBackend, CaptureError, WindowInfo
from game_ocr.settings import GameOcrSettings
from language import Language

# Asks the user to choose a window from a list of windows
def choose_window(windows: list[WindowInfo], query: str | None, ask: Callable[[str], str] = input) -> WindowInfo:
    if not windows:
        raise CaptureError("No capturable window found: is the game open (and not minimized)?")
    if query:
        needle = query.lower()
        matches = [w for w in windows if needle in w.label.lower()]
        if not matches:
            raise CaptureError(f"No window matches '{query}'. Open windows:\n" + "\n".join(f"  {w.label}" for w in windows))
        return matches[0]
    for i, window in enumerate(windows, 1):
        print(f"  {i:2d}. {window.label}")
    while True:
        answer = ask(f"Window number [1-{len(windows)}]: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(windows):
            return windows[int(answer) - 1]
        print("  Invalid choice.")


# Asks the user for the game window: through the OS dialog (Wayland portal), or from a list MiningCat prints (macOS).
def select_window(backend: CaptureBackend, settings: GameOcrSettings, query: str | None = None) -> None:
    info = capture.backend_info()
    if backend.has_system_picker:
        print("A system dialog will ask which window to share: pick the game window.", flush=True)
        backend.select_window()
    else:
        backend.select_window(choose_window(backend.list_windows(), query))
    settings.set_window(info.id, backend.state, backend.window_label)
    settings.save()
    print(f"Window: {settings.window_label}")

# Asks the user to select the screenshot and text areas, and saves them in the settings.
def select_areas(backend: CaptureBackend, settings: GameOcrSettings) -> bool:
    from gui_components.game_dialogs import SCREENSHOT_AREA_TITLE, TEXT_AREA_TITLE, pick_region_standalone
    from game_ocr.session import crop_region

    frame = backend.grab_frame()
    screenshot_region = pick_region_standalone(frame, SCREENSHOT_AREA_TITLE, initial_region=settings.screenshot_region)
    if screenshot_region is None:
        return False
    settings.set_screenshot_region(screenshot_region)
    text_region = pick_region_standalone(
        crop_region(frame, screenshot_region), TEXT_AREA_TITLE, initial_region=settings.text_region,
    )
    if text_region is None:
        settings.save()
        return False
    settings.text_region = text_region
    settings.save()
    print(f"Screenshot area: {tuple(round(v, 3) for v in screenshot_region)}")
    print(f"Text area:       {tuple(round(v, 3) for v in text_region)}")
    return True


def setup(window_query: str | None = None, areas_only: bool = False) -> None:
    from game_ocr.session import open_saved_window

    settings = GameOcrSettings.load()
    info = capture.backend_info()
    print(f"Capture backend: {info.label if info else sys.platform + ' (unsupported)'}")
    if areas_only:
        backend = open_saved_window(settings)
    else:
        backend = capture.create_backend()
    with backend:
        if not areas_only:
            select_window(backend, settings, window_query)
        if not select_areas(backend, settings):
            sys.exit("Selection cancelled.")
    print("Done. Now run: python src/main.py game serve")


def serve(
    language: Language,
    convert_target: str | None = None,
    port: int | None = None,
    auto: bool = False,
    hotkey: str | None = None,
    interval: float | None = None,
    join: bool = True,
    open_browser: bool = True,
) -> None:
    from game_ocr import server
    from game_ocr.hotkey import HotkeyError, create_hotkey
    from game_ocr.session import GameOcrSession, open_saved_window

    settings = GameOcrSettings.load()
    if not settings.is_ready:
        sys.exit("No window or text area selected yet. Run first: python src/main.py game setup")
    port = port or server.DEFAULT_PORT
    interval = interval or server.DEFAULT_INTERVAL_S

    backend = open_saved_window(settings)
    try:
        print(f"Window:    {settings.window_label}")
        print(f"Language:  {language.value.label}")
        print("Loading the OCR engine…", flush=True)
        session = GameOcrSession(backend, settings, language, convert_target=convert_target, join=join)
        # Continuous capture replaces the capture key.
        key = None
        if not auto and hotkey:
            try:
                key = create_hotkey(hotkey)
            except HotkeyError as exc:
                print(f"[capture key] {exc}", flush=True)
        app = server.create_app(session, language, auto=auto, interval=interval, hotkey=key, port=port)
        print(f"Mode:      {'continuous, every ' + str(interval) + ' s' if auto else 'capture key ' + (hotkey or 'off')}")
        print(f"Page:      {server.page_url(port)}")
        print(f"Capture:   curl -X POST {server.page_url(port)}capture", flush=True)
        server.run(app, port=port, open_browser=open_browser)
    finally:
        backend.close()


def main(args) -> None:
    try:
        if args.game_command == "setup":
            setup(window_query=args.window, areas_only=args.areas_only)
        else:
            serve(
                language=Language.from_id(args.language),
                convert_target=args.convert_to,
                port=args.port,
                auto=args.continuous,
                hotkey=args.hotkey,
                interval=args.interval,
                join=not args.keep_line_breaks,
                open_browser=not args.no_browser,
            )
    except CaptureError as exc:
        sys.exit(f"Error: {exc}")
