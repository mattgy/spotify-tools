#!/usr/bin/env python3
"""
Shared print utilities for consistent messaging across the project.
Extracted to prevent circular imports between spotify_utils and cache_utils.

Author: Matt Y
License: MIT
Version: 1.0.0
"""

import colorama
from colorama import Fore, Style

# Initialize colorama
colorama.init(autoreset=True)

def print_success(text):
    """Print a success message in green."""
    print(f"{Fore.GREEN}{text}")

def print_error(text):
    """Print an error message in red."""
    print(f"{Fore.RED}{text}")

def print_warning(text):
    """Print a warning message in yellow."""
    print(f"{Fore.YELLOW}{text}")

def print_info(text):
    """Print an info message in blue."""
    print(f"{Fore.BLUE}{text}")

def print_header(text):
    """Print a formatted header in cyan."""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}" + "="*50)
    print(f"{Fore.CYAN}{Style.BRIGHT}{text}")
    print(f"{Fore.CYAN}{Style.BRIGHT}" + "="*50)

# ============================================================================
# Enhanced Visual Styling Functions (Option 2: Minimalist with Icons & Color)
# ============================================================================

def print_box_header(text, icon="🎵", width=63):
    """
    Print a main header with double-line borders and icon.

    Example:
        ═══════════════════════════════════════════════════════════
           🎵  SPOTIFY TOOLS  v2.0
        ═══════════════════════════════════════════════════════════
    """
    border = "═" * width
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{border}")
    print(f"{Fore.CYAN}{Style.BRIGHT}   {icon}  {text}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{border}{Style.RESET_ALL}")

def print_section_header(text, icon="", color=Fore.YELLOW):
    """
    Print a section header with icon.

    Example:
        🎧  PLAYLIST MANAGEMENT
    """
    if icon:
        print(f"\n{color}{Style.BRIGHT}{icon}  {text.upper()}{Style.RESET_ALL}")
    else:
        print(f"\n{color}{Style.BRIGHT}{text.upper()}{Style.RESET_ALL}")

def print_menu_item(number, text, icon="", indent=True):
    """
    Print a formatted menu item.

    Example:
        1  Convert local playlists to Spotify playlists
    """
    indent_space = "    " if indent else ""
    # Only add space after icon if icon is not empty
    icon_str = f"{icon} " if icon else ""
    print(f"{indent_space}{Fore.WHITE}{number}  {icon_str}{text}{Style.RESET_ALL}")

def print_status(status_type, message):
    """
    Print a status message with appropriate icon and color.

    Args:
        status_type: 'success', 'error', 'warning', 'info'
        message: The message to display

    Example:
        ✓ Successfully authenticated with Spotify!
        ✗ Failed to connect to API
        ℹ Fetching your playlists...
        ⚠ Rate limit approaching
    """
    icons_and_colors = {
        'success': ('✓', Fore.GREEN),
        'error': ('✗', Fore.RED),
        'warning': ('⚠', Fore.YELLOW),
        'info': ('ℹ', Fore.BLUE)
    }

    icon, color = icons_and_colors.get(status_type, ('•', Fore.WHITE))
    print(f"{color}{icon} {message}{Style.RESET_ALL}")

def print_separator(char='─', width=60, color=Fore.CYAN):
    """
    Print a visual separator line.

    Example:
        ────────────────────────────────────────────────────────────
    """
    print(f"{color}{char * width}{Style.RESET_ALL}")

def print_table_row(columns, widths, colors=None, align='left'):
    """
    Print an aligned table row.

    Args:
        columns: List of column values
        widths: List of column widths
        colors: Optional list of colors for each column
        align: 'left', 'right', or 'center'

    Example:
        print_table_row(['Artist', 'Pop', 'Playlists'], [30, 5, 10])
    """
    if colors is None:
        colors = [Fore.WHITE] * len(columns)

    formatted_cols = []
    for col, width, color in zip(columns, widths, colors):
        col_str = str(col)
        if align == 'right':
            formatted = col_str.rjust(width)
        elif align == 'center':
            formatted = col_str.center(width)
        else:
            formatted = col_str.ljust(width)
        formatted_cols.append(f"{color}{formatted}{Style.RESET_ALL}")

    print("  ".join(formatted_cols))

def print_table_border(widths, style='top'):
    """
    Print a table border.

    Args:
        widths: List of column widths
        style: 'top', 'middle', 'bottom'

    Example:
        ┌─────────────────────────────────────┐
        ├─────────────────────────────────────┤
        └─────────────────────────────────────┘
    """
    chars = {
        'top': ('┌', '─', '┬', '┐'),
        'middle': ('├', '─', '┼', '┤'),
        'bottom': ('└', '─', '┴', '┘')
    }

    left, horiz, join, right = chars.get(style, chars['top'])

    segments = [horiz * (w + 2) for w in widths]
    border = left + join.join(segments) + right
    print(f"{Fore.CYAN}{border}{Style.RESET_ALL}")

def print_progress_status(message, icon="🔄"):
    """
    Print a progress/processing status message.

    Example:
        🔄 Processing playlists...
    """
    print(f"{Fore.CYAN}{icon} {message}{Style.RESET_ALL}")
