# Approved reference library

The medical data assistant cites only documents that are actually present here **and** marked
`"approved": true` in `manifest.json`. This keeps it from citing literature it does not have.

The repository ships with no third-party documents. To add one (for example a NASA Human Research
Program evidence report that you have the right to use):

1. Save it as `.md` or `.txt` in this folder.
2. Add an entry to `manifest.json`:

```json
{"file": "hrp-example.txt", "title": "Document title", "publisher": "NASA", "url": "https://...",
 "license": "Public domain (U.S. Government work)", "approved": true, "approved_by": "reviewer name"}
```

3. Restart the backend (the index is rebuilt at start-up and hourly). `GET /api/assistant/status` lists
   each manifest entry and whether it loaded.
