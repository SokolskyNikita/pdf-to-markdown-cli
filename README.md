# Marker PDF to Markdown Converter

A command-line tool that converts PDF documents to Markdown or JSON format using the Marker API. This tool provides comprehensive document conversion capabilities including OCR, image extraction, and layout analysis.

### Features & Capabilities of Marker's API

- **Document Conversion**
  - Convert PDFs, Word documents, and PowerPoints to Markdown/JSON/HTML
  - Support for multiple OCR languages
  - Intelligent image extraction and handling
  - Automatic file name cleaning and organization
  - Optional LLM enhancement for improved accuracy, including table structure recognition
  - Great support for inline math equations
  - Stores a cache of requests, lets you retrieve a requested file later if you accidentally close the terminal

### Supported File Types

- PDF (`.pdf`)
- Word Documents (`.doc`, `.docx`)
- PowerPoint (`.ppt`, `.pptx`)
- Images (`.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.tiff`)

### Installation & Setup

1. Clone and navigate to the repository:
```bash
git clone <repository-url>
cd marker_pdf_to_md
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your API key:
   - Get your API key from [datalab.to](https://www.datalab.to/app/keys)
   - Set the environment variable `MARKER_PDF_KEY`:
     ```bash
     export MARKER_PDF_KEY=your_api_key_here
     ```
   - For permanent setup, add to your shell configuration file (e.g., `.bashrc` or `.zshrc`):
     ```bash
     echo 'export MARKER_PDF_KEY=your_api_key_here' >> ~/.zshrc
     source ~/.zshrc
     ```

### Usage

Basic conversion:
```bash
python marker_cli.py input.pdf
```

#### Available Options

- `--max`
  - Enable all OCR enhancements: ignores existing OCR and uses LLM for all text, equations, and tables
  - Maximum accuracy at double the cost
  - **Strongly recommended for best results**

- `--strip`
  - Remove and redo OCR on the document
  - Useful for files with poor quality existing OCR

- `--force`
  - Force OCR on every page
  - Ignores existing PDF text
  - Slower but more accurate for problematic PDFs

- `--noimg`
  - Disable image extraction
  - When used with `--llm`, converts images to text descriptions

- `--llm`
  - Enable LLM enhancement for better accuracy
  - Improves forms, tables, inline math, and layout recognition
  - Note: Doubles the per-request cost

- `--json`
  - Output in JSON format instead of Markdown

- `--pages`
  - Add page delimiters to output
  - Helps maintain document structure

- `--outdir PATH`
  - Default: `converted/<filename>/<timestamp>/`

- `--langs LANGUAGES`
  - Comma-separated list of languages to use for OCR, useful for mixed language documents
  - Example: "English,French"

#### Usage Examples

Process with specific languages:
```bash
python marker_cli.py document.pdf --langs "English,French"
```

Maximum quality conversion:
```bash
python marker_cli.py document.pdf --max
```

JSON output with image extraction disabled:
```bash
python marker_cli.py document.pdf --json --noimg
```

### Output Structure

Converted files are organized as follows, the subfolders are created to avoid overwriting previous conversions:
```
converted/
└── document_name/
    └── YY-MM-DD_HH-MM/
        ├── document.md
        └── images/
            └── extracted_images...
```

### Troubleshooting

- If output quality is poor, try enabling `--force` OCR
- Ensure correct language settings with `--langs`
- When using `--llm` and/or `--max`, expect 100 pages to takes 7-10 minutes to process
- Files over 200MB are not supported (TODO: implement this)
- Failed conversions should show detailed error messages

### License

MIT License