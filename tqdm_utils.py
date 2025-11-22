#!/usr/bin/env python3
"""
Utilities for consistent progress bar formatting across all Spotify Tools scripts.

This module provides functions to create, update, and close progress bars using tqdm.

Author: Matt Y
License: MIT
Version: 1.0.0
"""

from tqdm import tqdm

def create_progress_bar(total, desc=None, unit=None):
    """
    Create a consistently formatted progress bar.
    
    Args:
        total: Total number of items
        desc: Description for the progress bar
        unit: Unit name for the items being processed
        
    Returns:
        A tqdm progress bar instance
    """
    # Ensure unit is a string to avoid TypeError
    if unit is None:
        unit = "item"
    
    return tqdm(
        total=total,
        desc=desc,
        unit=str(unit),
        bar_format='{l_bar}{bar:30}{r_bar}{bar:-30b}',
        ncols=100
    )

def update_progress_bar(progress_bar, n=1):
    """
    Update a progress bar safely.
    
    Args:
        progress_bar: The tqdm progress bar to update
        n: Number of steps to increment
    """
    if progress_bar is not None:
        progress_bar.update(n)

def close_progress_bar(progress_bar):
    """
    Close a progress bar safely.

    Args:
        progress_bar: The tqdm progress bar to close
    """
    if progress_bar is not None:
        progress_bar.close()

# ============================================================================
# Enhanced Progress Bar Functions with Visual Styling
# ============================================================================

def create_styled_progress_bar(total, desc=None, unit=None, style='processing', icon=None):
    """
    Create a visually enhanced progress bar with icons and colors.

    Args:
        total: Total number of items
        desc: Description for the progress bar
        unit: Unit name for the items being processed
        style: 'processing', 'success', 'warning', 'error' (affects color)
        icon: Optional icon to prefix the description (e.g., '🔄', '✓')

    Returns:
        A tqdm progress bar instance with enhanced styling

    Example:
        🔄 Processing playlists: █████████░░░ 60% | 300/500 [01:23<00:55, 3.2 playlist/s]
    """
    # Ensure unit is a string
    if unit is None:
        unit = "item"

    # Add icon to description if provided
    if icon and desc:
        desc = f"{icon} {desc}"
    elif desc and not icon:
        # Add default icon based on style
        style_icons = {
            'processing': '🔄',
            'success': '✓',
            'warning': '⚠',
            'error': '✗'
        }
        icon = style_icons.get(style, '')
        if icon:
            desc = f"{icon} {desc}"

    # Enhanced bar format with better visuals
    # Using block characters for a more solid look: █▓▒░
    bar_format = '{l_bar}{bar:30}{r_bar}'

    # Color codes for different styles (ANSI color codes)
    # These work with tqdm's native color support
    color_codes = {
        'processing': 'cyan',
        'success': 'green',
        'warning': 'yellow',
        'error': 'red'
    }

    color = color_codes.get(style, 'cyan')

    return tqdm(
        total=total,
        desc=desc,
        unit=str(unit),
        bar_format=bar_format,
        ncols=100,
        colour=color,
        ascii=False  # Use Unicode characters for smoother bars
    )

def create_minimal_progress_bar(total, desc=None, unit=None):
    """
    Create a minimal progress bar without percentage (for cleaner output).

    Args:
        total: Total number of items
        desc: Description for the progress bar
        unit: Unit name for the items being processed

    Returns:
        A tqdm progress bar instance with minimal styling
    """
    if unit is None:
        unit = "item"

    return tqdm(
        total=total,
        desc=desc,
        unit=str(unit),
        bar_format='{desc}: {n_fmt}/{total_fmt} [{elapsed}<{remaining}]',
        ncols=80
    )
