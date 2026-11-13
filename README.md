# Minesweeper

A desktop version of the classic Minesweeper game, built with Python and [Flet](https://flet.dev).

The game features fair, guess-free boards, customizable controls and themes, smooth animations, and saved high scores.

## Features

- **Classic Minesweeper gameplay** with safe first clicks, automatic clearing of empty areas, flags, and win/loss detection.
- **Fair boards** designed to be solvable through logic, without random guesses whenever possible.
- **Chording** to reveal neighboring tiles when the surrounding flags match the number.
- **Four difficulty options:** Easy, Medium, Hard, and Custom.
- **Custom games** with adjustable board dimensions and mine count.
- **High scores** with the top five times saved for each standard difficulty.
- **Resizable interface** that adapts the board to the window size.
- **Dark and light themes**, with preset or custom accent colors.
- **Animations** for tile reveals, flags, hovering, and winning. Animations can be disabled in Settings.
- **Customizable keyboard shortcuts** and settings saved between sessions.

## Controls

| Action | Default control |
|---|---|
| Reveal a tile | Left-click |
| Place or remove a flag | Right-click (after the first click) |
| Chord | Hold `Space` on a revealed number |
| Restart the game | `R` |
| Open or close a window | `Esc` |
| Toggle dark theme | `T` |
| Select Easy / Medium / Hard / Custom | `1` / `2` / `3` / `4` |
| Open high scores | `H` |

You can change any keyboard shortcut in **Settings → Controls**.

## Getting started

### Requirements

- Python 3.10 or later

### Install and run

1. Clone the repository:

   ```bash
   git clone https://github.com/aacuke17-boop/Minesweeper.git
   cd Minesweeper
   ```

2. Install Flet:

   ```bash
   pip install flet
   ```

3. Start the game:

   ```bash
   python main.py
   ```

## Building an executable

To package the game as a standalone executable, install PyInstaller and run:

```bash
pip install pyinstaller
flet pack main.py --name Minesweeper
```

The packaged application will be created in the `dist/` directory. Build it on the operating system you want to target.
