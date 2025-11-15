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
