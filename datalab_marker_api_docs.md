# Documentation

# General Info

These hosted APIs leverage the [surya](https://github.com/VikParuchuri/surya) and [marker](https://github.com/VikParuchuri/marker) projects to do OCR, convert PDFs to markdown, and recognize tables.

## Billing

Your initial plan gives you a certain number of credits. Each request will cost a certain amount, rounded up to the nearest cent. You can see the per-page prices on the [plans page](https://www.datalab.to/app/plans). If you go above the initial credit, you will be billed for the overage.

## Authentication

You authenticate by setting the `X-Api-Key` header. You can find your API keys [here](https://www.datalab.to/app/keys). Billing limits can be set per-key to avoid high bills.

## Limits

### Rate Limits

The request limit for all endpoints is `200` per `60` seconds. You also cannot have more than `200` concurrent requests. You'll get a `429` error if you exceed the rate limit.

Reach out to `support@datalab.to` if you need higher limits.

### File Size Limits

The file size limit for all endpoints is currently `200MB`. If you need to submit larger files, please reach out to `support@datalab.to`. One solution is to slice the file into chunks that are under `200MB`.

## Callbacks

You will normally need to poll to get API results. If you don't want to poll, you can specify a URL that will be hit when inference is complete. Specify the webhook URL in the settings panel on the dashboard.

The callback will pass this data to your webhook URL:

- `request_id` lookup key of the original request
- `webhook_secret` a webhook secret you can define to reject other messages
- `request_check_url` the URL you will need to hit to get the full results

# Marker API Endpoint

The endpoint will return immediately, and continue processing in the background, aka its asynchronous.

The marker endpoint converts PDFs, spreadsheets, Word documents, EPUB, HTML, and PowerPoint files to Markdown. It is available at `/api/v1/marker`.

Here is an example request in Python:

```python
import requests

url = "https://www.datalab.to/api/v1/marker"

form_data = {
    "file": ("test.pdf", open("~/pdfs/test.pdf", "rb"), "application/pdf"),
    "langs": (None, "English"),
    "force_ocr": (None, False),
    "paginate": (None, False),
    "output_format": (None, "markdown"),
    "use_llm": (None, False),
    "strip_existing_ocr": (None, False),
    "disable_image_extraction": (None, False),
}

headers = {"X-Api-Key": "YOUR_API_KEY"}

response = requests.post(url, files=form_data, headers=headers)
data = response.json()
```

As you can see, everything is a form parameter. This is because we're uploading a file, so the request body has to be `multipart/form-data`.

Parameters:

- `file`: The input file.
- `langs`: An optional, comma-separated list of languages in the file (this is used if OCR is needed). The language names and codes are from [here](https://github.com/VikParuchuri/surya/blob/master/surya/languages.py).
- `output_format`: One of `json`, `html`, or `markdown`.
- `force_ocr`: Will force OCR on every page (ignore the text in the PDF). This is slower, but can be useful for PDFs with known bad text.
- `paginate`: Adds delimiters to the output pages. See the API reference for details.
- `use_llm`: Setting this to `True` will use an LLM to enhance accuracy of forms, tables, inline math, and layout. It can be much more accurate, but carries a small hallucination risk. Setting `use_llm` to `True` will make responses slower.
- `strip_existing_ocr`: Setting to `True` will remove all existing OCR text from the file and redo OCR. This is useful if you know OCR text was added to the PDF by a low-quality OCR tool.
- `disable_image_extraction`: Setting to `True` will disable extraction of images. If `use_llm` is set to `True`, this will also turn images into text descriptions.
- `max_pages`: From the start of the file, specifies the maximum number of pages to inference.
- `page_range`: The page range to parse, comma separated like `0,5-10,20`. This will override `max_pages` if provided. Example: `'0,2-4'` will process pages 0, 2, 3, and 4.
- `skip_cache`: Skip the cache and re-run the inference. Defaults to `False`. If set to `True`, the cache will be skipped and the inference will be re-run.

You can see a full list of parameters and descriptions in the [API reference](https://www.datalab.to/app/reference).

The request will return the following:

```json
{
  "success": true,
  "error": null,
  "request_id": "PpK1oM-HB4RgrhsQhVb2uQ",
  "request_check_url": "https://www.datalab.to/api/v1/marker/PpK1oM-HB4RgrhsQhVb2uQ"
}
```

You will then need to poll `request_check_url` (don't forget to include your authentication headers), like this:

```python
import time

max_polls = 300
check_url = data["request_check_url"]

for i in range(max_polls):
    time.sleep(2)
    response = requests.get(check_url, headers=headers)  # Don't forget to send the auth headers
    data = response.json()

    if data["status"] == "complete":
        break
```

You can customize the max number of polls and the check interval to your liking. Eventually, the `status` field will be set to `complete`, and you will get an object that looks like this:

```json
{
  "output_format": "markdown",
  "markdown": "...",
  "status": "complete",
  "success": true,
  "images": {...},
  "metadata": {...},
  "error": "",
  "page_count": 5
}
```

If `success` is `False`, you will get an error code along with the response.

All response data will be deleted from Datalab servers an hour after processing is complete, so make sure to get your results by then.

### Response fields

- `output_format` is the requested output format, `json`, `html`, or `markdown`.
- `markdown` | `json` | `html` is the output from the file. It will be named according to the `output_format`. You can find more details on the json format [here](https://github.com/VikParuchuri/marker?tab=readme-ov-file#json).
- `status` - indicates the status of the request (`complete`, or `processing`).
- `success` - indicates if the request completed successfully. `True` or `False`.
- `images` - dictionary of image filenames (keys) and base64 encoded images (values). Each value can be decoded with `base64.b64decode(value)`. Then it can be saved to the filename (key).
- `meta` - metadata about the markdown conversion.
- `error` - if there was an error, this contains the error message.
- `page_count` - number of pages that were converted.

### Supported file types

Marker supports the following extensions and mime types:

- PDF - `pdf`/`application/pdf`
- Spreadsheet - `xls`/`application/vnd.ms-excel`, `xlsx`/`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `ods`/`application/vnd.oasis.opendocument.spreadsheet`
- Word document - `doc`/`application/msword`, `docx`/`application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `odt`/`application/vnd.oasis.opendocument.text`
- PowerPoint - `ppt`/`application/vnd.ms-powerpoint`, `pptx`/`application/vnd.openxmlformats-officedocument.presentationml.presentation`, `odp`/`application/vnd.oasis.opendocument.presentation`
- HTML - `html`/`text/html`
- Epub - `epub`/`application/epub+zip`
- Images - `png`/`image/png`, `jpeg`/`image/jpeg`, `wepb`/`image/webp`, `gif`/`image/gif`, `tiff`/`image/tiff`, `jpg`/`image/jpg`

You can automatically find the mimetype in python by installing `filetype`, then using `filetype.guess(FILEPATH).mime`.

### Troubleshooting

If you get bad output, setting `force_ocr` to `True` is a good first step. A lot of PDFs have bad text inside. Marker attempts to auto-detect this and run OCR, but the auto-detection is not 100% accurate. Making sure `langs` is set properly is a good second step.
