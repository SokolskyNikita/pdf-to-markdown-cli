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

### File size limits

The file size limit for all endpoints is `200MB` currently. If you need to submit larger files, please reach out to `support@datalab.to`. One solution is also to slice the file into chunks that are under `200MB` in size.

## Callbacks

You will normally need to poll to get API results. If you don't want to poll, you can specify a URL that will be hit when inference is complete. Specify the webhook URL in the settings panel on the dashboard.

The callback will pass this data to your webhook URL:

-   `request_id`- lookup key of the original request
-   `webhook_secret` - a webhook secret you can define to reject other messages
-   `request_check_url` - the url you will need to hit to get the full results

# API Endpoints

All endpoints will return immediately, and continue processing in the background.

## Marker

The marker endpoint converts PDF, word documents, and powerpoints to markdown. It is available at `/api/v1/marker`.

Here is an example request in Python:

`import requests

url = "https://www.datalab.to/api/v1/marker"

form_data = {
    'file': ('test.pdf', open('~/pdfs/test.pdf', 'rb'), 'application/pdf'),
    'langs': (None, "English"),
    "force_ocr": (None, False),
    "paginate": (None, False),
    'output_format': (None, 'markdown'),
    "use_llm": (None, False),
    "strip_existing_ocr": (None, False),
    "disable_image_extraction": (None, False)
}

headers = {"X-Api-Key": "YOUR_API_KEY"}

response = requests.post(url, files=form_data, headers=headers)
data = response.json()` 

As you can see, everything is a form parameter. This is because we're uploading a file, so the request body has to be `multipart/form-data`.

