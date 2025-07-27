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
