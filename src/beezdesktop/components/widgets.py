"""
Custom Widget Components

Provides custom widgets for the application:
- SelectableLabel: A label whose text can be selected and copied
- SelectableText: Multi-line selectable text
- CopyableLabel: Label with a copy button
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW


class SelectableLabel(toga.Box):
    """
    A label-like widget whose text content can be selected with the mouse.
    
    Uses a readonly TextInput internally to enable text selection.
    Styled to look like a regular label.
    
    Args:
        text: The text to display
        style: Pack style to apply
        font_size: Font size (default 12)
        color: Text color (default #333333)
    """
    
    def __init__(
        self,
        text: str = "",
        style: Pack = None,
        font_size: int = 12,
        color: str = "#333333",
        **kwargs
    ):
        # Merge provided style with defaults
        base_style = Pack(
            direction=ROW,
            padding=0,
        )
        if style:
            # Apply any additional style properties
            for attr in ['flex', 'width', 'height', 'padding', 'background_color']:
                if hasattr(style, attr):
                    val = getattr(style, attr)
                    if val is not None:
                        setattr(base_style, attr, val)
        
        super().__init__(style=base_style)
        
        # Create the readonly text input that looks like a label
        self._text_input = toga.TextInput(
            value=text,
            readonly=True,
            style=Pack(
                flex=1,
                font_size=font_size,
                color=color,
                background_color="transparent",
                padding=0,
            )
        )
        self.add(self._text_input)
    
    @property
    def text(self) -> str:
        """Get the current text."""
        return self._text_input.value
    
    @text.setter
    def text(self, value: str):
        """Set the text content."""
        self._text_input.value = value


class SelectableText(toga.Box):
    """
    A multi-line text widget whose content can be selected with the mouse.
    
    Uses a readonly MultilineTextInput internally.
    
    Args:
        text: The text to display
        style: Pack style to apply
        height: Height of the text area (default 100)
        font_size: Font size (default 11)
        color: Text color (default #333333)
    """
    
    def __init__(
        self,
        text: str = "",
        style: Pack = None,
        height: int = 100,
        font_size: int = 11,
        color: str = "#333333",
        **kwargs
    ):
        base_style = Pack(
            direction=COLUMN,
            padding=0,
        )
        if style:
            for attr in ['flex', 'width', 'padding', 'background_color']:
                if hasattr(style, attr):
                    val = getattr(style, attr)
                    if val is not None:
                        setattr(base_style, attr, val)
        
        super().__init__(style=base_style)
        
        self._text_area = toga.MultilineTextInput(
            value=text,
            readonly=True,
            style=Pack(
                flex=1,
                height=height,
                font_size=font_size,
                color=color,
                padding=0,
            )
        )
        self.add(self._text_area)
    
    @property
    def text(self) -> str:
        """Get the current text."""
        return self._text_area.value
    
    @text.setter
    def text(self, value: str):
        """Set the text content."""
        self._text_area.value = value


class CopyableLabel(toga.Box):
    """
    A label with a copy button next to it.
    
    Displays text with a small copy button that copies the text to clipboard.
    
    Args:
        text: The text to display
        style: Pack style to apply
        font_size: Font size (default 12)
        color: Text color (default #333333)
        show_copy_button: Whether to show copy button (default True)
    """
    
    def __init__(
        self,
        text: str = "",
        style: Pack = None,
        font_size: int = 12,
        color: str = "#333333",
        show_copy_button: bool = True,
        on_copy=None,
        **kwargs
    ):
        base_style = Pack(
            direction=ROW,
            padding=0,
            alignment="center",
        )
        if style:
            for attr in ['flex', 'width', 'padding', 'background_color']:
                if hasattr(style, attr):
                    val = getattr(style, attr)
                    if val is not None:
                        setattr(base_style, attr, val)
        
        super().__init__(style=base_style)
        
        self._on_copy = on_copy
        
        # Selectable text input
        self._text_input = toga.TextInput(
            value=text,
            readonly=True,
            style=Pack(
                flex=1,
                font_size=font_size,
                color=color,
                background_color="transparent",
                padding=(0, 5, 0, 0),
            )
        )
        self.add(self._text_input)
        
        # Copy button
        if show_copy_button:
            self._copy_btn = toga.Button(
                "📋",
                on_press=self._do_copy,
                style=Pack(
                    width=30,
                    height=24,
                    font_size=10,
                    padding=0,
                )
            )
            self.add(self._copy_btn)
    
    @property
    def text(self) -> str:
        """Get the current text."""
        return self._text_input.value
    
    @text.setter
    def text(self, value: str):
        """Set the text content."""
        self._text_input.value = value
    
    async def _do_copy(self, widget):
        """Copy text to clipboard."""
        try:
            # Try to use the app's clipboard
            if hasattr(self, 'app') and self.app:
                self.app.clipboard = self._text_input.value
            
            # Call custom callback if provided
            if self._on_copy:
                self._on_copy(self._text_input.value)
            
            # Change button text temporarily to indicate success
            if hasattr(self, '_copy_btn'):
                self._copy_btn.text = "✓"
                await asyncio.sleep(1)
                self._copy_btn.text = "📋"
        except Exception as e:
            print(f"Copy failed: {e}", flush=True)


class InfoRow(toga.Box):
    """
    A row with a label and selectable value.
    
    Commonly used for displaying key-value pairs where the value
    should be selectable/copyable.
    
    Args:
        label: The label text
        value: The value text (selectable)
        label_width: Width of the label column (default 100)
        style: Pack style to apply
    """
    
    def __init__(
        self,
        label: str = "",
        value: str = "",
        label_width: int = 100,
        style: Pack = None,
        **kwargs
    ):
        base_style = Pack(
            direction=ROW,
            padding=3,
            alignment="center",
        )
        if style:
            for attr in ['flex', 'padding', 'background_color']:
                if hasattr(style, attr):
                    val = getattr(style, attr)
                    if val is not None:
                        setattr(base_style, attr, val)
        
        super().__init__(style=base_style)
        
        # Label (non-selectable, just for the key)
        self._label = toga.Label(
            label,
            style=Pack(
                width=label_width,
                font_size=11,
                color="#666666",
                padding=(0, 10, 0, 0),
            )
        )
        self.add(self._label)
        
        # Selectable value
        self._value_input = toga.TextInput(
            value=value,
            readonly=True,
            style=Pack(
                flex=1,
                font_size=11,
                color="#333333",
                background_color="transparent",
            )
        )
        self.add(self._value_input)
    
    @property
    def label(self) -> str:
        """Get the label text."""
        return self._label.text
    
    @label.setter
    def label(self, value: str):
        """Set the label text."""
        self._label.text = value
    
    @property
    def value(self) -> str:
        """Get the value text."""
        return self._value_input.value
    
    @value.setter
    def value(self, val: str):
        """Set the value text."""
        self._value_input.value = val


# Import asyncio for clipboard feedback
import asyncio
