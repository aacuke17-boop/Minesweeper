import asyncio
import colorsys
import re
import time

import flet as ft

import storage
from game import Board

# Flet normally redraws the WHOLE page after every event. This game updates
# only the controls that changed, which is much faster, so auto-update is off.
ft.context.disable_auto_update()

# ---------------------------------------------------------------- constants

CELL_GAP = 3
MIN_CELL = 16
MAX_CELL = 56
BOARD_PAD = 12
PAGE_PAD = 16
HUD_MIN_WIDTH = 300

MIN_ROWS, MAX_ROWS = 5, 30
MIN_COLS, MAX_COLS = 5, 40
SAFE_ZONE = 9  # the first click and its 8 neighbors never hold mines

HOVER_SCALE = 1.05
POP_SCALE = 1.1
POP_LIMIT = 40  # bigger reveals skip the pop, which means far fewer updates
RIPPLE_STEPS = 8  # a reveal ripple is drawn in this many steps
HOVER_INTERVAL = 16  # ms: how often the board reports the cursor position

# the tile under the cursor gets a light white veil
HOVER_TINT = ft.BoxDecoration(
    bgcolor=ft.Colors.with_opacity(0.2, ft.Colors.WHITE), border_radius=6
)

# animation speeds in milliseconds (make smaller = faster)
EASE = ft.Animation(50, ft.AnimationCurve.EASE_OUT)  # buttons, pills, swatches
BOUNCE = ft.Animation(70, ft.AnimationCurve.EASE_OUT_BACK)
# the next four belong to the game itself: the Animations setting turns them off
CELL_COLOR_ANIM = ft.Animation(50, ft.AnimationCurve.EASE_OUT)
CELL_SCALE_ANIM = ft.Animation(40, ft.AnimationCurve.EASE_OUT)
INTRO_FADE = ft.Animation(80, ft.AnimationCurve.EASE_OUT)
INTRO_SCALE = ft.Animation(110, ft.AnimationCurve.EASE_OUT_BACK)

# name: (rows, cols, mines)
DIFFICULTIES = {
    "Easy": (9, 9, 10),
    "Medium": (16, 16, 40),
    "Hard": (16, 30, 99),
}
SCORE_MODES = tuple(DIFFICULTIES)  # highscores are kept for these only
PILL_ICONS = {
    "Easy": ft.Icons.SENTIMENT_SATISFIED,
    "Medium": ft.Icons.SENTIMENT_NEUTRAL,
    "Hard": ft.Icons.SENTIMENT_VERY_DISSATISFIED,
    "Custom": ft.Icons.TUNE,
}

ACCENTS = [
    ("Teal", "#009688"),
    ("Blue", "#2196F3"),
    ("Indigo", "#3F51B5"),
    ("Purple", "#9C27B0"),
    ("Pink", "#E91E63"),
    ("Red", "#F44336"),
    ("Orange", "#FF9800"),
    ("Amber", "#FFC107"),
    ("Green", "#4CAF50"),
    ("Cyan", "#00BCD4"),
    ("Brown", "#795548"),
    ("Grey", "#607D8B"),
]

NUMBER_COLORS = {
    1: ft.Colors.BLUE_400,
    2: ft.Colors.GREEN_500,
    3: ft.Colors.RED_400,
    4: ft.Colors.PURPLE_300,
    5: ft.Colors.ORANGE_600,
    6: ft.Colors.CYAN_500,
    7: ft.Colors.PINK_400,
    8: ft.Colors.GREY_500,
}
# Light theme: deeper, more saturated shades so the numbers stay readable
LIGHT_NUMBER_COLORS = {
    1: ft.Colors.BLUE_700,
    2: ft.Colors.GREEN_700,
    3: ft.Colors.RED_700,
    4: ft.Colors.PURPLE_700,
    5: ft.Colors.ORANGE_800,
    6: ft.Colors.CYAN_700,
    7: ft.Colors.PINK_700,
    8: ft.Colors.BLUE_GREY_700,
}

# (action id, label, icon)
ACTIONS = [
    ("restart", "Restart", ft.Icons.REFRESH),
    ("chord", "Chord (hold)", ft.Icons.TOUCH_APP),
    ("settings", "Settings / close window", ft.Icons.SETTINGS),
    ("theme", "Toggle dark theme", ft.Icons.DARK_MODE),
    ("easy", "Easy game", ft.Icons.SENTIMENT_SATISFIED),
    ("medium", "Medium game", ft.Icons.SENTIMENT_NEUTRAL),
    ("hard", "Hard game", ft.Icons.SENTIMENT_VERY_DISSATISFIED),
    ("custom", "Custom game", ft.Icons.TUNE),
    ("scores", "Highscores", ft.Icons.EMOJI_EVENTS),
]
DEFAULT_BINDS = {
    "restart": "R",
    "chord": "SPACE",
    "settings": "ESCAPE",
    "theme": "T",
    "easy": "1",
    "medium": "2",
    "hard": "3",
    "custom": "4",
    "scores": "H",
}
MODIFIER_PREFIXES = ("SHIFT", "CONTROL", "ALT", "META", "CAPS", "NUM LOCK", "FN")

CHORD_MOUSE = "MOUSE"  # the chord can also be bound to the middle mouse button
# keys whose label is a control character instead of a name
SPECIAL_KEYS = {
    " ": "SPACE",
    "\r": "ENTER",
    "\n": "ENTER",
    "\t": "TAB",
    "\b": "BACKSPACE",
    "\x7f": "DELETE",
}
KEYS_NOTE = "Click a button, then press the new key. Esc cancels."

HEX_LABEL = "Custom color (#RRGGBB)"
HEX_RE = re.compile(r"#[0-9a-fA-F]{6}")


def normalize_key(key: str) -> str:
    if key in SPECIAL_KEYS:
        return SPECIAL_KEYS[key]
    key = key.strip().upper()
    return "ESCAPE" if key == "ESC" else key


def pretty_key(key: str) -> str:
    if key == "ESCAPE":
        return "Esc"
    if key == CHORD_MOUSE:
        return "Middle mouse"
    return key if len(key) == 1 else key.title()


def light_tile_color(accent: str) -> str:
    """A stronger version of the accent, used for hidden tiles in the light theme."""
    r, g, b = (int(accent[i : i + 2], 16) / 255 for i in (1, 3, 5))
    h, _, s = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(h, 0.70, min(max(s, 0.40), 0.75))
    return f"#{round(r * 255):02X}{round(g * 255):02X}{round(b * 255):02X}"


