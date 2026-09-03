# Catholic Text JSON

A small, GitHub-friendly collection of major Catholic texts in JSON.

This repo **scrapes papal encyclicals** from [Vatican.va](https://www.vatican.va/offices/papal_docs_list.html) and **points at existing datasets** via git submodules instead of copying them.

| Corpus | What you get | Source |
| --- | --- | --- |
| NABRE Bible | 73 books | [nirmalben/bible-nabre-json-dataset](https://github.com/nirmalben/bible-nabre-json-dataset) (submodule) |
| Catechism | 2,865 paragraphs | [aseemsavio/catholicism-in-json](https://github.com/aseemsavio/catholicism-in-json) (submodule + GitHub release) |
| Canon Law | 1,751 canons | same |
| GIRM | 399 paragraphs | same |
| Papal encyclicals | one JSON file per encyclical | scraped here from Vatican.va |

## Layout

```
data/
├── bible-nabre-json-dataset/          git submodule
├── catholicism-in-json/               git submodule
└── encyclicals/
    ├── index.json                     small catalog (title, pope, date, file)
    └── en/
        ├── fratelli-tutti.json
        └── ...
```

Generated locally (not committed, because they are large duplicates):

- `data/papal_encyclicals.json` — all encyclical bodies in one file (`make postprocess`)
- `data/catholic_all.json` — Bible + CCC + Canon + GIRM + encyclicals (`make build`)

## Clone

```bash
git clone --recurse-submodules <this-repo-url>
cd catholic_text_json
pip3 install -r requirements.txt
```

If you already cloned without submodules:

```bash
git submodule update --init --recursive
```

## One-command rebuild

```bash
make all
```

Or step by step:

```bash
python3 scripts/download_datasets.py
python3 scripts/scrape_papal_encyclicals_vatican.py \
  --out data/papal_encyclicals.json \
  --out-dir data/encyclicals
python3 scripts/postprocess_encyclicals.py
python3 scripts/build_catholic_json.py
```

Default language is English (`--lang en`). Files go in `data/encyclicals/en/`.

### Other encyclical languages

Vatican pages exist in other languages. This is **opt-in** — English is still the default.

```bash
# Italian
python3 scripts/scrape_papal_encyclicals_vatican.py \
  --lang it \
  --out data/papal_encyclicals-it.json \
  --out-dir data/encyclicals
python3 scripts/postprocess_encyclicals.py --lang it

# Spanish, French, German, Portuguese, Latin, Polish, ...
make scrape LANG=es
make postprocess LANG=es
```

That writes `data/encyclicals/it/` (or `es/`, `fr/`, …) plus `data/encyclicals/index-it.json`.

`--lang` accepts Vatican codes such as `en`, `it`, `es`, `fr`, `de`, `pt`, `la`, `pl`, `ar`, `zh_cn`. Use `--lang none` to keep whatever language the index pages list.

## Encyclical JSON

Each file in `data/encyclicals/en/` looks like:

```json
{
  "id": "francesco-2020-10-03-fratelli-tutti",
  "slug": "fratelli-tutti",
  "pope": "Francis",
  "title": "Fratelli tutti",
  "publicationDate": "2020-10-03",
  "vaticanUrl": "https://www.vatican.va/...",
  "language": "en",
  "paragraphCount": 287,
  "paragraphs": [
    { "paragraph": 1, "text": "With these words, Saint Francis..." }
  ]
}
```

Browse everything from `data/encyclicals/index.json` without loading the full texts.

## Combined dump (`make build`)

```json
{
  "generatedAt": "...",
  "counts": {
    "bible": 73,
    "catechism": 2865,
    "canonLaw": 1751,
    "romanMissal": 399,
    "encyclicals": 211
  },
  "bible": [],
  "catechism": [],
  "canonLaw": [],
  "romanMissal": [],
  "encyclicals": []
}
```

## Credits

- Bible: [nirmalben/bible-nabre-json-dataset](https://github.com/nirmalben/bible-nabre-json-dataset)
- Catechism, Canon Law, GIRM: [aseemsavio/catholicism-in-json](https://github.com/aseemsavio/catholicism-in-json)
- Encyclicals: [Vatican.va papal documents](https://www.vatican.va/offices/papal_docs_list.html)

Scripts are MIT-licensed. The texts themselves remain under their original copyrights (USCCB, Libreria Editrice Vaticana, and others).
