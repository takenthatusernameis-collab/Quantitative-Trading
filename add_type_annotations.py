#!/usr/bin/env python3
"""Script to add type annotations to test_cli.py functions."""

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
        match = re.match(r'^(\s+)def\s+(\w+)\s*\(([^)]*)\):\s*$', line)
        if match:
            indent, func_name, params = match.groups()

            # Check if already has return annotation
            if '->' not in line:
                # Determine return type
                # Test functions typically return None
                # Helper functions may return other types

                # Check if it's a test function or a helper
                is_test = func_name.startswith('test_')
                is_helper = func_name.startswith('_')
                is_special = func_name in ('side_effect', '_raise_import_error', '_raise_os_error',
                                             '_raise_value_error', 'spy', 'mock_create_strategy',
                                             '__init__', 'generate_signals', 'get_parameters',
                                             'summary', 'segments', '__slots__')

                # Check next few lines for docstring to infer return type
                next_lines = '\n'.join(lines[i+1:i+5])

                # For test methods and most helper functions, return None
                # For functions with explicit return in body, we'd need more analysis
                # but for test files, almost all return None
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

                # For parametrized test functions, the first param might be self or a parameter
                # We'll add -> None for all test functions
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
        r'\bself\b': 'self',
        r'\bcapsys\b': 'capsys: CaptureFixture[Any]',
        r'\btmp_path\b': 'tmp_path: Path',
        r'\bmonkeypatch\b': 'monkeypatch: MonkeyPatch',
        r'\bmock_run_backtest\b': 'mock_run_backtest: MagicMock',
        r'\bmock_run\b': 'mock_run: MagicMock',
        r'\bmock_list_strategies\b': 'mock_list_strategies: MagicMock',
        r'\bmock_list_providers\b': 'mock_list_providers: MagicMock',
        r'\bmock_init_config\b': 'mock_init_config: MagicMock',
        r'\bmock_validate_config\b': 'mock_validate_config: MagicMock',
        r'\bmock_run_combined\b': 'mock_run_combined: MagicMock',
        r'\bmock_run_walk_forward\b': 'mock_run_walk_forward: MagicMock',
        r'\bmock_run_optimization\b': 'mock_run_optimization: MagicMock',
        r'\bmock_wf\b': 'mock_wf: MagicMock',
        r'\bmock_opt\b': 'mock_opt: MagicMock',
        r'\binterval\b': 'interval: str',
        r'\bfilename\b': 'filename: str',
        r'\bcontent\b': 'content: str',
        r'\barguments\b': 'arguments: list[str]',
        r'\boutput\b': 'output: str',
        r'\boverrides\b': 'overrides: Any',
        r'\bkwargs\b': 'kwargs: Any',
        r'\bargs\b': 'args: Any',
        r'\bmock_create_strategy\b': 'mock_create_strategy: Any',
        r'\bmock_parse\b': 'mock_parse: MagicMock',
    }

    # We need to be more careful - only add annotations to parameters that don't already have them
    lines = content.split('\n')
    new_lines = []

    for line in lines:
        # Check if this is a function definition with parameters but no type annotations on some params
        match = re.match(r'^(\s+)def\s+\w+\s*\(([^)]*)\)\s*->', line)
        if match:
            indent, params = match.groups()
            if params.strip():
                # Split parameters
                param_list = [p.strip() for p in params.split(',')]
                new_params = []
                for param in param_list:
                    # Skip if already has type annotation
                    if ':' in param and not param.startswith('**'):
                        new_params.append(param)
                        continue
                    # Skip *args, **kwargs
                    if param.startswith('*') or param.startswith('**'):
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
                new_line = f"{indent}def {match.group(0).split('def ')[1].split('(')[0]}({', '.join(new_params)})"
                # But we need to preserve the rest of the line...
                # Actually let's just reconstruct
                rest = line[line.index(')')+1:]
                new_line = f"{indent}def {match.group(0).split('def ')[1].split('(')[0]}({', '.join(new_params)}){rest}"
                new_lines.append(new_line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    return '\n'.join(new_lines)


def main():
    file_path = '/home/runner/work/Quantitative-Trading/Quantitative-Trading/tests/test_cli.py'

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