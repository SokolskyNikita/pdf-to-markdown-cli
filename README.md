# PDF -> Markdown CLI utility

Convenience CLI wrapper around the [Marker API](https://datalab.to/marker) which is currently the best-in-class for PDF->Markdown conversion. See the **/examples** folder for conversion examples.

### Features 
  - Supported **inputs**: PDF, Word (.doc, .docx), PowerPoint (.ppt, .pptx), Images (.png, .jpg, .jpeg, .webp, .gif, .tiff)
  - Supported **outputs**: Markdown and JSON
  - Automatically splits large PDFs into smaller files for processing, speeds up processing up to 10x
  - Can OCR in ~any language that's supported by modern LLMs
  - Automatic file name cleaning and organization
  - Optional LLM enhancement for improved accuracy, including table structure recognition
  - Excellent support for inline math equations
  - Stores the requests status in a local cache file, lets you resume interrupted conversions

### Installation & Usage

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

```bash
python marker_cli.py input.pdf # single file
python marker_cli.py input_dir/ # directory of files
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

  - `--llm`
  - Enable LLM enhancement for better accuracy
  - Improves forms, tables, inline math, and layout recognition
  - Note: Doubles the per-request cost

- `--noimg`
  - Disable image extraction
  - When used with `--llm`, converts images to text descriptions

- `--json`
  - Output in JSON format instead of Markdown

- `--pages`
  - Add page delimiters to output
  - Helps maintain document structure

- `--no-chunk`
  - Disable PDF chunking (processes entire PDF as one file)
  - Useful for small PDFs or when you want to ensure document coherence
  - Note: May be slower for large files

- `-cs`, `--chunk-size PAGES`
  - Set custom chunk size in pages (default: 25)
  - Larger chunks mean fewer API requests but slower individual processing
  - Example: `-cs 50` processes 50 pages per chunk

- `--outdir PATH`
  - Default: `converted/<filename>/<timestamp>/`

- `--langs LANGUAGES`
  - Comma-separated list of languages to use for OCR, useful for mixed language documents
  - Example: "English,French"

#### More Usage Examples

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

Process large PDF without chunking:
```bash
python marker_cli.py document.pdf --no-chunk
```

Process with custom chunk size of 50 pages:
```bash
python marker_cli.py document.pdf --chunk-size 50
# or
python marker_cli.py document.pdf -cs 50
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

- If output quality is poor, try enabling `--force` to ignore existing OCR inside the PDF
- Ensure correct language settings with `--langs`
- Failed conversions should show detailed error messages, open an issue on the repo if you think it's an error with the tool

### License

MIT License