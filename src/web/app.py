import json
import threading
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, render_template, request, send_file

from miningcat.domain.languages import Language
from gui_components.constants import CONVERT_BY_LABEL, PYTHON, ROOT
from web import files, options
from web.state import AppState, JobBusyError

# Mutating requests must carry this header. A web page from another site can't add it without
# a CORS preflight, which this server never approves: it protects the local API from other tabs.
CSRF_HEADER = "X-MiningCat"
_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}


class UserError(Exception):
    """An error meant to be shown to the user in a dialog (like Tkinter's messagebox)."""

    def __init__(self, title: str, message: str, status: int = 400):
        super().__init__(message)
        self.title = title
        self.message = message
        self.status = status


def _language(lang_id) -> Language:
    try:
        return Language.from_id(str(lang_id))
    except ValueError:
        raise UserError("Unknown language", f"Unknown language: {lang_id!r}")


def _convert_target(label, lang: Language) -> str | None:
    if label not in options.convert_labels_for(lang):
        return None
    return CONVERT_BY_LABEL.get(label)


def _model(label, lang: Language) -> str:
    values = options.precision_values_for(lang)
    if label not in values:
        label = options.DEFAULT_PRECISION if options.DEFAULT_PRECISION in values else values[0]
    return options.model_from_precision(label)


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _paths(refs, base: Path | None = None) -> list[Path]:
    try:
        return files.resolve_refs(refs or [], base)
    except files.InvalidPathError as exc:
        raise UserError("File not available", str(exc))


def _selected_chapters(indices, total: int) -> list[int]:
    if not isinstance(indices, list):
        return []
    return sorted({i for i in indices if isinstance(i, int) and 0 <= i < total})


def _ocr_region(value) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    try:
        region = tuple(float(v) for v in value)
    except (TypeError, ValueError):
        raise UserError("Invalid region", "The subtitle region is invalid.")
    if len(region) != 4 or not all(0.0 <= v <= 1.0 for v in region) or region[2] <= 0 or region[3] <= 0:
        raise UserError("Invalid region", "The subtitle region is invalid.")
    return region


