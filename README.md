# ViPDF

A keyboard-driven PDF viewer with Vim-style modal navigation, caret browsing, text selection, and annotation support.

Inspired by [zathura](https://github.com/pwmt/zathura), [qutebrowser](https://github.com/qutebrowser/qutebrowser), and [vim](https://www.vim.org/)

## Overview

ViPDF

ViPDF is PDF viewer designed for use without the mouse. It features vim-like modal keybinds, and importantly, annotation support.

## Usage

```bash
uv run main.py <file.pdf>
```

## Modes

ViPDF uses three modes:

| Mode | Description |
|------|-------------|
| **Normal** | Scroll and zoom the document |
| **Caret** | Move a cursor through the document text character by character |
| **Visual** | Select a range of text starting from the cursor position |

## Keybindings

Keybindings are defined in `keybinds.py`. The table below describes the general layout — refer to that file for the exact key mappings.

### Command Bar

Press `:` in any mode to open the command bar. A list of currently implemented commands are as follows:

| Command | Description |
|---------|-------------|
| `w` | Save the document (writes annotations back to the PDF) |
| `highlight` | Highlight the current Visual selection |
| `highlight -m "text"` | Highlight with a comment |
| `delete-annotation` | Delete the annotation under the caret |

Press `Tab` to autocomplete commands. Press `Escape` to dismiss the command bar.