class MinesweeperApp:
    def __init__(self, page: ft.Page):
        self.page = page

        # settings
        self.dark = True
        self.accent = ACCENTS[0][1]
        self.animations = True
        self.easy_mode = False
        self.fair_boards = True  # mines are laid out so no guessing is needed
        self.binds = dict(DEFAULT_BINDS)
        self.key_map: dict[str, str] = {}  # key -> action (see refresh_key_map)
        self.rebinding: str | None = None
        self.last_rebind_at = 0.0

        # dialogs
        self.current_dialog: str | None = None  # "settings" or "custom"
        self.dialog_closed_at = 0.0

        # game state
        self.difficulty = "Easy"
        self.custom = (12, 12, 25)  # rows, cols, mines
        self.custom_draft = self.custom
        self.board = Board(*DIFFICULTIES[self.difficulty])
        self.cell_boxes: list[list[ft.Container]] = []
        self.cell_size = 40
        self.game_id = 0  # changes on every new game, stops old animations
        self.best: dict[str, float] = {}  # custom boards: best time of this session
        self.scores: dict[str, list[dict]] = {m: [] for m in SCORE_MODES}
        self.new_best = False
        self.rank: int | None = None  # place of the last win in the top list
        self.clear_armed = False

        # pointer / chord / highlight state
        self.hover: tuple[int, int] | None = None  # tile under the cursor
        self.highlight: set[tuple[int, int]] = set()  # tiles drawn highlighted
        self.chord_held = False
        self.chord_by_mouse = False
        self.chord_origin: tuple[int, int] | None = None  # tile it started on
        self.chord_moved = False  # moved to another tile while held

        # timer
        self.timer_token = 0
        self.start_time = 0.0
        self.elapsed = 0.0

        self.resize_token = 0

        self.load_state()

        self.build_ui()
        self.build_settings()
        self.build_custom_dialog()
        self.build_scores_dialog()
        self.apply_theme()
        self.new_game()
        page.run_task(self.delayed_layout)

    # ==================================================================
    # Small helpers
    # ==================================================================

    @staticmethod
    def set_text(control: ft.Text, value: str):
        """Update a Text only if its value really changed."""
        if control.value != value:
            control.value = value
            control.update()

    def key(self, action: str) -> str:
        return pretty_key(self.binds[action])

    def refresh_key_map(self):
        self.key_map = {bound: action for action, bound in self.binds.items()}

    def game_anim(self, anim):
        """A game animation, or None when the Animations setting is off."""
        return anim if self.animations else None

    def refocus(self, delay: float = 0.1):
        """Give the keyboard focus back to the game.

        After a button was clicked, Space would otherwise "press" that button
        again instead of being used as the chord key.
        """
        self.page.run_task(self.refocus_task, delay)

    async def refocus_task(self, delay: float):
        await asyncio.sleep(delay)
        try:
            await self.key_listener.focus()
        except Exception:
            pass

    def config(self, difficulty: str | None = None) -> tuple[int, int, int]:
        name = difficulty or self.difficulty
        return self.custom if name == "Custom" else DIFFICULTIES[name]

    def best_key(self) -> str:
        if self.difficulty == "Custom":
            return "Custom {}x{}/{}".format(*self.custom)
        return self.difficulty

    def best_time(self) -> float | None:
        key = self.best_key()
        if key in self.scores:
            entries = self.scores[key]
            return entries[0]["time"] if entries else None
        return self.best.get(key)

    # ------------------------------------------------------------------
    # Saving & loading
    # ------------------------------------------------------------------

    def load_state(self):
        """Restore settings and highscores. Anything invalid is ignored."""
        data = storage.load()
        saved = data.get("settings")
        if not isinstance(saved, dict):
            saved = {}

        if isinstance(saved.get("dark"), bool):
            self.dark = saved["dark"]
        if isinstance(saved.get("animations"), bool):
            self.animations = saved["animations"]
        if isinstance(saved.get("easy_mode"), bool):
            self.easy_mode = saved["easy_mode"]
        if isinstance(saved.get("fair_boards"), bool):
            self.fair_boards = saved["fair_boards"]
        accent = saved.get("accent")
        if isinstance(accent, str) and HEX_RE.fullmatch(accent):
            self.accent = accent.upper()

        binds = saved.get("binds")
        if isinstance(binds, dict):
            for action in DEFAULT_BINDS:
                key = binds.get(action)
                if isinstance(key, str) and key.strip():
                    self.binds[action] = normalize_key(key)
            if len(set(self.binds.values())) != len(self.binds):
                others = [v for a, v in self.binds.items() if a != "chord"]
                if len(set(others)) == len(others):
                    self.binds["chord"] = CHORD_MOUSE  # only the chord key clashed
                else:
                    self.binds = dict(DEFAULT_BINDS)  # duplicate keys: start over

        custom = saved.get("custom")
        if (
            isinstance(custom, list)
            and len(custom) == 3
            and all(isinstance(v, int) and not isinstance(v, bool) for v in custom)
        ):
            rows = min(max(custom[0], MIN_ROWS), MAX_ROWS)
            cols = min(max(custom[1], MIN_COLS), MAX_COLS)
            mines = min(max(custom[2], 1), rows * cols - SAFE_ZONE)
            self.custom = self.custom_draft = (rows, cols, mines)

        if saved.get("difficulty") in (*DIFFICULTIES, "Custom"):
            self.difficulty = saved["difficulty"]

        self.scores = storage.clean_scores(data.get("scores"), SCORE_MODES)
        self.refresh_key_map()

    def save_state(self):
        storage.save(
            {
                "settings": {
                    "dark": self.dark,
                    "animations": self.animations,
                    "easy_mode": self.easy_mode,
                    "fair_boards": self.fair_boards,
                    "accent": self.accent,
                    "binds": self.binds,
                    "difficulty": self.difficulty,
                    "custom": list(self.custom),
                },
                "scores": self.scores,
            }
        )

    def default_hint(self) -> str:
        return (
            f"Click: reveal · Right click: flag · {self.key('chord')}: chord · "
            f"{self.key('restart')}: restart · {self.key('settings')}: settings"
        )

    def pill_tooltip(self, name: str) -> str:
        rows, cols, mines = self.config(name)
        return f"{rows}×{cols}, {mines} mines ({self.key(name.lower())})"

    # ==================================================================
    # UI construction
    # ==================================================================

    def build_ui(self):
        page = self.page
        page.title = "Minesweeper"
        page.padding = PAGE_PAD
        page.spacing = 14
        page.scroll = ft.ScrollMode.AUTO
        page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        page.window.width = 900
        page.window.height = 720
        page.window.min_width = 360
        page.window.min_height = 520
        page.on_resize = self.on_resize
        page.on_keyboard_event = self.on_key

        # top bar: flags left, smiley (restart), timer
        self.mines_text = ft.Text("0", size=20, weight=ft.FontWeight.BOLD)
        self.timer_text = ft.Text("0.000", size=20, weight=ft.FontWeight.BOLD)
        self.face_icon = ft.Icon(
            icon=ft.Icons.SENTIMENT_SATISFIED_ALT,
            size=34,
            color=ft.Colors.ON_PRIMARY_CONTAINER,
        )
        self.face = ft.Container(
            content=self.face_icon,
            width=56,
            height=56,
            alignment=ft.Alignment.CENTER,
            border_radius=28,
            bgcolor=ft.Colors.PRIMARY_CONTAINER,
            ink=True,
            tooltip=f"Restart ({self.key('restart')})",
            on_click=self.on_restart,
            scale=1,
            animate_scale=self.game_anim(BOUNCE),
        )
        self.hud = ft.Container(
            width=HUD_MIN_WIDTH,
            content=ft.Row(
                [
                    self.chip(ft.Icons.FLAG, self.mines_text, 100),
                    self.face,
                    self.chip(ft.Icons.TIMER, self.timer_text, 132),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        # difficulty pills + settings button
        self.pills: dict[str, ft.Container] = {}
        self.pill_parts: dict[str, tuple[ft.Icon, ft.Text]] = {}
        for name in [*DIFFICULTIES, "Custom"]:
            icon = ft.Icon(icon=PILL_ICONS[name], size=18)
            label = ft.Text(name, weight=ft.FontWeight.BOLD)
            self.pill_parts[name] = (icon, label)
            self.pills[name] = ft.Container(
                content=ft.Row([icon, label], spacing=6, tight=True),
                padding=ft.Padding.symmetric(vertical=6, horizontal=14),
                border_radius=20,
                ink=True,
                tooltip=self.pill_tooltip(name),
                on_click=self.make_difficulty_handler(name),
                animate=EASE,
            )
        self.scores_btn = ft.IconButton(
            icon=ft.Icons.EMOJI_EVENTS,
            tooltip=f"Highscores ({self.key('scores')})",
            on_click=self.open_scores,
        )
        self.settings_btn = ft.IconButton(
            icon=ft.Icons.SETTINGS,
            tooltip=f"Settings ({self.key('settings')})",
            on_click=self.open_settings,
        )
        pills_row = ft.Row(
            [*self.pills.values(), self.scores_btn, self.settings_btn],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True,
            spacing=8,
            run_spacing=8,
        )

        # board: ONE detector for the whole grid (see "the board" further down)
        self.grid = ft.Column(spacing=CELL_GAP, tight=True)
        self.board_input = ft.GestureDetector(
            content=self.grid,
            mouse_cursor=ft.MouseCursor.CLICK,
            hover_interval=HOVER_INTERVAL,
            on_hover=self.on_hover,
            on_exit=self.on_exit,
            on_tap_up=self.on_tap_up,
            on_secondary_tap_up=self.on_secondary_tap_up,
            on_tertiary_tap_down=self.on_middle_down,
            on_tertiary_tap_up=self.on_middle_up,
            on_tertiary_tap_cancel=self.on_middle_cancel,
        )
        self.board_card = ft.Container(
            content=self.board_input,
            padding=BOARD_PAD,
            border_radius=18,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            shadow=ft.BoxShadow(
                blur_radius=24,
                color=ft.Colors.with_opacity(0.25, ft.Colors.BLACK),
                offset=ft.Offset(0, 8),
            ),
            opacity=1,
            scale=1,
        )

        self.hint_text = ft.Text(
            self.default_hint(),
            size=13,
            color=ft.Colors.ON_SURFACE_VARIANT,
            text_align=ft.TextAlign.CENTER,
        )

        # The listener tells us when the chord key is pressed AND released.
        self.key_listener = ft.KeyboardListener(
            content=ft.Column(
                [self.hud, pills_row, self.board_card, self.hint_text],
                spacing=14,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            autofocus=True,
            on_key_down=self.on_key_down,
            on_key_up=self.on_key_up,
        )
        page.add(self.key_listener)
        page.update()

    def chip(self, icon, text: ft.Text, width: int) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [ft.Icon(icon=icon, size=22, color=ft.Colors.PRIMARY), text],
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            width=width,
            padding=ft.Padding.symmetric(vertical=10, horizontal=10),
            border_radius=14,
            alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        )

    # ------------------------------------------------------------------
    # Settings dialog (main view + keybinds view)
    # ------------------------------------------------------------------

    def build_settings(self):
        self.dark_switch = ft.Switch(
            label="Dark theme", value=self.dark, on_change=self.on_dark_change
        )
        self.anim_switch = ft.Switch(
            label="Animations", value=self.animations, on_change=self.on_anim_change
        )
        self.fair_switch = ft.Switch(
            label="Fair boards",
            tooltip=(
                "New boards are laid out so that logic alone can solve them, "
                "without guessing (when the mine density allows it)"
            ),
            value=self.fair_boards,
            on_change=self.on_fair_change,
        )
        self.easy_switch = ft.Switch(
            label="Easy mode",
            tooltip="Highlights the tiles around the one under the cursor",
            value=self.easy_mode,
            on_change=self.on_easy_change,
        )

        self.swatches: dict[str, ft.Container] = {}
        for name, color in ACCENTS:
            self.swatches[color] = ft.Container(
                width=34,
                height=34,
                border_radius=17,
                bgcolor=color,
                tooltip=name,
                animate=EASE,
                on_click=self.make_accent_handler(color),
            )
        self.refresh_swatches()

        self.hex_field = ft.TextField(
            label=HEX_LABEL,
            value=self.accent,
            expand=True,
            on_submit=self.apply_hex,
        )

        self.settings_main = ft.Column(
            [
                ft.Row([ft.Icon(icon=ft.Icons.DARK_MODE), self.dark_switch]),
                ft.Row([ft.Icon(icon=ft.Icons.ANIMATION), self.anim_switch]),
                ft.Row([ft.Icon(icon=ft.Icons.GRID_ON), self.easy_switch]),
                ft.Row([ft.Icon(icon=ft.Icons.LIGHTBULB), self.fair_switch]),
                ft.Row(
                    [
                        ft.Icon(icon=ft.Icons.PALETTE),
                        ft.Text("Accent color", weight=ft.FontWeight.BOLD),
                    ]
                ),
                ft.Row(list(self.swatches.values()), wrap=True, spacing=8, run_spacing=8),
                ft.Row(
                    [
                        self.hex_field,
                        ft.Button(content="Apply", on_click=self.apply_hex),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(),
                ft.Button(
                    content="Controls",
                    icon=ft.Icons.KEYBOARD,
                    on_click=lambda e: self.show_settings_view("keys"),
                ),
            ],
            tight=True,
            width=340,
            spacing=12,
        )

        self.bind_buttons: dict[str, ft.Button] = {}
        bind_rows = []
        for action, label, icon in ACTIONS:
            button = ft.Button(
                content=pretty_key(self.binds[action]),
                width=130,
                on_click=self.make_rebind_handler(action),
            )
            self.bind_buttons[action] = button
            bind_rows.append(
                ft.Row(
                    [ft.Icon(icon=icon, size=20), ft.Text(label, expand=True), button],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )

        self.keys_note = ft.Text(
            KEYS_NOTE, size=12, color=ft.Colors.ON_SURFACE_VARIANT
        )
        self.settings_keys = ft.Column(
            [
                ft.Row(
                    [
                        ft.IconButton(
                            icon=ft.Icons.ARROW_BACK,
                            tooltip="Back",
                            on_click=lambda e: self.show_settings_view("main"),
                        ),
                        ft.Text("Controls", size=16, weight=ft.FontWeight.BOLD),
                    ]
                ),
                self.keys_note,
                *bind_rows,
                ft.TextButton(
                    content="Use the middle mouse button for chord",
                    icon=ft.Icons.MOUSE,
                    on_click=self.use_mouse_chord,
                ),
                ft.Text(
                    "Chord: hold it on a number to highlight the tiles around it, "
                    "release to open them when the flags match the number. Moving "
                    "to another tile only moves the highlight.",
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.TextButton(
                    content="Reset to defaults",
                    icon=ft.Icons.RESTORE,
                    on_click=self.reset_binds,
                ),
            ],
            tight=True,
            width=340,
            spacing=8,
        )

        self.settings_dialog = ft.AlertDialog(
            title=ft.Row(
                [ft.Icon(icon=ft.Icons.SETTINGS), ft.Text("Settings")], spacing=10
            ),
            content=self.settings_main,
            scrollable=True,
            actions=[ft.TextButton(content="Close", on_click=self.close_dialog)],
            on_dismiss=self.on_dialog_dismiss,
        )

    def show_settings_view(self, name: str, update: bool = True):
        self.rebinding = None
        self.settings_dialog.content = (
            self.settings_main if name == "main" else self.settings_keys
        )
        if update:
            self.refresh_bind_buttons()
            self.settings_dialog.update()

    # ------------------------------------------------------------------
    # Custom game dialog
    # ------------------------------------------------------------------

    def build_custom_dialog(self):
        rows, cols, mines = self.custom
        self.rows_label = ft.Text()
        self.cols_label = ft.Text()
        self.mines_label = ft.Text()
        self.custom_info = ft.Text(size=13, color=ft.Colors.ON_SURFACE_VARIANT)

        self.rows_slider = ft.Slider(
            min=MIN_ROWS,
            max=MAX_ROWS,
            divisions=MAX_ROWS - MIN_ROWS,
            value=rows,
            on_change=self.on_custom_change,
        )
        self.cols_slider = ft.Slider(
            min=MIN_COLS,
            max=MAX_COLS,
            divisions=MAX_COLS - MIN_COLS,
            value=cols,
            on_change=self.on_custom_change,
        )
        self.mines_slider = ft.Slider(
            min=1,
            max=rows * cols - SAFE_ZONE,
            value=mines,
            on_change=self.on_custom_change,
        )
        self.refresh_custom(update=False)

        self.custom_dialog = ft.AlertDialog(
            title=ft.Row(
                [ft.Icon(icon=ft.Icons.TUNE), ft.Text("Custom game")], spacing=10
            ),
            content=ft.Column(
                [
                    self.rows_label,
                    self.rows_slider,
                    self.cols_label,
                    self.cols_slider,
                    self.mines_label,
                    self.mines_slider,
                    self.custom_info,
                ],
                tight=True,
                width=340,
                spacing=2,
            ),
            actions=[
                ft.TextButton(content="Cancel", on_click=self.close_dialog),
                ft.Button(
                    content="Start", icon=ft.Icons.PLAY_ARROW, on_click=self.start_custom
                ),
            ],
            on_dismiss=self.on_dialog_dismiss,
        )

    def refresh_custom(self, update: bool = True):
        rows = round(self.rows_slider.value)
        cols = round(self.cols_slider.value)
        max_mines = rows * cols - SAFE_ZONE
        mines = max(1, min(round(self.mines_slider.value), max_mines))

        self.mines_slider.max = max_mines
        if round(self.mines_slider.value) != mines:
            self.mines_slider.value = mines

        self.custom_draft = (rows, cols, mines)
        self.rows_label.value = f"Rows: {rows}"
        self.cols_label.value = f"Columns: {cols}"
        self.mines_label.value = f"Mines: {mines}"
        density = mines * 100 / (rows * cols)
        self.custom_info.value = f"{rows * cols} cells · {density:.0f}% mines"

        if update:
            for control in (
                self.rows_label,
                self.cols_label,
                self.mines_label,
                self.mines_slider,
                self.custom_info,
            ):
                control.update()

    def on_custom_change(self, e):
        self.refresh_custom()

    def open_custom(self, e=None):
        if self.current_dialog:
            return
        rows, cols, mines = self.custom
        self.rows_slider.value = rows
        self.cols_slider.value = cols
        self.mines_slider.max = rows * cols - SAFE_ZONE
        self.mines_slider.value = mines
        self.refresh_custom(update=False)
        self.show_dialog("custom", self.custom_dialog)

    def start_custom(self, e=None):
        self.custom = self.custom_draft
        self.difficulty = "Custom"
        self.save_state()
        self.close_dialog()
        self.new_game()

    # ------------------------------------------------------------------
    # Highscores dialog
    # ------------------------------------------------------------------

    def build_scores_dialog(self):
        self.scores_body = ft.Column(tight=True, width=340, spacing=10)
        self.clear_btn = ft.TextButton(
            content="Clear highscores",
            icon=ft.Icons.DELETE_OUTLINE,
            on_click=self.on_clear_scores,
        )
        self.scores_dialog = ft.AlertDialog(
            title=ft.Row(
                [ft.Icon(icon=ft.Icons.EMOJI_EVENTS), ft.Text("Highscores")],
                spacing=10,
            ),
            content=self.scores_body,
            scrollable=True,
            actions=[
                self.clear_btn,
                ft.TextButton(content="Close", on_click=self.close_dialog),
            ],
            on_dismiss=self.on_dialog_dismiss,
        )

    def refresh_scores(self):
        """Build the list only when the dialog opens, never during play."""
        muted = ft.Colors.ON_SURFACE_VARIANT
        sections: list[ft.Control] = []
        for mode in SCORE_MODES:
            rows, cols, mines = DIFFICULTIES[mode]
            if sections:
                sections.append(ft.Divider(height=1))
            sections.append(
                ft.Row(
                    [
                        ft.Icon(icon=PILL_ICONS[mode], size=20, color=ft.Colors.PRIMARY),
                        ft.Text(mode, weight=ft.FontWeight.BOLD),
                        ft.Text(f"{rows}×{cols} · {mines} mines", size=12, color=muted),
                    ],
                    spacing=8,
                )
            )
            entries = self.scores[mode]
            if not entries:
                sections.append(ft.Text("No wins yet", size=13, color=muted))
            for place, entry in enumerate(entries):
                latest = mode == self.difficulty and place == self.rank
                color = ft.Colors.PRIMARY if latest else None
                sections.append(
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Text(f"{place + 1}.", color=muted),
                                width=26,
                            ),
                            ft.Text(
                                self.format_time(entry["time"]),
                                weight=ft.FontWeight.BOLD,
                                color=color,
                                expand=True,
                            ),
                            ft.Text(entry["date"], size=12, color=muted),
                        ],
                        spacing=4,
                    )
                )
        self.scores_body.controls = sections

    def open_scores(self, e=None):
        if self.current_dialog:
            return
        self.clear_armed = False
        self.clear_btn.content = "Clear highscores"
        self.refresh_scores()
        self.show_dialog("scores", self.scores_dialog)

    def on_clear_scores(self, e=None):
        if not self.clear_armed:  # ask for a second click first
            self.clear_armed = True
            self.clear_btn.content = "Click again to confirm"
            self.clear_btn.update()
            return
        self.clear_armed = False
        self.clear_btn.content = "Clear highscores"
        self.scores = {mode: [] for mode in SCORE_MODES}
        self.rank = None
        self.save_state()
        self.refresh_scores()
        self.scores_dialog.update()

    # ------------------------------------------------------------------
    # Dialog helpers
    # ------------------------------------------------------------------

    def show_dialog(self, name: str, dialog: ft.AlertDialog):
        self.chord_end(False)
        self.current_dialog = name
        self.page.show_dialog(dialog)
        self.page.update()

    def close_dialog(self, e=None):
        if not self.current_dialog:
            return
        self.on_dialog_dismiss()
        try:
            self.page.pop_dialog()
            self.page.update()
        except Exception:
            pass

    def on_dialog_dismiss(self, e=None):
        self.current_dialog = None
        self.rebinding = None
        self.dialog_closed_at = time.perf_counter()
        self.refocus(0.2)  # the dialog gave the focus to one of its buttons

    def open_settings(self, e=None):
        if self.current_dialog:
            return
        self.show_settings_view("main", update=False)
        self.show_dialog("settings", self.settings_dialog)

    # ==================================================================
    # Theme & settings
    # ==================================================================

    def apply_theme(self):
        # light theme: stronger tile and number colors, dark theme: unchanged
        if self.dark:
            self.hidden_color = ft.Colors.PRIMARY_CONTAINER
            self.number_colors = NUMBER_COLORS
        else:
            self.hidden_color = light_tile_color(self.accent)
            self.number_colors = LIGHT_NUMBER_COLORS
        # chord / easy-mode highlight: the real accent colour
        self.highlight_fill = ft.Colors.with_opacity(0.6, self.accent)
        self.highlight_border = ft.Border.all(2, self.accent)
        self.restyle_all()

        self.page.theme = ft.Theme(color_scheme_seed=self.accent)
        self.page.dark_theme = ft.Theme(color_scheme_seed=self.accent)
        self.page.theme_mode = ft.ThemeMode.DARK if self.dark else ft.ThemeMode.LIGHT
        self.page.update()

    def set_dark(self, value: bool):
        self.dark = value
        self.dark_switch.value = value
        self.apply_theme()
        self.save_state()

    def toggle_dark(self):
        self.set_dark(not self.dark)

    def on_dark_change(self, e):
        self.set_dark(e.control.value)

    def on_anim_change(self, e):
        self.animations = e.control.value
        self.save_state()
        self.apply_game_animations()

    def apply_game_animations(self):
        """Turn the game's own animations on or off (buttons keep theirs)."""
        on = self.animations
        for row in self.cell_boxes:
            for box in row:
                box.animate = CELL_COLOR_ANIM if on else None
                box.animate_scale = CELL_SCALE_ANIM if on else None
                box.scale = 1
        self.face.animate_scale = BOUNCE if on else None
        self.board_card.animate_opacity = INTRO_FADE if on else None
        self.board_card.animate_scale = INTRO_SCALE if on else None
        self.board_card.opacity = 1
        self.board_card.scale = 1
        self.face.update()
        self.board_card.update()

    def on_fair_change(self, e):
        self.fair_boards = e.control.value
        self.save_state()
        if not self.board.mines_placed:
            self.board.fair = self.fair_boards  # this board has no mines yet

    def on_easy_change(self, e):
        self.easy_mode = e.control.value
        self.save_state()
        self.refresh_highlight()

    def make_accent_handler(self, color: str):
        def handler(e):
            self.set_accent(color)

        return handler

    def set_accent(self, color: str):
        self.accent = color
        self.hex_field.value = color
        self.hex_field.label = HEX_LABEL
        self.hex_field.border_color = None
        self.refresh_swatches()
        self.apply_theme()
        self.save_state()

    def refresh_swatches(self):
        for color, swatch in self.swatches.items():
            selected = color.lower() == self.accent.lower()
            swatch.border = ft.Border.all(3, ft.Colors.ON_SURFACE) if selected else None

    def apply_hex(self, e=None):
        value = (self.hex_field.value or "").strip().lstrip("#")
        if re.fullmatch(r"[0-9a-fA-F]{6}", value):
            self.set_accent("#" + value.upper())
        else:
            self.hex_field.label = "Invalid color, use #RRGGBB"
            self.hex_field.border_color = ft.Colors.ERROR
            self.hex_field.update()

    # ==================================================================
    # Keybinds
    # ==================================================================

    def on_key(self, e: ft.KeyboardEvent):
        key = normalize_key(e.key)

        if self.rebinding:
            self.handle_rebind(key)
            return
        if e.ctrl or e.alt or e.meta:
            return

        action = self.key_map.get(key)
        if action is None:
            return  # (the chord key is handled by the keyboard listener)

        if action == "settings":
            if self.current_dialog:
                self.close_dialog()
            elif time.perf_counter() - self.dialog_closed_at > 0.3:
                # (the delay stops the same key press that just closed
                # the dialog from opening it again)
                self.open_settings()
            return

        if self.current_dialog:
            return
        if action == "restart":
            self.new_game()
        elif action in ("easy", "medium", "hard"):
            self.new_game(action.title())
        elif action == "custom":
            self.open_custom()
        elif action == "scores":
            self.open_scores()
        elif action == "theme":
            self.toggle_dark()

    def make_rebind_handler(self, action: str):
        def handler(e):
            if time.perf_counter() - self.last_rebind_at < 0.25:
                return  # Space/Enter just "pressed" the focused button again
            self.rebinding = None if self.rebinding == action else action
            self.refresh_bind_buttons()

        return handler

    def handle_rebind(self, key: str):
        if not key or key.startswith(MODIFIER_PREFIXES):
            return  # wait for a real key
        action = self.rebinding
        if key == "ESCAPE":  # cancel
            self.rebinding = None
            self.refresh_bind_buttons()
            return

        old_key = self.binds[action]
        for other, bound in self.binds.items():
            if other != action and bound == key:
                if old_key == CHORD_MOUSE:
                    # the mouse button can't be handed to another action
                    self.rebinding = None
                    self.refresh_bind_buttons()
                    self.set_text(
                        self.keys_note, f"{pretty_key(key)} is already used elsewhere"
                    )
                    return
                self.binds[other] = old_key  # swap, so nothing is left unbound

        if action == "chord":
            self.chord_end(False)
        self.binds[action] = key
        self.rebinding = None
        self.last_rebind_at = time.perf_counter()
        self.set_text(self.keys_note, KEYS_NOTE)
        self.refresh_key_map()
        self.refresh_bind_buttons()
        self.refresh_key_labels()
        self.save_state()

    def use_mouse_chord(self, e=None):
        if self.binds["chord"] == CHORD_MOUSE:
            return
        self.chord_end(False)
        self.binds["chord"] = CHORD_MOUSE
        self.rebinding = None
        self.set_text(self.keys_note, KEYS_NOTE)
        self.refresh_key_map()
        self.refresh_bind_buttons()
        self.refresh_key_labels()
        self.save_state()

    def reset_binds(self, e=None):
        self.chord_end(False)
        self.binds = dict(DEFAULT_BINDS)
        self.rebinding = None
        self.set_text(self.keys_note, KEYS_NOTE)
        self.refresh_key_map()
        self.refresh_bind_buttons()
        self.refresh_key_labels()
        self.save_state()

    def refresh_bind_buttons(self):
        for action, button in self.bind_buttons.items():
            text = (
                "Press a key…"
                if self.rebinding == action
                else pretty_key(self.binds[action])
            )
            if button.content != text:
                button.content = text
                button.update()

    def refresh_key_labels(self):
        """Update tooltips and the hint after the binds changed."""
        self.face.tooltip = f"Restart ({self.key('restart')})"
        self.face.update()
        self.settings_btn.tooltip = f"Settings ({self.key('settings')})"
        self.settings_btn.update()
        self.scores_btn.tooltip = f"Highscores ({self.key('scores')})"
        self.scores_btn.update()
        for name, pill in self.pills.items():
            pill.tooltip = self.pill_tooltip(name)
            pill.update()
        self.update_hud()

    # ==================================================================
    # Adaptive layout
    # ==================================================================

    def compute_cell_size(self) -> int:
        pw = self.page.width or 900
        ph = self.page.height or 720
        header = 195 if pw < 520 else 175  # top bar + pills + hint + spacing
        avail_w = pw - 2 * PAGE_PAD - 2 * BOARD_PAD
        avail_h = ph - header - 2 * PAGE_PAD - 2 * BOARD_PAD
        cols, rows = self.board.cols, self.board.rows
        size_w = (avail_w - (cols - 1) * CELL_GAP) / cols
        size_h = (avail_h - (rows - 1) * CELL_GAP) / rows
        return int(max(MIN_CELL, min(MAX_CELL, size_w, size_h)))

    def label_size(self) -> int:
        return max(10, int(self.cell_size * 0.5))

    def hud_width(self) -> int:
        cols = self.board.cols
        board_w = cols * self.cell_size + (cols - 1) * CELL_GAP + 2 * BOARD_PAD
        pw = self.page.width or 900
        return int(min(max(board_w, HUD_MIN_WIDTH), pw - 2 * PAGE_PAD))

    def apply_layout(self):
        size = self.compute_cell_size()
        changed = size != self.cell_size
        if changed:
            self.cell_size = size
            font = self.label_size()
            for row in self.cell_boxes:
                for box in row:
                    box.width = size
                    box.height = size
                    box.content.size = font
            self.board_card.update()

        width = self.hud_width()
        if self.hud.width != width:
            self.hud.width = width
            self.hud.update()

    async def on_resize(self, e):
        # debounce: react only when the user pauses resizing for a moment
        self.resize_token += 1
        token = self.resize_token
        await asyncio.sleep(0.04)
        if token == self.resize_token:
            self.apply_layout()

    async def delayed_layout(self):
        await asyncio.sleep(0.2)
        self.apply_layout()

    # ==================================================================
    # Game flow
    # ==================================================================

    def new_game(self, difficulty: str | None = None):
        if difficulty and difficulty != self.difficulty:
            self.difficulty = difficulty
            self.save_state()  # remember the last played difficulty
        rows, cols, mines = self.config()

        self.game_id += 1
        self.stop_timer()
        self.elapsed = 0.0
        self.new_best = False
        self.rank = None

        same_shape = (
            bool(self.cell_boxes)
            and len(self.cell_boxes) == rows
            and len(self.cell_boxes[0]) == cols
        )
        self.board = Board(rows, cols, mines, fair=self.fair_boards)
        self.highlight = set()
        self.chord_held = False
        self.chord_origin = None
        if not same_shape:
            self.hover = None
        size = self.compute_cell_size()

        if same_shape and size == self.cell_size:
            self.reset_cells()  # reuse the controls, much faster than rebuilding
        else:
            self.cell_size = size
            self.build_grid()

        self.set_text(self.timer_text, "0.000")
        self.hud.width = self.hud_width()
        self.hud.update()
        self.update_pills()
        self.update_hud()

        if self.animations:
            # start hidden and small (instantly), then fade and scale in
            self.board_card.animate_opacity = None
            self.board_card.animate_scale = None
            self.board_card.opacity = 0
            self.board_card.scale = 0.94
            self.board_card.update()
            self.page.run_task(self.intro_animation, self.game_id)
        else:
            self.board_card.opacity = 1
            self.board_card.scale = 1
            self.board_card.update()

    async def intro_animation(self, game_id: int):
        await asyncio.sleep(0.01)
        if game_id != self.game_id:
            return
        self.board_card.animate_opacity = INTRO_FADE
        self.board_card.animate_scale = INTRO_SCALE
        self.board_card.opacity = 1
        self.board_card.scale = 1
        self.board_card.update()

    def reset_cells(self):
        for row in self.cell_boxes:
            for box in row:
                box.bgcolor = self.hidden_color
                box.border = None
                box.foreground_decoration = None
                box.scale = 1
                box.content.value = ""
        if self.hover is not None:  # the cursor is still resting on a tile
            self.style_cell(*self.hover)

    def build_grid(self):
        size = self.cell_size
        font = self.label_size()
        color_anim = self.game_anim(CELL_COLOR_ANIM)
        scale_anim = self.game_anim(CELL_SCALE_ANIM)
        self.cell_boxes = []
        rows_ui = []

        for _ in range(self.board.rows):
            boxes = [
                ft.Container(
                    width=size,
                    height=size,
                    alignment=ft.Alignment.CENTER,
                    border_radius=6,
                    bgcolor=self.hidden_color,
                    content=ft.Text("", size=font, weight=ft.FontWeight.BOLD),
                    scale=1,
                    animate=color_anim,
                    animate_scale=scale_anim,
                )
                for _ in range(self.board.cols)
            ]
            self.cell_boxes.append(boxes)
            rows_ui.append(ft.Row(boxes, spacing=CELL_GAP, tight=True))

        self.grid.controls = rows_ui

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def make_difficulty_handler(self, name: str):
        def handler(e):
            if name == "Custom":
                self.open_custom()
            else:
                self.new_game(name)
                self.refocus()

        return handler

    def on_restart(self, e=None):
        self.new_game()
        self.refocus()

    # ---------- the board: ONE detector for all tiles ----------
    # The whole grid sits inside a single GestureDetector. It reports where the
    # pointer is, and we work out which tile that is. This is far lighter than a
    # detector per tile, and every tile owns a full square (the tile plus half
    # of the gap on each side), so there are no dead spots between tiles.

    def tile_at(self, pos) -> tuple[int, int] | None:
        if pos is None:
            return None
        pitch = self.cell_size + CELL_GAP
        c = int((pos.x + CELL_GAP / 2) // pitch)
        r = int((pos.y + CELL_GAP / 2) // pitch)
        if 0 <= r < self.board.rows and 0 <= c < self.board.cols:
            return r, c
        return None

    def on_tap_up(self, e):
        tile = self.tile_at(e.local_position)
        if tile:
            self.on_reveal(*tile)

    def on_secondary_tap_up(self, e):
        tile = self.tile_at(e.local_position)
        if tile:
            self.toggle_flag(*tile)

    def on_hover(self, e):
        tile = self.tile_at(e.local_position)
        if tile == self.hover:
            return
        old, self.hover = self.hover, tile
        self.move_hover(old, tile)
        if self.chord_held and self.chord_origin is not None and tile != self.chord_origin:
            self.chord_moved = True  # no reveal on release anymore
        if self.easy_mode or self.chord_held:
            self.refresh_highlight()

    def on_exit(self, e):
        old, self.hover = self.hover, None
        self.move_hover(old, None)
        if self.chord_held and self.chord_origin is not None:
            self.chord_moved = True  # the cursor left the board
        if self.easy_mode or self.chord_held:
            self.refresh_highlight()

    def move_hover(self, old, new):
        """Hover feedback: a light veil on the tile under the cursor (plus a
        small grow when animations are on). style_cell() sets or clears the veil."""
        board = self.board
        for tile in {old, new} - {None}:
            r, c = tile
            self.style_cell(r, c)
            box = self.cell_boxes[r][c]
            if self.animations:
                active = (
                    tile == self.hover
                    and not board.game_over
                    and not board.grid[r][c].is_revealed
                )
                box.scale = HOVER_SCALE if active else 1
            box.update()

    def toggle_flag(self, r: int, c: int):
        board = self.board
        if not board.mines_placed:
            if not board.game_over:
                self.set_text(
                    self.hint_text, "Make your first click: flags unlock after that"
                )
            return

        was_flagged = board.grid[r][c].is_flagged
        board.toggle_flag(r, c)
        if board.grid[r][c].is_flagged == was_flagged:
            return  # nothing changed

        box = self.cell_boxes[r][c]
        self.style_cell(r, c)
        if self.animations:
            box.scale = 1.25
        box.update()
        self.update_hud()
        if self.animations:
            self.page.run_task(self.settle, box, self.game_id)

    def on_reveal(self, r: int, c: int):
        board = self.board
        if board.game_over:
            return
        first_click = not board.mines_placed
        self.after_reveal(board.reveal(r, c), (r, c), first_click)

    def after_reveal(self, cells, origin, first_click: bool = False):
        """Shared by a normal click and a chord: timer, game over, drawing."""
        board = self.board
        if not cells:
            return  # flagged / already open tile, or the flags didn't match

        if first_click:
            self.start_timer()

        if board.game_over:
            self.finish_game()
            if not board.won:
                # also show the remaining mines and the wrong flags
                for rr in range(board.rows):
                    for cc in range(board.cols):
                        cell = board.grid[rr][cc]
                        if not cell.is_revealed and cell.is_mine != cell.is_flagged:
                            cells.append((rr, cc))
            # the game is over: remove any highlight and hover veil still showing
            old, self.highlight = self.highlight, set()
            leftover = old.difference(cells)
            if self.hover is not None:
                leftover.add(self.hover)
            for rr, cc in leftover:
                self.style_cell(rr, cc)
                self.cell_boxes[rr][cc].update()

        self.update_hud()
        self.page.run_task(self.animate_cells, cells, origin, self.game_id, board.won)

    # ---------- chord (hold on a number) ----------
    # Hold the chord key (or the middle mouse button): the hidden tiles around
    # the number are highlighted. With the key, the highlight follows the cursor.
    # On release the tiles open, but only if you did not move to another tile
    # and the flags around the number match it.

    def chord_begin(self, tile, by_mouse: bool):
        if self.chord_held:
            self.chord_end(False)
        if self.board.game_over:
            return
        self.chord_held = True
        self.chord_by_mouse = by_mouse
        self.chord_origin = tile
        self.chord_moved = False
        self.refresh_highlight()

    def chord_end(self, reveal: bool):
        if not self.chord_held:
            return
        origin, moved = self.chord_origin, self.chord_moved
        self.chord_held = False
        self.chord_origin = None
        self.chord_moved = False
        self.refresh_highlight()
        if reveal and origin is not None and not moved:
            self.after_reveal(self.board.chord(*origin), origin)

    def on_key_down(self, e):
        if self.current_dialog or self.rebinding:
            return
        key = normalize_key(e.key)
        if key and key == self.binds["chord"]:
            self.chord_begin(self.hover, by_mouse=False)

    def on_key_up(self, e):
        if (
            self.chord_held
            and not self.chord_by_mouse
            and normalize_key(e.key) == self.binds["chord"]
        ):
            self.chord_end(True)

    def on_middle_down(self, e):
        if self.binds["chord"] == CHORD_MOUSE and not self.current_dialog:
            self.chord_begin(self.tile_at(e.local_position), by_mouse=True)

    def on_middle_up(self, e):
        if self.chord_held and self.chord_by_mouse:
            self.chord_end(True)

    def on_middle_cancel(self, e):
        # Flutter cancels a held click once the pointer moves away: no reveal
        if self.chord_held and self.chord_by_mouse:
            self.chord_end(False)

    # ---------- highlight (chord and easy mode) ----------

    def hidden_around(self, r: int, c: int) -> set[tuple[int, int]]:
        board = self.board
        return {
            (nr, nc)
            for nr, nc in board.neighbors(r, c)
            if not board.grid[nr][nc].is_revealed
        }

    def desired_highlight(self) -> set[tuple[int, int]]:
        board = self.board
        if board.game_over:
            return set()
        if self.chord_held:
            tile = self.chord_origin if self.chord_by_mouse else self.hover
            if tile is not None:
                cell = board.grid[tile[0]][tile[1]]
                if cell.is_revealed and cell.neighbor_count:
                    return self.hidden_around(*tile)
        if self.easy_mode and self.hover is not None:
            return self.hidden_around(*self.hover)
        return set()

    def refresh_highlight(self):
        self.set_highlight(self.desired_highlight())

    def set_highlight(self, new: set[tuple[int, int]]):
        """Highlight exactly these tiles, redrawing only the ones that changed."""
        old = self.highlight
        if new == old:
            return
        self.highlight = new
        for r, c in old ^ new:
            self.style_cell(r, c)
            self.cell_boxes[r][c].update()

    def finish_game(self):
        self.stop_timer()
        if self.start_time:
            self.elapsed = time.perf_counter() - self.start_time
        self.set_text(self.timer_text, self.format_time(self.elapsed))

        if self.board.won:
            key = self.best_key()
            if key in self.scores:  # Easy / Medium / Hard are saved to disk
                self.rank = storage.add_score(self.scores[key], self.elapsed)
                self.new_best = self.rank == 0
                if self.rank is not None:
                    self.save_state()
            else:  # custom boards only keep the best time for this session
                best = self.best.get(key)
                self.new_best = best is None or self.elapsed < best
                if self.new_best:
                    self.best[key] = self.elapsed

    # ------------------------------------------------------------------
    # Timer
    # ------------------------------------------------------------------

    @staticmethod
    def format_time(seconds: float) -> str:
        total_ms = int(seconds * 1000)
        minutes, rest = divmod(total_ms, 60_000)
        secs, ms = divmod(rest, 1000)
        if minutes:
            return f"{minutes}:{secs:02d}.{ms:03d}"
        return f"{secs}.{ms:03d}"

    def start_timer(self):
        self.timer_token += 1
        self.start_time = time.perf_counter()
        self.page.run_task(self.tick, self.timer_token)

    def stop_timer(self):
        self.timer_token += 1

    async def tick(self, token: int):
        while token == self.timer_token:
            self.elapsed = time.perf_counter() - self.start_time
            self.timer_text.value = self.format_time(self.elapsed)
            self.timer_text.update()
            await asyncio.sleep(0.03)

    # ==================================================================
    # Drawing & animations
    # ==================================================================

    def style_cell(self, r: int, c: int):
        board = self.board
        cell = board.grid[r][c]
        box = self.cell_boxes[r][c]
        label = box.content
        lost = board.game_over and not board.won

        if cell.is_revealed:
            if cell.is_mine:
                box.bgcolor = ft.Colors.ERROR
                label.value = "💣"
            else:
                box.bgcolor = ft.Colors.SURFACE_CONTAINER_LOW
                label.value = str(cell.neighbor_count) if cell.neighbor_count else ""
                label.color = self.number_colors.get(cell.neighbor_count)
        elif cell.is_flagged:
            if lost and not cell.is_mine:
                box.bgcolor = ft.Colors.ERROR_CONTAINER
                label.value = "❌"
            else:
                box.bgcolor = ft.Colors.TERTIARY_CONTAINER
                label.value = "🚩"
        elif lost and cell.is_mine:
            box.bgcolor = ft.Colors.ERROR_CONTAINER
            label.value = "💣"
        elif board.won and cell.is_mine:
            box.bgcolor = ft.Colors.TERTIARY_CONTAINER
            label.value = "🚩"
        else:
            box.bgcolor = self.hidden_color
            label.value = ""

        if (r, c) in self.highlight and not cell.is_revealed:
            box.border = self.highlight_border
            if not cell.is_flagged:
                box.bgcolor = self.highlight_fill
        else:
            box.border = None

        # the tile under the cursor gets a light veil
        hovered = (r, c) == self.hover and not cell.is_revealed and not board.game_over
        box.foreground_decoration = HOVER_TINT if hovered else None

    def restyle_all(self):
        """Repaint every tile (used when the theme or accent changes)."""
        for r, row in enumerate(self.cell_boxes):
            for c in range(len(row)):
                self.style_cell(r, c)

    def update_hud(self):
        board = self.board
        remaining = 0 if board.won else board.mines - board.flags_used
        self.set_text(self.mines_text, str(remaining))

        if board.won:
            icon = ft.Icons.EMOJI_EVENTS
        elif board.game_over:
            icon = ft.Icons.SENTIMENT_VERY_DISSATISFIED
        else:
            icon = ft.Icons.SENTIMENT_SATISFIED_ALT
        if icon != self.face_icon.icon:
            self.face_icon.icon = icon
            self.face_icon.update()
            if self.animations:
                self.page.run_task(self.pop, self.face, 1.2)

        if board.won:
            text = f"Cleared in {self.format_time(self.elapsed)}"
            best = self.best_time()
            if self.new_best:
                text += " · 🏆 New best!"
            else:
                if self.rank is not None:
                    text += f" · #{self.rank + 1} highscore"
                if best is not None:
                    text += f" · best {self.format_time(best)}"
            hint = f"{text} — press {self.key('restart')} to play again"
        elif board.game_over:
            hint = f"💥 Boom! Press {self.key('restart')} to try again"
        else:
            hint = self.default_hint()
            if board.fair and board.solvable is False:
                hint = "Too many mines for a guess-free board: a guess may be needed"
        self.set_text(self.hint_text, hint)

    def update_pills(self):
        for name, pill in self.pills.items():
            selected = name == self.difficulty
            bg = ft.Colors.PRIMARY if selected else ft.Colors.SURFACE_CONTAINER_HIGHEST
            if pill.bgcolor == bg:
                continue
            fg = ft.Colors.ON_PRIMARY if selected else ft.Colors.ON_SURFACE
            pill.bgcolor = bg
            icon, label = self.pill_parts[name]
            icon.color = fg
            label.color = fg
            pill.update()

    async def pop(self, control: ft.Control, big: float):
        """Quick 'pop' for single controls: scale up, then back."""
        control.scale = big
        control.update()
        await asyncio.sleep(0.03)
        control.scale = 1.0
        control.update()

    async def settle(self, box: ft.Container, game_id: int):
        await asyncio.sleep(0.025)
        if game_id == self.game_id:
            box.scale = 1.0
            box.update()

    async def animate_cells(self, cells, origin, game_id: int, win: bool):
        """Reveal cells as a quick ripple spreading from the clicked cell."""
        boxes = self.cell_boxes

        if not self.animations:
            for r, c in cells:
                self.style_cell(r, c)
                box = boxes[r][c]
                box.scale = 1.0
                box.update()
        else:
            r0, c0 = origin
            if len(cells) > 1:
                cells = sorted(
                    cells, key=lambda p: (p[0] - r0) ** 2 + (p[1] - c0) ** 2
                )
            per_batch = max(1, -(-len(cells) // RIPPLE_STEPS))  # ceil division
            pop = len(cells) <= POP_LIMIT  # big floods: colour only, half the updates
            prev = []
            for i in range(0, len(cells), per_batch):
                if game_id != self.game_id:
                    return
                batch = cells[i : i + per_batch]
                for r, c in batch:
                    self.style_cell(r, c)
                    box = boxes[r][c]
                    box.scale = POP_SCALE if pop else 1.0
                    box.update()
                if pop:
                    for r, c in prev:
                        box = boxes[r][c]
                        box.scale = 1.0
                        box.update()
                    prev = batch
                await asyncio.sleep(0.008)

            if pop:
                await asyncio.sleep(0.025)
                if game_id != self.game_id:
                    return
                for r, c in prev:
                    box = boxes[r][c]
                    box.scale = 1.0
                    box.update()

        if win and self.animations and game_id == self.game_id:
            await self.win_wave(game_id)

    async def win_wave(self, game_id: int):
        rows_ui = self.grid.controls
        for i in range(len(rows_ui) + 1):
            if game_id != self.game_id:
                return
            if i < len(rows_ui):
                for box in self.cell_boxes[i]:
                    box.scale = 1.1
                rows_ui[i].update()
            if i > 0:
                for box in self.cell_boxes[i - 1]:
                    box.scale = 1.0
                rows_ui[i - 1].update()
            await asyncio.sleep(0.0125)

def main(page: ft.Page):
    MinesweeperApp(page)


ft.run(main)