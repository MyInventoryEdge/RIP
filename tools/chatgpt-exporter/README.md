# ChatGPT Conversation Exporter

Exports every loaded message from one ChatGPT conversation through a dedicated authenticated Edge session.

Start the dedicated Edge session, sign in there once, and leave that window open:

```powershell
.\start-authenticated-edge.ps1

# Enter ChatGPT authentication in the Edge window that opens.
& "C:\INVENTORY_EDGE\runtime\python314\python.exe" .\export_chatgpt.py "https://chatgpt.com/c/<conversation-id>" --output-dir .\export
```

The launcher uses `C:\RIP\tools\chatgpt-exporter\.chatgpt-edge-profile` and enables CDP at `http://127.0.0.1:9222`. The exporter attaches to the active session, creates one export tab, and closes only that tab; it never receives or stores authentication credentials.

Version 1 intentionally does not provide profile selection, profile discovery, Chrome support, or browser-management features.

It writes `conversation.json`, `conversation.md`, and `manifest.json` to the output directory. Markdown is reconstructed from the rendered conversation DOM, including headings, emphasis, links, lists, block quotes, and fenced code blocks.