def create_app(state: AppState | None = None) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    state = state or AppState()
    app.extensions["miningcat"] = state
    from web.reader import bp as reader_bp
    from web.mining_api import bp as mining_bp
    from web.game import bp as game_bp
    from web.player import bp as player_bp
    from web import profile
    app.register_blueprint(profile.bp)
    app.register_blueprint(reader_bp)
    app.register_blueprint(mining_bp)
    app.register_blueprint(game_bp)
    app.register_blueprint(player_bp)
    app.extensions["miningcat-game-frame"] = {"data": None, "version": 0}
    ocr_preview: dict = {"frames": [], "version": 0}

    @app.before_request
    def _guard():
        host = urlparse(f"//{request.host}").hostname or ""
        if host not in _LOCAL_HOSTNAMES:
            return jsonify(error="MiningCat only answers on localhost."), 403
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != "1":
            return jsonify(error="Missing MiningCat header."), 403
        return profile.guard()

    # The language studied, for every page's header (see web/profile.py).
    @app.context_processor
    def _study_language():
        return {"study": profile.describe(profile.current())}

    @app.errorhandler(UserError)
    def _user_error(exc: UserError):
        return jsonify(title=exc.title, error=exc.message), exc.status

    # ---------- pages & settings ----------

    # Home: the user chooses the language they study, then a screen.
    @app.get("/")
    def home():
        return render_template("home.html")

    @app.get("/converter/")
    def converter():
        return render_template("converter.html")

    # Video game captures, with the dictionary popup and the card creator (see web/game.py).
    @app.get("/game/")
    def game_page():
        return render_template("game.html")

    # Clipboard: a text typed or pasted by the user, then read with the dictionary popup (static/clipboard.js).
    @app.get("/clipboard/")
    def clipboard_page():
        return render_template("clipboard.html")

    @app.get("/api/options")
    def api_options():
        return jsonify(options.all_options(profile.current()))

    @app.get("/api/state")
    def api_state():
        return jsonify(job=state.snapshot(), files=files.preload())

    @app.get("/api/events")
    def api_events():
        try:
            last_id = int(request.headers.get("Last-Event-ID") or request.args.get("last") or 0)
        except ValueError:
            last_id = 0

        def stream():
            yield "retry: 2000\n\n"
            for item in state.bus.follow(last_id):
                if item is None:
                    yield ": keep-alive\n\n"
                    continue
                event_id, event = item
                yield f"id: {event_id}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

        return Response(stream(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ---------- files ----------

    @app.post("/api/upload/<kind>")
    def api_upload(kind: str):
        from config import AUDIO_EXTENSIONS

        extensions = {
            "audio": AUDIO_EXTENSIONS,
            "ebook": options.EBOOK_EXTENSIONS,
            "video": options.VIDEO_EXTENSIONS,
        }.get(kind)
        if extensions is None:
            raise UserError("Upload failed", f"Unknown file kind: {kind}", 404)
        saved, rejected = files.save_uploads(kind, request.files.getlist("files"), extensions)
        return jsonify(files=saved, rejected=rejected)

    @app.post("/api/discard")
    def api_discard():
        try:
            removed = files.discard(_body().get("path"))
        except files.InvalidPathError as exc:
            raise UserError("File not available", str(exc))
        return jsonify(removed=removed)

    @app.post("/api/chapters")
    def api_chapters():
        paths = files.normalize_ebook_selection(_paths(_body().get("files")))
        try:
            chapters = files.load_chapters(paths)
            error = None
        except Exception as exc:
            chapters, error = [], f"Could not read the book: {exc}"
        return jsonify(
            files=[files.describe(p) for p in paths],
            chapters=[{"index": i, "title": title} for i, (title, _) in enumerate(chapters)],
            error=error,
        )

    # ---------- video helpers ----------

    @app.post("/api/video/tracks")
    def api_video_tracks():
        video_file = _paths([_body().get("path")])[0]
        try:
            import video
            tracks = video.list_audio_tracks(video_file)
        except Exception:
            tracks = []
        return jsonify(tracks=[{"index": t["index"], "label": options.audio_track_label(t)} for t in tracks])

    @app.post("/api/video/validate")
    def api_video_validate():
        body = _body()
        return jsonify(error=options.validate_video_url(str(body.get("url") or "").strip(), body.get("website")))

    # Grabs a carousel of candidate frames for the subtitle region picker. For a URL the video is
    # downloaded first (yt-dlp then skips re-downloading it when the video is generated).
    @app.post("/api/ocr/preview")
    def api_ocr_preview():
        body = _body()
        from config import DIR_TEMP, DIR_VIDEOS
        from ocr_mining import frames

        if body.get("path"):
            video_file = _paths([body["path"]])[0]
        else:
            url = str(body.get("url") or "").strip()
            if not url:
                raise UserError("Missing URL", "Enter a video URL.")
            try:
                import video_downloader
                video_file = video_downloader.download_video(url, DIR_VIDEOS, app_id="web")
            except Exception as exc:
                raise UserError("Download failed", f"Could not download the video for preview:\n{exc}")
        try:
            preview_paths = frames.grab_sample_frames(video_file, DIR_TEMP / "ocr_region_preview")
            width, height = frames.probe_dimensions(video_file)
        except Exception as exc:
            raise UserError("Preview failed", f"Could not load preview frames:\n{exc}")
        ocr_preview["frames"] = [Path(p) for p in preview_paths]
        ocr_preview["version"] += 1
        version = ocr_preview["version"]
        return jsonify(
            width=width, height=height,
            frames=[f"/api/ocr/frame/{i}?v={version}" for i in range(len(preview_paths))],
        )

    @app.get("/api/ocr/frame/<int:index>")
    def api_ocr_frame(index: int):
        frame_list = ocr_preview["frames"]
        if not 0 <= index < len(frame_list) or not frame_list[index].is_file():
            return jsonify(error="Frame not found"), 404
        return send_file(frame_list[index], mimetype="image/jpeg", max_age=0)

    # ---------- pipelines ----------

    @app.post("/api/run/audiobook")
    def api_run_audiobook():
        from gui_components import pipeline

        body = _body()
        mode = body.get("mode")
        if mode not in options.MODES:
            raise UserError("Unknown mode", f"Unknown mode: {mode!r}")
        lang = _language(body.get("language"))
        audio_files = _paths(body.get("audio")) if mode != "Generate audio" else []
        ebook_files = files.normalize_ebook_selection(_paths(body.get("ebook"))) if mode != "Generate subtitles" else []

        if mode != "Generate audio" and not audio_files:
            raise UserError("Missing files", "Add at least one audio file (MP3 or M4B).")
        if mode != "Generate subtitles" and not ebook_files:
            raise UserError("Missing file", "Select an EPUB or TXT file.")

        chapters: list[tuple[str, str]] = []
        selected: list[int] = []
        if mode != "Generate subtitles":
            try:
                chapters = files.load_chapters(ebook_files)
            except Exception:
                chapters = []
            selected = _selected_chapters(body.get("chapters"), len(chapters))
            if chapters and not selected:
                raise UserError("No chapters selected", "Select at least one chapter.")

        voice = body.get("voice")
        if mode == "Generate audio" and lang.profile.voice_id(voice) is None:
            raise UserError("Missing voice", "Pick a voice.")

        def on_done() -> None:
            state.bus.publish({"type": "done", "kind": "audiobook"})

        try:
            state.start_job(
                "audiobook", pipeline.run_pipeline, on_done,
                python_exe=PYTHON,
                mode=mode,
                lang=lang,
                model=_model(body.get("precision"), lang),
                convert_target=_convert_target(body.get("convert"), lang),
                voice_label=voice or "",
                audio_files=audio_files,
                epub_files=ebook_files,
                epub_chapters=chapters,
                selected_chapters=selected,
            )
        except JobBusyError as exc:
            raise UserError("Busy", str(exc), 409)
        return jsonify(started=True)

    @app.post("/api/run/video")
    def api_run_video():
        from gui_components import pipeline

        body = _body()
        lang = _language(body.get("language"))
        is_local = body.get("input_mode") == "Local file"
        video_file = None
        url = None
        audio_track = None
        if is_local:
            if not body.get("path"):
                raise UserError("Missing file", "Select a local video file.")
            video_file = _paths([body["path"]])[0]
            if isinstance(body.get("audio_track"), int):
                audio_track = body["audio_track"]
        else:
            url = str(body.get("url") or "").strip()
            if not url:
                raise UserError("Missing URL", "Enter a video URL.")
            url_error = options.validate_video_url(url, body.get("website"))
            if url_error:
                raise UserError("URL mismatch", url_error)

        from ocr_mining.frames import OCR_FPS_DEFAULT, OCR_FPS_MAX, OCR_FPS_MIN

        use_ocr = bool(body.get("ocr"))
        try:
            ocr_fps = int(body.get("ocr_fps", OCR_FPS_DEFAULT))
        except (TypeError, ValueError):
            ocr_fps = OCR_FPS_DEFAULT
        ocr_fps = max(OCR_FPS_MIN, min(OCR_FPS_MAX, ocr_fps))

        def on_done(srt_path: Path | None) -> None:
            state.last_video_srt = srt_path
            state.bus.publish({"type": "done", "kind": "video", "has_srt": srt_path is not None})

        try:
            state.start_job(
                "video", pipeline.run_video_pipeline, on_done,
                python_exe=PYTHON,
                lang=lang,
                model=_model(body.get("precision"), lang),
                convert_target=_convert_target(body.get("convert"), lang),
                url=url,
                video_path=video_file,
                audio_track=audio_track,
                use_ocr=use_ocr,
                ocr_region=_ocr_region(body.get("ocr_region")) if use_ocr else None,
                ocr_fps=ocr_fps,
            )
        except JobBusyError as exc:
            raise UserError("Busy", str(exc), 409)
        return jsonify(started=True)

    # ---------- frequency lists ----------

    @app.post("/api/frequency")
    def api_frequency():
        from frequency import character_frequency, word_frequency
        from gui_components.utils import srt_to_text

        body = _body()
        kind = body.get("kind")
        if kind not in ("word", "char"):
            raise UserError("Unknown list", f"Unknown frequency list: {kind!r}")
        lang = _language(body.get("language"))
        if kind == "char" and not character_frequency.supports_language(lang):
            raise UserError("Not supported", f"Character lists are not available for {lang.profile.label}.")

        if body.get("source") == "video":
            srt_path = state.last_video_srt
            if srt_path is None or not srt_path.exists():
                raise UserError("No video processed", "Generate a video first.")
            text = srt_to_text(srt_path)
            stem = srt_path.stem
        else:
            ebook_files = files.normalize_ebook_selection(_paths(body.get("ebook")))
            if not ebook_files:
                raise UserError("No chapters", "Load an EPUB or TXT file first.")
            all_chapters = files.load_chapters(ebook_files)
            if not all_chapters:
                raise UserError("No chapters", "Load an EPUB or TXT file first.")
            selected = _selected_chapters(body.get("chapters"), len(all_chapters))
            if not selected:
                raise UserError("No chapters selected", "Select at least one chapter.")
            text = "\n".join(all_chapters[i][1] for i in selected)
            stem = ebook_files[0].stem

        out_dir = ROOT / "output" / "frequency"
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            if kind == "word":
                counter = word_frequency.compute(text, lang)
                out_path = out_dir / f"{stem}_word_freq.csv"
                word_frequency.save_csv(counter, out_path)
                total = word_frequency.total_count(counter)
                message = f"Word frequency saved ({len(counter)} unique words, {total} total words)."
                state.info(f"Word frequency: {len(counter)} unique words, {total} total words : {out_path}\n")
            else:
                counter = character_frequency.compute(text, lang)
                data = character_frequency.build_json(stem, lang, counter)
                out_path = out_dir / f"{stem}_char_list.json"
                character_frequency.save_json(data, out_path)
                message = f"Character list saved ({len(counter)} unique characters)."
                state.info(f"Character list: {len(counter)} unique characters → {out_path}\n")
        except Exception as exc:
            label = "Word frequency" if kind == "word" else "Character list"
            state.info(f"{label} error: {exc}\n")
            raise UserError(f"{label} error", str(exc), 500)
        return jsonify(message=message, path=str(out_path))

    # ---------- reader ----------

    # After a conversion: imports its book into the reader's library, with the chapters' audio and subtitles.
    @app.post("/api/reader/from-output")
    def api_reader_from_output():
        from web import book_audio, books

        if state.running:
            raise UserError("Busy", "Wait for the current job to finish.", 409)
        ebook_files = files.normalize_ebook_selection(_paths(_body().get("ebook")))
        if not ebook_files:
            raise UserError("No book", "This conversion has no book to open in the reader.")
        source = ebook_files[0]
        try:
            meta = books.import_book(source.name, source.read_bytes())
            audio = book_audio.attach_from_output(meta["id"])
        except (books.BookError, book_audio.AudioError) as exc:
            raise UserError("Reader", str(exc))
        return jsonify(id=meta["id"], audio=audio)

    # After a video conversion: imports its video, with the subtitles it now carries, into the player's library.
    @app.post("/api/player/from-output")
    def api_player_from_output():
        from config import DIR_FINAL
        from web import videos

        if state.running:
            raise UserError("Busy", "Wait for the current job to finish.", 409)
        body = _body()
        finals = sorted(DIR_FINAL.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True) if DIR_FINAL.exists() else []
        if not finals:
            raise UserError("No video", "No converted video found in output/final: generate one first.")
        language = _language(body["language"]).profile.tag if body.get("language") else None
        try:
            meta = videos.import_file(finals[0], language=language)
        except videos.VideoError as exc:
            raise UserError("Player", str(exc))
        return jsonify(id=meta["id"])

    # ---------- output folder ----------

    @app.post("/api/clear-output")
    def api_clear_output():
        if state.running:
            raise UserError("Busy", "Wait for the current job to finish before clearing the output folder.", 409)
        files.clear_output()
        state.last_video_srt = None
        state.info("Output folder cleared.\n")
        return jsonify(cleared=True)

    @app.post("/api/open-folder")
    def api_open_folder():
        from gui_components.utils import open_folder

        folder = {"final": "final", "frequency": "frequency"}.get(_body().get("which"), "final")
        path = ROOT / "output" / folder
        try:
            open_folder(path)
        except Exception as exc:
            raise UserError("Could not open the folder", f"{exc}\n\nThe files are in: {path}", 500)
        return jsonify(path=str(path))

    return app


def main(port: int = 5050, open_browser: bool = True, page: str = "") -> None:
    files.clear_staging()
    app = create_app()
    url = f"http://127.0.0.1:{port}/{page}"
    print(f"MiningCat is running at {url}  (press Ctrl+C to stop)")
    if open_browser:
        import webbrowser
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        app.run(host="127.0.0.1", port=port, threaded=True, debug=False, use_reloader=False)
    finally:
        # Stops the video game capture with the server, so it doesn't keep its port and the window capture busy.
        proc = app.extensions["miningcat"].game_proc
        if proc is not None:
            from gui_components import pipeline
            pipeline.stop_game_server(proc)