Parameters: - `file`, the input file. - `langs` is an optional, comma-separated list of languages in the file (this is used if OCR is needed). The language names and codes are from [here](https://github.com/VikParuchuri/surya/blob/master/surya/languages.py). - `output_format` - one of `json`, `html`, or `markdown`. - `force_ocr` will force OCR on every page (ignore the text in the PDF). This is slower, but can be useful for PDFs with known bad text. - `paginate` - adds delimiters to the output pages. See the API reference for details. - `use_llm` - Beta: setting this to `True` will use an LLM to enhance accuracy of forms, tables, inline math, and layout. It's much more accurate, but will double the per-request cost. - `strip_existing_ocr` - setting to `True` will remove all existing OCR text from the file and redo OCR. This is useful if you know OCR text was added to the PDF by a low-quality OCR tool. - `disable_image_extraction` - setting to `True` will disable extraction of images. If `use_llm` is set to `True`, this will also turn images into text descriptions.

You can see a full list of parameters and descriptions in the [API reference](https://www.datalab.to/app/reference).

The request will return the following:

`{'success': True, 'error': None, 'request_id': "PpK1oM-HB4RgrhsQhVb2uQ", 'request_check_url': 'https://www.datalab.to/api/v1/marker/PpK1oM-HB4RgrhsQhVb2uQ'}` 

You will then need to poll `request_check_url`, like this:

`import time

max_polls = 300
check_url = data["request_check_url"]

for i in range(max_polls):
    time.sleep(2)
    response = requests.get(check_url, headers=headers) # Don't forget to send the auth headers
    data = response.json()

    if data["status"] == "complete":
        break` 

You can customize the max number of polls and the check interval to your liking. Eventually, the `status` field will be set to `complete`, and you will get an object that looks like this:

`{
    "output_format": "markdown",
    "markdown": "...",
    "status": "complete",
    "success": True,
    "images": {...},
    "metadata": {...},
    "error": "",
    "page_count": 5
}` 

If success is `False`, you will get an error code along with the response.

All response data will be deleted from datalab servers an hour after the processing is complete, so make sure to get your results by then.

### Response fields

-   `output_format` is the requested output format, `json`, `html`, or `markdown`.
-   `markdown` | `json` | `html` is the output from the file. It will be named according to the `output_format`. You can find more details on the json format [here](https://github.com/VikParuchuri/marker?tab=readme-ov-file#json).
-   `status` - indicates the status of the request (`complete`, or `processing`).
-   `success` - indicates if the request completed successfully. `True` or `False`.
-   `images` - dictionary of image filenames (keys) and base64 encoded images (values). Each value can be decoded with `base64.b64decode(value)`. Then it can be saved to the filename (key).
-   `meta` - metadata about the markdown conversion.
-   `error` - if there was an error, this contains the error message.
-   `page_count` - number of pages that were converted.

### Supported file types

Marker supports the following extensions and mime types:

-   PDF - `pdf`/`application/pdf`
-   Word document - `doc`/`application/msword`, `docx`/`application/vnd.openxmlformats-officedocument.wordprocessingml.document`
-   Powerpoint - `ppt`/`application/vnd.ms-powerpoint`, `pptx`/`application/vnd.openxmlformats-officedocument.presentationml.presentation`
-   Images - `png`/`image/png`, `jpeg`/`image/jpeg`, `wepb`/`image/webp`, `gif`/`image/gif`, `tiff`/`image/tiff`, `jpg`/`image/jpg`

You can automatically find the mimetype in python by installing `filetype`, then using `filetype.guess(FILEPATH).mime`.

### Troubleshooting

If you get bad output, setting `force_ocr` to `True` is a good first step. A lot of PDFs have bad text inside. Marker attempts to auto-detect this and run OCR, but the auto-detection is not 100% accurate. Making sure `langs` is set properly is a good second step.

## Table Recognition

The table recognition endpoint at `/api/v1/table_rec` will detect tables, then identify the structure and format the tables properly.

Here is an example request in python:

`import requests

url = "https://www.datalab.to/api/v1/table_rec"

form_data = {
    'file': ('test.png', open('~/images/test.png', 'rb'), 'image/png'),
}

headers = {"X-Api-Key": "YOUR_API_KEY"}

response = requests.post(url, files=form_data, headers=headers)
data = response.json()` 

The api accepts files of type `application/pdf`, `image/png`, `image/jpeg`, `image/webp`, `image/gif`, `image/tiff`, and `image/jpg`.

Optional parameters are:

-   `max_pages` lets you specify the maximum number of pages of a pdf to make predictions for.
-   `skip_table_detection` doesn't re-detect tables if your pages are already cropped.
-   `detect_cell_boxes` will re-detect all cell bounding boxes vs using the text in the PDF.
-   `output_format` is the format of the output, one of `markdown`, `html`, `json`. Default is `markdown`.
-   `paginate` determines whether to paginate markdown output. Default is `False`.
-   `use_llm` beta: optionally uses an LLM to merge tables and improve accuracy. This will double the cost of requests.

The request will return the following:

`{'success': True, 'error': None, 'request_id': "PpK1oM-HB4RgrhsQhVb2uQ", 'request_check_url': 'https://www.datalab.to/api/v1/table_rec/PpK1oM-HB4RgrhsQhVb2uQ'}` 

You will then need to poll `request_check_url`, like this:

`import time

max_polls = 300
check_url = data["request_check_url"]

for i in range(max_polls):
    time.sleep(2)
    response = requests.get(check_url, headers=headers) # Don't forget to send the auth headers
    data = response.json()

    if data["status"] == "complete":
        break` 

The final response will look like this:

`{
    "output_format": "markdown",
    "markdown": "...",
    "status": "complete",
    "success": True,
    "metadata": {...},
    "error": "",
    "page_count": 5
}` 

If success is `False`, you will get an error code along with the response.

All response data will be deleted from datalab servers an hour after the processing is complete, so make sure to get your results by then.

### Response fields

-   `output_format` is the requested output format, `json`, `html`, or `markdown`.
-   `markdown` | `json` | `html` is the output from the file. It will be named according to the `output_format`. You can find more details on the json format [here](https://github.com/VikParuchuri/marker?tab=readme-ov-file#json).
-   `status` - indicates the status of the request (`complete`, or `processing`).
-   `success` - indicates if the request completed successfully. `True` or `False`.
-   `meta` - metadata about the markdown conversion.
-   `error` - if there was an error, this contains the error message.
-   `page_count` - number of pages that were converted.

### Supported file types

Table recognition supports the following extensions and mime types:

-   PDF - `pdf`/`application/pdf`
-   Word document - `doc`/`application/msword`, `docx`/`application/vnd.openxmlformats-officedocument.wordprocessingml.document`
-   Powerpoint - `ppt`/`application/vnd.ms-powerpoint`, `pptx`/`application/vnd.openxmlformats-officedocument.presentationml.presentation`
-   Images - `png`/`image/png`, `jpeg`/`image/jpeg`, `wepb`/`image/webp`, `gif`/`image/gif`, `tiff`/`image/tiff`, `jpg`/`image/jpg`

You can automatically find the mimetype in python by installing `filetype`, then using `filetype.guess(FILEPATH).mime`.

## OCR

The OCR endpoint at `/api/v1/ocr` will OCR a given pdf, word document, powerpoint, or image.

Here is an example request in python:

`import requests

url = "https://www.datalab.to/api/v1/ocr"

form_data = {
    'file': ('test.png', open('~/images/test.png', 'rb'), 'image/png'),
    'langs': (None, "English")
}

headers = {"X-Api-Key": "YOUR_API_KEY"}

response = requests.post(url, files=form_data, headers=headers)
data = response.json()` 

The `langs` field is optional, to give language hints to the OCR model. The language names and codes are from [here](https://github.com/VikParuchuri/surya/blob/master/surya/languages.py). You can specify up to 4 languages.

The api accepts files of type `application/pdf`, `image/png`, `image/jpeg`, `image/webp`, `image/gif`, `image/tiff`, and `image/jpg`. The optional parameter `max_pages` lets you specify the maximum number of pages of a pdf to make predictions for.

The request will return the following:

`{'success': True, 'error': None, 'request_id': "PpK1oM-HB4RgrhsQhVb2uQ", 'request_check_url': 'https://www.datalab.to/api/v1/ocr/PpK1oM-HB4RgrhsQhVb2uQ'}` 

You will then need to poll `request_check_url`, like this:

`import time

max_polls = 300
check_url = data["request_check_url"]

for i in range(max_polls):
    time.sleep(2)
    response = requests.get(check_url, headers=headers) # Don't forget to send the auth headers
    data = response.json()

    if data["status"] == "complete":
        break` 

The final response will look like this:

`{
    'status': 'complete', 
    'pages': [
        {
            'text_lines': [{
                'polygon': [[267.0, 139.0], [525.0, 139.0], [525.0, 159.0], [267.0, 159.0]], 
                'confidence': 0.99951171875, 
                'text': 'Subspace Adversarial Training', 
                'bbox': [267.0, 139.0, 525.0, 159.0]
            }, ...],
            'languages': ['en'], 
            'image_bbox': [0.0, 0.0, 816.0, 1056.0], 
            'page': 12
        }
    ], 
    'success': True, 
    'error': '',
    'page_count': 5
}` 

If success is `False`, you will get an error code along with the response.

All response data will be deleted from datalab servers an hour after the processing is complete, so make sure to get your results by then.

### Response fields

-   `status` - indicates the status of the request (`complete`, or `processing`).
-   `success` - indicates if the request completed successfully. `True` or `False`.
-   `error` - If there was an error, this is the error message.
-   `page_count` - number of pages we ran ocr on.
-   `pages` - a list containing one dictionary per input page. The fields are:
    -   `text_lines` - the detected text and bounding boxes for each line
        -   `text` - the text in the line
        -   `confidence` - the confidence of the model in the detected text (0-1)
        -   `polygon` - the polygon for the text line in (x1, y1), (x2, y2), (x3, y3), (x4, y4) format. The points are in clockwise order from the top left.
        -   `bbox` - the axis-aligned rectangle for the text line in (x1, y1, x2, y2) format. (x1, y1) is the top left corner, and (x2, y2) is the bottom right corner.
    -   `languages` - the languages specified for the page
    -   `page` - the page number in the file
    -   `image_bbox` - the bbox for the image in (x1, y1, x2, y2) format. (x1, y1) is the top left corner, and (x2, y2) is the bottom right corner. All line bboxes will be contained within this bbox.

### Supported file types

OCR supports the following extensions and mime types:

-   PDF - `pdf`/`application/pdf`
-   Word document - `doc`/`application/msword`, `docx`/`application/vnd.openxmlformats-officedocument.wordprocessingml.document`
-   Powerpoint - `ppt`/`application/vnd.ms-powerpoint`, `pptx`/`application/vnd.openxmlformats-officedocument.presentationml.presentation`
-   Images - `png`/`image/png`, `jpeg`/`image/jpeg`, `wepb`/`image/webp`, `gif`/`image/gif`, `tiff`/`image/tiff`, `jpg`/`image/jpg`

You can automatically find the mimetype in python by installing `filetype`, then using `filetype.guess(FILEPATH).mime`.

## Layout

The layout endpoint at `/api/v1/layout` will detect layout bboxes in a given pdf, word document, powerpoint, or image. The possible labels for the layout bboxes are: `Caption`, `Footnote`, `Formula`, `List-item`, `Page-footer`, `Page-header`, `Picture`, `Figure`, `Section-header`, `Table`, `Text`, `Title`. The layout boxes are then labeled with a `position` field indicating their reading order, and sorted.

Here is an example request in python:

`import requests

url = "https://www.datalab.to/api/v1/layout"

form_data = {
    'file': ('test.png', open('~/images/test.png', 'rb'), 'image/png'),
}

headers = {"X-Api-Key": "YOUR_API_KEY"}

response = requests.post(url, files=form_data, headers=headers)
data = response.json()` 

The api accepts files of type `application/pdf`, `image/png`, `image/jpeg`, `image/webp`, `image/gif`, `image/tiff`, and `image/jpg`. The optional parameter `max_pages` lets you specify the maximum number of pages of a pdf to make predictions for.

The request will return the following:

`{'success': True, 'error': None, 'request_id': "PpK1oM-HB4RgrhsQhVb2uQ", 'request_check_url': 'https://www.datalab.to/api/v1/layout/PpK1oM-HB4RgrhsQhVb2uQ'}` 

You will then need to poll `request_check_url`, like this:

`import time

max_polls = 300
check_url = data["request_check_url"]

for i in range(max_polls):
    time.sleep(2)
    response = requests.get(check_url, headers=headers) # Don't forget to send the auth headers
    data = response.json()

    if data["status"] == "complete":
        break` 

The final response will look like this:

`{
    'status': 'complete',
    'pages': [
        {
            'bboxes': [
                {'bbox': [0.0, 0.0, 1334.0, 1625.0],
                'position': 0,
                'label': 'Table',
                'polygon': [[0, 0], [1334, 0], [1334, 1625], [0, 1625]]}
            ],
            'image_bbox': [0.0, 0.0, 1336.0, 1626.0],
            'page': 1
        }
    ],
    'success': True,
    'error': '',
    'page_count': 5
}` 

If success is `False`, you will get an error code along with the response.

All response data will be deleted from datalab servers an hour after the processing is complete, so make sure to get your results by then.

### Response fields

-   `status` - indicates the status of the request (`complete`, or `processing`).
-   `success` - indicates if the request completed successfully. `True` or `False`.
-   `error` - If there was an error, this is the error message.
-   `page_count` - number of pages we ran layout on.
-   `pages` - a list containing one dictionary per input page. The fields are:
    -   `bboxes` - detected layout bounding boxes.
        -   `bbox` - the axis-aligned rectangle for the text line in (x1, y1, x2, y2) format. (x1, y1) is the top left corner, and (x2, y2) is the bottom right corner.
        -   `polygon` - the polygon for the text line in (x1, y1), (x2, y2), (x3, y3), (x4, y4) format. The points are in clockwise order from the top left.
        -   `label` - the label for the bbox. One of `Caption`, `Footnote`, `Formula`, `List-item`, `Page-footer`, `Page-header`, `Picture`, `Figure`, `Section-header`, `Table`, `Text`, `Title`.
        -   `position` - the reading order of this bbox within the page.
    -   `page` - the page number in the input file
    -   `image_bbox` - the bbox for the page image in (x1, y1, x2, y2) format. (x1, y1) is the top left corner, and (x2, y2) is the bottom right corner. All layout bboxes will be contained within this bbox.

### Supported file types

Layout supports the following extensions and mime types:

-   PDF - `pdf`/`application/pdf`
-   Word document - `doc`/`application/msword`, `docx`/`application/vnd.openxmlformats-officedocument.wordprocessingml.document`
-   Powerpoint - `ppt`/`application/vnd.ms-powerpoint`, `pptx`/`application/vnd.openxmlformats-officedocument.presentationml.presentation`
-   Images - `png`/`image/png`, `jpeg`/`image/jpeg`, `wepb`/`image/webp`, `gif`/`image/gif`, `tiff`/`image/tiff`, `jpg`/`image/jpg`

You can automatically find the mimetype in python by installing `filetype`, then using `filetype.guess(FILEPATH).mime`.