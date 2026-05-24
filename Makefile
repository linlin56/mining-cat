.PHONY: help gui install test audio epub align export chapter1 chapter run clean

# Defaults
CHAPTER  ?= 1
N        ?= 1
MODEL    ?= tiny
LANGUAGE ?= zh
PRESET   ?= ultrafast
RANGE    ?=
PYTHON   ?= .venv/bin/python3
MAIN     := $(PYTHON) main.py

GUI_PYTHON ?= python3.12

gui:
	$(GUI_PYTHON) gui.py

help:
	@echo "AudiobookMiner"
	@echo ""
	@echo "Usage:"
	@echo "  make install                    Install dependencies"
	@echo "  make test                       Run tests"
	@echo "  make audio                      Step 1: prepare audio chapters"
	@echo "  make epub [RANGE=4-9]           Step 2: extract epub text"
	@echo "  make align [CHAPTER=1|all]      Step 3: align chapter(s)"
	@echo "  make export [CHAPTER=1|all]     Step 4: export chapter(s) to MP4"
	@echo "  make chapter1                   Align + export chapter 1"
	@echo "  make chapter N=5                Align + export chapter N"
	@echo "  make run [RANGE=4-9]            Run all steps in sequence"
	@echo "  make clean                      Clean temp and output files"
	@echo ""
	@echo "Examples:"
	@echo "  make epub RANGE=4-9"
	@echo "  make align CHAPTER=all MODEL=large"
	@echo "  make export CHAPTER=all PRESET=superfast"
	@echo "  make run RANGE=4-9"

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest

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

clean:
	rm -rf temp/*.mp3 temp/*.txt temp/*.srt output/*
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
