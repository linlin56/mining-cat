.PHONY: help gui install test test-gui coverage audio epub align export chapter1 chapter run clean video game-setup game

# Defaults
CHAPTER  ?= 1
N        ?= 1
MODEL    ?= tiny
LANGUAGE ?= mandarin_tw
PRESET   ?= ultrafast
RANGE    ?=
URL      ?=
FILE     ?=
APP_ID   ?= web
HOTKEY   ?= F9
ifeq ($(OS),Windows_NT)
  _VENV_PYTHON := .venv/Scripts/python.exe
else
  _VENV_PYTHON := .venv/bin/python3
endif
ifeq ($(wildcard $(_VENV_PYTHON)),)
  PYTHON ?= python
else
  PYTHON ?= $(_VENV_PYTHON)
endif
MAIN     := $(PYTHON) src/main.py

gui:
	$(PYTHON) src/gui.py

help:
	@echo "MiningCat"
	@echo ""
	@echo "Usage:"
	@echo "  make install                    Install dependencies"
	@echo "  make test                       Run tests (without the GUI tests, which open windows)"
	@echo "  make test-gui                   Run the GUI tests"
	@echo "  make audio                      Step 1: prepare audio chapters"
	@echo "  make epub [RANGE=4-9]           Step 2: extract epub text"
	@echo "  make align [CHAPTER=1|all]      Step 3: align chapter(s)"
	@echo "  make export [CHAPTER=1|all]     Step 4: export chapter(s) to MP4"
	@echo "  make chapter1                   Align + export chapter 1"
	@echo "  make chapter N=5                Align + export chapter N"
	@echo "  make run [RANGE=4-9]            Run all steps in sequence"
	@echo "  make video URL=...              Download an online video and generate subtitles"
	@echo "  make video FILE=...             Use a local video file and generate subtitles"
	@echo "  make game-setup                 Select the game window, screenshot area and text area"
	@echo "  make game [HOTKEY=F9]           Start the video game / screen share OCR page (capture with the key)"
	@echo "  make clean                      Clean temp and output files"
	@echo ""
	@echo "Examples:"
	@echo "  make epub RANGE=4-9"
	@echo "  make align CHAPTER=all MODEL=large"
	@echo "  make export CHAPTER=all PRESET=superfast"
	@echo "  make run RANGE=4-9"
	@echo "  make video URL=https://www.instagram.com/reel/xxxxx/"

install:
	$(PYTHON) -m pip install -r requirements.txt
	# Install separately with --no-deps to avoid the PyGObject build error on Linux.
	$(PYTHON) -m pip install --no-deps "owocr>=1.26.8"

test:
	$(PYTHON) -m pytest

test-gui:
	$(PYTHON) -m pytest -m gui

coverage:
	$(PYTHON) -m pytest --cov=src --cov-report=xml --cov-report=term-missing

audio:
	$(MAIN) audio

epub:
	@if [ -n "$(RANGE)" ]; then \
		$(MAIN) epub --range $(RANGE); \
	else \
		$(MAIN) epub; \
	fi

align:
	@if [ "$(CHAPTER)" = "all" ]; then \
		$(MAIN) align --model $(MODEL) --language $(LANGUAGE); \
	else \
		$(MAIN) align --model $(MODEL) --language $(LANGUAGE) --only $(CHAPTER); \
	fi

export:
	@if [ "$(CHAPTER)" = "all" ]; then \
		$(MAIN) export --all --preset $(PRESET); \
	else \
		$(MAIN) export --chapter $(CHAPTER) --preset $(PRESET); \
	fi

chapter1:
	$(MAIN) align --only 1 --model $(MODEL) --language $(LANGUAGE)
	$(MAIN) export --chapter 1 --preset $(PRESET)

# make chapter N=5
chapter:
	$(MAIN) align --only $(N) --model $(MODEL) --language $(LANGUAGE)
	$(MAIN) export --chapter $(N) --preset $(PRESET)

run:
	@if [ -n "$(RANGE)" ]; then \
		$(MAIN) run --range $(RANGE); \
	else \
		$(MAIN) run; \
	fi

# make video URL=https://www.instagram.com/reel/xxxxx/
# make video FILE=path/to/movie.mp4
video:
	@if [ -n "$(FILE)" ]; then \
		$(MAIN) video --file "$(FILE)" --model $(MODEL) --language $(LANGUAGE); \
	elif [ -n "$(URL)" ]; then \
		$(MAIN) video --url "$(URL)" --model $(MODEL) --language $(LANGUAGE) --app-id $(APP_ID); \
	else \
		echo "Error: URL or FILE is required, e.g. make video URL=https://www.instagram.com/reel/xxxxx/"; \
		exit 1; \
	fi

game-setup:
	$(MAIN) game setup

game:
	$(MAIN) game serve --language $(LANGUAGE) --hotkey $(HOTKEY)

clean:
	rm -rf temp/*.mp3 temp/*.txt temp/*.srt output/*
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
