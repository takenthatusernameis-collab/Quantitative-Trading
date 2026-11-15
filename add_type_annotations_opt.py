#!/usr/bin/env python3
"""Script to add type annotations to test_optimization.py functions."""

import re
import sys

def add_return_annotations(content: str) -> str:
    """Add return type annotations to functions that don't have them."""
    lines = content.split('\n')
    new_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Check if this is a function definition without return annotation
        # Pattern: def func_name(params): or def func_name(self, params):
        match = re.match(r'^(\s*)def\s+(\w+)\s*\(([^)]*)\):\s*$', line)
        if match:
            indent, func_name, params = match.groups()

            # Check if already has return annotation
            if '->' not in line:
                # Test functions and helpers return None
                return_type = "None"

                # Special cases: nested functions inside test methods
                # Check if we're inside a class method by looking at previous lines
                in_class = False
                for j in range(i-1, max(0, i-20), -1):
                    if re.match(r'^\s*class\s+\w+', lines[j]):
                        in_class = True
                        break
                    if lines[j].strip() and not lines[j].startswith(' ') and not lines[j].startswith('\t'):
                        break

                new_line = f"{indent}def {func_name}({params}) -> {return_type}:"
                new_lines.append(new_line)
                i += 1
                continue

        new_lines.append(line)
        i += 1

    return '\n'.join(new_lines)


def add_param_annotations(content: str) -> str:
    """Add parameter type annotations for common patterns."""
    # Common parameter patterns and their types
    param_patterns = {
        'self': 'self',
        'capsys': 'capsys: pytest.CaptureFixture[Any]',
        'tmp_path': 'tmp_path: pathlib.Path',
        'monkeypatch': 'monkeypatch: pytest.MonkeyPatch',
        'mock_run_backtest': 'mock_run_backtest: unittest.mock.MagicMock',
        'mock_run': 'mock_run: unittest.mock.MagicMock',
        'mock_list_strategies': 'mock_list_strategies: unittest.mock.MagicMock',
        'mock_list_providers': 'mock_list_providers: unittest.mock.MagicMock',
        'mock_init_config': 'mock_init_config: unittest.mock.MagicMock',
        'mock_validate_config': 'mock_validate_config: unittest.mock.MagicMock',
        'mock_run_combined': 'mock_run_combined: unittest.mock.MagicMock',
        'mock_run_walk_forward': 'mock_run_walk_forward: unittest.mock.MagicMock',
        'mock_run_optimization': 'mock_run_optimization: unittest.mock.MagicMock',
        'mock_wf': 'mock_wf: unittest.mock.MagicMock',
        'mock_opt': 'mock_opt: unittest.mock.MagicMock',
        'interval': 'interval: str',
        'filename': 'filename: str',
        'content': 'content: str',
        'arguments': 'arguments: list[str]',
        'output': 'output: str',
        'overrides': 'overrides: Any',
        'kwargs': 'kwargs: Any',
        'args': 'args: Any',
        'mock_create_strategy': 'mock_create_strategy: Any',
        'mock_parse': 'mock_parse: unittest.mock.MagicMock',
        'step': 'step: float',
        'train_size': 'train_size: float',
        'n_windows': 'n_windows: int',
        'anchored': 'anchored: bool',
    }

    lines = content.split('\n')
    new_lines = []

    for line in lines:
        # Check if this is a function definition with parameters and return annotation
        match = re.match(r'^(\s*)def\s+(\w+)\s*\(([^)]*)\)\s*->', line)
        if match:
            indent, func_name, params = match.groups()
            if params.strip():
                # Split parameters
                param_list = [p.strip() for p in params.split(',')]
                new_params = []
                for param in param_list:
                    # Skip if already has type annotation
                    if ':' in param and not param.strip().startswith('**'):
                        new_params.append(param)
                        continue
                    # Skip *args, **kwargs
                    if param.strip().startswith('*') or param.strip().startswith('**'):
                        new_params.append(param)
                        continue
                    # Check for known patterns
                    param_name = param.split('=')[0].strip()
                    if param_name in param_patterns:
                        # Replace with annotated version
                        if '=' in param:
                            default = param.split('=', 1)[1]
                            new_params.append(f"{param_patterns[param_name]} = {default}")
                        else:
                            new_params.append(param_patterns[param_name])
                    else:
                        new_params.append(param)
                # Reconstruct the line
                rest = line[line.index(')')+1:]
                new_line = f"{indent}def {func_name}({', '.join(new_params)}){rest}"
                new_lines.append(new_line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    return '\n'.join(new_lines)


def main():
    file_path = '/home/runner/work/Quantitative-Trading/Quantitative-Trading/tests/test_optimization.py'

    with open(file_path, 'r') as f:
        content = f.read()

    # First add return annotations
    content = add_return_annotations(content)

    # Then add parameter annotations
    content = add_param_annotations(content)

    with open(file_path, 'w') as f:
        f.write(content)

    print("Type annotations added!")


if __name__ == '__main__':
    main()