# Reference Files

Use this folder for local Robinhood monthly statement PDFs that you want to import into the reporting tools.

Recommended workflow:

1. Download your Robinhood Derivatives monthly statement PDFs.
2. Place the PDFs in this folder.
3. Run the importer from the repository root.

Example:

```bash
./.venv/bin/python ./robinhood_event_contracts.py \
  --input-pdf ./_reference_files/*.pdf \
  --output-format table
```

Notes:

- PDF files in this folder are ignored by git.
- Keep statements local and do not commit account documents to the repository.
- The importer expands glob patterns itself, so quoted patterns like `'./_reference_files/*.pdf'` also work.
