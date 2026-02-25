"""
Beez Desktop Design System

Centralized theme providing consistent colors, typography, spacing,
and reusable UI component builders for the entire application.
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW


# =============================================================================
# LAYOUT CONSTANTS
# =============================================================================

SIDEBAR_WIDTH = 200


# =============================================================================
# COLOR PALETTE
# =============================================================================

class Colors:
    # Brand
    PRIMARY = "#1565c0"
    PRIMARY_DARK = "#0d47a1"
    PRIMARY_LIGHT = "#42a5f5"
    ACCENT = "#f9a825"
    ACCENT_DARK = "#f57f17"

    # Sidebar
    SIDEBAR_BG = "#0f1629"
    SIDEBAR_BTN = "#182240"
    SIDEBAR_BTN_ACTIVE = "#1565c0"
    SIDEBAR_TEXT = "#c8d6e5"
    SIDEBAR_TEXT_ACTIVE = "#ffffff"

    # Backgrounds
    BG_PAGE = "#f4f6f9"
    BG_CARD = "#ffffff"
    BG_CARD_HOVER = "#f8f9fb"
    BG_HEADER = "#e8edf4"

    # Surfaces (status cards)
    SURFACE_INFO = "#e3f2fd"
    SURFACE_SUCCESS = "#e8f5e9"
    SURFACE_WARNING = "#fff8e1"
    SURFACE_DANGER = "#ffebee"

    # Text
    TEXT_PRIMARY = "#1a1a2e"
    TEXT_SECONDARY = "#546e7a"
    TEXT_MUTED = "#90a4ae"
    TEXT_ON_PRIMARY = "#ffffff"
    TEXT_ON_DARK = "#e0e6ed"

    # Status
    STATUS_ONLINE = "#43a047"
    STATUS_OFFLINE = "#e53935"
    STATUS_PENDING = "#fb8c00"

    # Borders / Dividers
    BORDER = "#e0e0e0"
    DIVIDER = "#eceff1"


# =============================================================================
# TYPOGRAPHY
# =============================================================================

class Font:
    SIZE_H1 = 22
    SIZE_H2 = 17
    SIZE_H3 = 14
    SIZE_BODY = 12
    SIZE_SMALL = 11
    SIZE_CAPTION = 10
    SIZE_BADGE = 9


# =============================================================================
# SPACING
# =============================================================================

class Spacing:
    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24
    XXL = 32

    CARD_PADDING = 14
    SECTION_GAP = 16
    PAGE_PADDING = 20


# =============================================================================
# NAVIGATION ICONS (Unicode)
# =============================================================================

NAV_ICONS = {
    "dashboard":    "\u25A3",
    "wallet":       "\u25C8",
    "files":        "\u25A4",
    "smart":        "\u2605",
    "knowledge":    "\u2606",
    "transactions": "\u21C4",
    "blockchain":   "\u26D3",
    "network":      "\u26C1",
    "settings":     "\u2699",
}


# =============================================================================
# REUSABLE COMPONENT BUILDERS
# =============================================================================

def scrollable_content() -> toga.ScrollContainer:
    """Create a ScrollContainer for the main content area of a view.

    Every view's ``build()`` should wrap its contents in this so that
    content that exceeds the window height can be scrolled.
    """
    sc = toga.ScrollContainer(
        horizontal=False,
        style=Pack(flex=1),
    )
    return sc


def page_header(title: str, subtitle: str = "") -> toga.Box:
    """Build a consistent page header with title and optional subtitle."""
    box = toga.Box(style=Pack(direction=COLUMN, padding=(0, 0, Spacing.SECTION_GAP, 0)))

    title_label = toga.Label(
        title,
        style=Pack(
            font_size=Font.SIZE_H1,
            font_weight="bold",
            color=Colors.TEXT_PRIMARY,
            padding=(0, 0, Spacing.XS, 0),
        ),
    )
    box.add(title_label)

    if subtitle:
        sub_label = toga.Label(
            subtitle,
            style=Pack(font_size=Font.SIZE_BODY, color=Colors.TEXT_SECONDARY),
        )
        box.add(sub_label)

    return box


def card(
    children: list = None,
    title: str = "",
    bg: str = Colors.BG_CARD,
    padding: int = Spacing.CARD_PADDING,
    direction=COLUMN,
    width: int = None,
    flex: int = None,
) -> toga.Box:
    """Build a card container with optional title."""
    style_kwargs = dict(direction=direction, padding=padding, background_color=bg)
    if width:
        style_kwargs["width"] = width
    if flex is not None:
        style_kwargs["flex"] = flex

    box = toga.Box(style=Pack(**style_kwargs))

    if title:
        header = toga.Label(
            title,
            style=Pack(
                font_size=Font.SIZE_H3,
                font_weight="bold",
                color=Colors.TEXT_PRIMARY,
                padding=(0, 0, Spacing.SM, 0),
            ),
        )
        box.add(header)

    if children:
        for child in children:
            box.add(child)

    return box


def stat_card(
    label: str,
    value: str,
    color: str = Colors.PRIMARY,
    bg: str = Colors.SURFACE_INFO,
) -> toga.Box:
    """Build a compact stat card that stretches with flex."""
    box = toga.Box(
        style=Pack(
            direction=COLUMN,
            padding=Spacing.CARD_PADDING,
            background_color=bg,
            flex=1,
        )
    )

    val_label = toga.Label(
        value,
        style=Pack(font_size=Font.SIZE_H2, font_weight="bold", color=color, padding=(0, 0, Spacing.XS, 0)),
    )
    box.add(val_label)

    name_label = toga.Label(
        label,
        style=Pack(font_size=Font.SIZE_SMALL, color=Colors.TEXT_SECONDARY),
    )
    box.add(name_label)

    return box


def status_badge(text: str, online: bool = True) -> toga.Box:
    """Build a colored status indicator row."""
    row = toga.Box(style=Pack(direction=ROW, padding=Spacing.XS, alignment="center"))

    dot_color = Colors.STATUS_ONLINE if online else Colors.STATUS_OFFLINE
    dot = toga.Label("\u25CF", style=Pack(color=dot_color, font_size=12, padding=(0, Spacing.SM, 0, 0)))
    row.add(dot)

    label = toga.Label(
        text,
        style=Pack(
            color=Colors.STATUS_ONLINE if online else Colors.STATUS_OFFLINE,
            font_weight="bold",
            font_size=Font.SIZE_BODY,
        ),
    )
    row.add(label)

    return row


def section_divider() -> toga.Box:
    """A horizontal divider between sections."""
    return toga.Box(
        style=Pack(
            height=1,
            padding=(Spacing.MD, 0),
            background_color=Colors.DIVIDER,
        )
    )


def info_row(label: str, value: str, label_width: int = 120) -> toga.Box:
    """Key-value row with label and selectable value."""
    row = toga.Box(style=Pack(direction=ROW, padding=Spacing.XS, alignment="center"))

    key = toga.Label(
        label,
        style=Pack(width=label_width, font_size=Font.SIZE_BODY, color=Colors.TEXT_SECONDARY),
    )
    row.add(key)

    val = toga.TextInput(
        value=value,
        readonly=True,
        style=Pack(flex=1, font_size=Font.SIZE_BODY, color=Colors.TEXT_PRIMARY, background_color="transparent"),
    )
    row.add(val)

    return row


def primary_button(text: str, handler, width: int = 160) -> toga.Button:
    """Styled primary action button."""
    return toga.Button(
        text,
        on_press=handler,
        style=Pack(
            width=width,
            padding=Spacing.SM,
            color=Colors.TEXT_ON_PRIMARY,
            background_color=Colors.PRIMARY,
            font_weight="bold",
        ),
    )


def secondary_button(text: str, handler, width: int = 140) -> toga.Button:
    """Styled secondary action button."""
    return toga.Button(
        text,
        on_press=handler,
        style=Pack(
            width=width,
            padding=Spacing.SM,
            color=Colors.TEXT_PRIMARY,
            background_color=Colors.BG_HEADER,
        ),
    )


def danger_button(text: str, handler, width: int = 140) -> toga.Button:
    """Styled danger/destructive action button."""
    return toga.Button(
        text,
        on_press=handler,
        style=Pack(
            width=width,
            padding=Spacing.SM,
            color=Colors.TEXT_ON_PRIMARY,
            background_color=Colors.STATUS_OFFLINE,
        ),
    )


def action_card(
    title: str,
    description: str,
    button_text: str,
    handler,
    icon: str = "",
) -> toga.Box:
    """Clickable action card with icon, description and button. Uses flex sizing."""
    box = toga.Box(
        style=Pack(
            direction=COLUMN,
            padding=Spacing.CARD_PADDING,
            flex=1,
            background_color=Colors.BG_CARD,
        )
    )

    if icon:
        icon_label = toga.Label(
            icon,
            style=Pack(font_size=Font.SIZE_H1, padding=(0, 0, Spacing.SM, 0)),
        )
        box.add(icon_label)

    title_label = toga.Label(
        title,
        style=Pack(font_size=Font.SIZE_H3, font_weight="bold", color=Colors.TEXT_PRIMARY, padding=(0, 0, Spacing.XS, 0)),
    )
    box.add(title_label)

    desc_label = toga.Label(
        description,
        style=Pack(font_size=Font.SIZE_SMALL, color=Colors.TEXT_SECONDARY, padding=(0, 0, Spacing.MD, 0)),
    )
    box.add(desc_label)

    btn = primary_button(button_text, handler, width=140)
    box.add(btn)

    return box


def spacer(height: int = Spacing.SECTION_GAP) -> toga.Box:
    """Vertical spacer."""
    return toga.Box(style=Pack(height=height))


# =============================================================================
# LOADING INDICATOR
# =============================================================================

class LoadingIndicator:
    """A simple loading indicator that can be shown/hidden.

    Works by adding/removing an inner content row from an outer wrapper box,
    which is reliable across all Toga backends (GTK, WinForms, Cocoa).

    Usage::

        loading = LoadingIndicator("Loading transactions...")
        parent.add(loading.box)
        loading.show()   # make visible, set message
        loading.hide()   # hide after data loads
    """

    def __init__(self, message: str = "Loading..."):
        self.box = toga.Box(style=Pack(direction=COLUMN))
        self._inner = toga.Box(
            style=Pack(
                direction=ROW,
                padding=Spacing.MD,
                alignment="center",
                background_color=Colors.SURFACE_INFO,
                height=40,
            )
        )
        self._spinner = toga.Label(
            "\u25F7",
            style=Pack(font_size=Font.SIZE_H3, color=Colors.PRIMARY, padding=(0, Spacing.SM, 0, 0)),
        )
        self._label = toga.Label(
            message,
            style=Pack(font_size=Font.SIZE_BODY, color=Colors.PRIMARY, font_weight="bold"),
        )
        self._inner.add(self._spinner)
        self._inner.add(self._label)
        self._visible = False

    def show(self, message: str = None):
        """Show the loading indicator with an optional new message."""
        if message:
            self._label.text = message
        if not self._visible:
            self.box.add(self._inner)
            self._visible = True

    def hide(self):
        """Hide the loading indicator."""
        if self._visible:
            try:
                self.box.remove(self._inner)
            except Exception:
                pass
            self._visible = False


# =============================================================================
# SEARCHABLE TABLE
# =============================================================================

class SearchableTable:
    """A table with built-in search/filter and pagination.

    Usage::

        st = SearchableTable(
            headings=["Name", "Value"],
            page_size=15,
            on_select=my_handler,
        )
        parent.add(st.box)
        st.set_data([("row1", "val1"), ("row2", "val2"), ...])
    """

    def __init__(
        self,
        headings: list,
        page_size: int = 15,
        on_select=None,
        search_placeholder: str = "Search...",
        table_height: int = None,
    ):
        self._headings = headings
        self._page_size = page_size
        self._on_select = on_select
        self._all_data: list = []
        self._filtered: list = []
        self._page = 0

        self.box = toga.Box(style=Pack(direction=COLUMN, flex=1))

        # Search row
        search_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, Spacing.SM, 0), alignment="center"))

        self._search_input = toga.TextInput(
            placeholder=search_placeholder,
            on_change=self._on_search_changed,
            style=Pack(flex=1, padding=(0, Spacing.SM, 0, 0)),
        )
        search_row.add(self._search_input)

        clear_btn = toga.Button(
            "Clear",
            on_press=self._on_clear_search,
            style=Pack(width=60, padding=Spacing.XS, background_color=Colors.BG_HEADER),
        )
        search_row.add(clear_btn)

        self.box.add(search_row)

        # Table
        table_style = Pack(flex=1)
        if table_height:
            table_style = Pack(height=table_height)

        self._table = toga.Table(
            headings=headings,
            data=[],
            style=table_style,
            on_select=self._handle_select,
        )
        self.box.add(self._table)

        # Pagination row
        self._pagination_row = toga.Box(style=Pack(direction=ROW, padding=(Spacing.SM, 0, 0, 0), alignment="center"))

        self._prev_btn = toga.Button(
            "\u2190 Prev",
            on_press=self._on_prev,
            style=Pack(width=80, padding=Spacing.XS, background_color=Colors.BG_HEADER),
        )
        self._pagination_row.add(self._prev_btn)

        self._page_label = toga.Label(
            "Page 1 / 1",
            style=Pack(flex=1, font_size=Font.SIZE_SMALL, color=Colors.TEXT_SECONDARY, padding=(0, Spacing.SM)),
        )
        self._pagination_row.add(self._page_label)

        self._count_label = toga.Label(
            "",
            style=Pack(font_size=Font.SIZE_SMALL, color=Colors.TEXT_MUTED, padding=(0, Spacing.SM, 0, 0)),
        )
        self._pagination_row.add(self._count_label)

        self._next_btn = toga.Button(
            "Next \u2192",
            on_press=self._on_next,
            style=Pack(width=80, padding=Spacing.XS, background_color=Colors.BG_HEADER),
        )
        self._pagination_row.add(self._next_btn)

        self.box.add(self._pagination_row)

    # -- public API --

    @property
    def table(self) -> toga.Table:
        return self._table

    def set_data(self, data: list):
        """Replace all table data. Each item should be a tuple matching headings."""
        self._all_data = list(data)
        self._apply_filter()

    def clear(self):
        self._all_data = []
        self._filtered = []
        self._page = 0
        self._table.data.clear()
        self._update_pagination()

    def append(self, row):
        self._all_data.append(row)
        self._apply_filter()

    # -- internals --

    def _apply_filter(self):
        query = self._search_input.value.strip().lower() if self._search_input.value else ""
        if query:
            self._filtered = [
                row for row in self._all_data
                if any(query in str(cell).lower() for cell in row)
            ]
        else:
            self._filtered = list(self._all_data)

        self._page = 0
        self._render_page()

    def _render_page(self):
        start = self._page * self._page_size
        end = start + self._page_size
        page_data = self._filtered[start:end]

        self._table.data.clear()
        for row in page_data:
            self._table.data.append(row)

        self._update_pagination()

    def _update_pagination(self):
        total = len(self._filtered)
        total_pages = max(1, (total + self._page_size - 1) // self._page_size)
        current = self._page + 1
        self._page_label.text = f"Page {current} / {total_pages}"
        self._count_label.text = f"{total} rows"
        self._prev_btn.enabled = self._page > 0
        self._next_btn.enabled = current < total_pages

    def _on_search_changed(self, widget):
        self._apply_filter()

    def _on_clear_search(self, widget):
        self._search_input.value = ""
        self._apply_filter()

    def _on_prev(self, widget):
        if self._page > 0:
            self._page -= 1
            self._render_page()

    def _on_next(self, widget):
        total_pages = max(1, (len(self._filtered) + self._page_size - 1) // self._page_size)
        if self._page + 1 < total_pages:
            self._page += 1
            self._render_page()

    def _handle_select(self, widget):
        if self._on_select:
            self._on_select(widget)
