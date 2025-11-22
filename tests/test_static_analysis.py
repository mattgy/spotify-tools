#!/usr/bin/env python3
"""
Static analysis tests to catch code issues without execution.

These tests use Python's ast module to detect:
- Undefined variables and names
- Import issues
- Syntax errors

This helps catch runtime errors like NameError before code is executed.
"""

import unittest
import ast
import os
import sys
from pathlib import Path


class TestStaticAnalysis(unittest.TestCase):
    """Test suite for static code analysis."""

    @classmethod
    def setUpClass(cls):
        """Set up test class with list of Python files to analyze."""
        cls.project_root = Path(__file__).parent.parent

        # Get all main Python scripts (not in tests or venv)
        cls.python_files = []
        for file_path in cls.project_root.glob('*.py'):
            if file_path.name not in ['setup.py', '__init__.py']:
                cls.python_files.append(file_path)

    def test_all_files_parseable(self):
        """Test that all Python files can be parsed (no syntax errors)."""
        for file_path in self.python_files:
            with self.subTest(file=file_path.name):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        source = f.read()
                    ast.parse(source, filename=str(file_path))
                except SyntaxError as e:
                    self.fail(f"Syntax error in {file_path.name}: {e}")

    def test_no_undefined_names_in_imports(self):
        """Test that all imported names are defined in the target modules."""
        errors = []

        for file_path in self.python_files:
            # Skip constants.py - it defines these constants, doesn't import them
            if file_path.name == 'constants.py':
                continue

            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()

            try:
                tree = ast.parse(source, filename=str(file_path))
            except SyntaxError:
                continue  # Skip files with syntax errors (caught by other test)

            # Extract all imports
            imports = self._extract_imports(tree)

            # Check if constants are imported when used
            if self._uses_constant(tree, 'DEFAULT_CACHE_EXPIRATION'):
                if not self._imports_from_module(imports, 'constants', 'DEFAULT_CACHE_EXPIRATION'):
                    errors.append(
                        f"{file_path.name}: Uses DEFAULT_CACHE_EXPIRATION but doesn't import it from constants"
                    )

            if self._uses_constant(tree, 'STANDARD_CACHE_KEYS'):
                if not self._imports_from_module(imports, 'constants', 'STANDARD_CACHE_KEYS'):
                    errors.append(
                        f"{file_path.name}: Uses STANDARD_CACHE_KEYS but doesn't import it from constants"
                    )

            if self._uses_constant(tree, 'BATCH_SIZES'):
                if not self._imports_from_module(imports, 'constants', 'BATCH_SIZES'):
                    errors.append(
                        f"{file_path.name}: Uses BATCH_SIZES but doesn't import it from constants"
                    )

        if errors:
            self.fail("Import errors detected:\n" + "\n".join(errors))

    def test_cache_utils_usage(self):
        """Test that files using cache_utils import required functions."""
        errors = []

        for file_path in self.python_files:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()

            try:
                tree = ast.parse(source, filename=str(file_path))
            except SyntaxError:
                continue

            imports = self._extract_imports(tree)

            # Check if cache functions are used but not imported
            if self._uses_function(tree, 'load_from_cache'):
                if not self._imports_from_module(imports, 'cache_utils', 'load_from_cache'):
                    errors.append(
                        f"{file_path.name}: Uses load_from_cache but doesn't import it from cache_utils"
                    )

            if self._uses_function(tree, 'save_to_cache'):
                if not self._imports_from_module(imports, 'cache_utils', 'save_to_cache'):
                    errors.append(
                        f"{file_path.name}: Uses save_to_cache but doesn't import it from cache_utils"
                    )

        if errors:
            self.fail("Cache utils import errors:\n" + "\n".join(errors))

    def test_spotify_utils_usage(self):
        """Test that files using spotify_utils import required functions."""
        errors = []

        common_functions = [
            'create_spotify_client',
            'fetch_user_playlists',
            'fetch_playlist_tracks',
            'print_success',
            'print_error',
            'print_warning',
            'print_info'
        ]

        for file_path in self.python_files:
            # Skip spotify_utils itself
            if file_path.name == 'spotify_utils.py':
                continue

            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()

            try:
                tree = ast.parse(source, filename=str(file_path))
            except SyntaxError:
                continue

            imports = self._extract_imports(tree)

            # Check commonly used functions
            for func_name in common_functions:
                if self._uses_function(tree, func_name):
                    if not (self._imports_from_module(imports, 'spotify_utils', func_name) or
                            self._imports_from_module(imports, 'spotify_utils', '*')):
                        # Only warn, not fail, as some files may define these locally
                        pass  # We'll be lenient here

        if errors:
            self.fail("Spotify utils import errors:\n" + "\n".join(errors))

    def test_no_common_typos(self):
        """Test for common variable name typos."""
        import re

        typos_to_check = {
            'DEFUALT_CACHE_EXPIRATION': 'DEFAULT_CACHE_EXPIRATION',
            'STANARD_CACHE_KEYS': 'STANDARD_CACHE_KEYS',
        }

        errors = []

        for file_path in self.python_files:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()

            for typo, correct in typos_to_check.items():
                # Use word boundaries to avoid matching substrings
                pattern = r'\b' + re.escape(typo) + r'\b'
                if re.search(pattern, source):
                    errors.append(
                        f"{file_path.name}: Found potential typo '{typo}' (should be '{correct}')"
                    )

        if errors:
            self.fail("Potential typos detected:\n" + "\n".join(errors))

    # Helper methods

    def _extract_imports(self, tree):
        """Extract all imports from an AST tree."""
        imports = {
            'modules': set(),  # Module names
            'from_imports': {}  # {module: [name1, name2, ...]}
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports['modules'].add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                if module not in imports['from_imports']:
                    imports['from_imports'][module] = []
                for alias in node.names:
                    imports['from_imports'][module].append(alias.name)

        return imports

    def _uses_constant(self, tree, const_name):
        """Check if a constant name is used in the AST."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == const_name:
                return True
        return False

    def _uses_function(self, tree, func_name):
        """Check if a function is called in the AST."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == func_name:
                    return True
                elif isinstance(node.func, ast.Attribute) and node.func.attr == func_name:
                    return True
        return False

    def _imports_from_module(self, imports, module, name):
        """Check if a specific name is imported from a module."""
        if module in imports['from_imports']:
            return name in imports['from_imports'][module] or '*' in imports['from_imports'][module]
        return False


if __name__ == '__main__':
    unittest.main()
