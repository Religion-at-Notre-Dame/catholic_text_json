.PHONY: install download scrape postprocess build all

LANG ?= en

install:
	pip3 install -r requirements.txt

download:
	python3 scripts/download_datasets.py

scrape:
	python3 scripts/scrape_papal_encyclicals_vatican.py \
		--lang $(LANG) \
		--out data/papal_encyclicals-$(LANG).json \
		--out-dir data/encyclicals

postprocess:
	python3 scripts/postprocess_encyclicals.py --lang $(LANG)

build:
	python3 scripts/build_catholic_json.py

all: install download scrape postprocess build
