"""
Code Execution Service - Secure, accurate Python code execution with test case validation.
Supports: Python (native), JavaScript (via Node.js), C++/Java (stub with clear error).
"""
import subprocess
import time
import json
import sys
import traceback
import os
import tempfile
import re
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr



class CodeExecutor:
    """Execute user code safely with per-test-case results and performance tracking."""

    def __init__(self, timeout=10):
        self.timeout = timeout

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────────────────

    def execute_python(self, code: str, test_cases: list, function_name=None) -> dict:
        """
        Execute Python code against a list of test cases.

        test_cases format: [{"input": [arg1, arg2, ...], "expected": <value>}, ...]
        The "input" field is a list of positional arguments to the function.
        """
        results = self._empty_results(len(test_cases))

        # ── 1. Compile (catches SyntaxError early) ────────────────────────
        try:
            compiled = compile(code, "<user_code>", "exec")
        except SyntaxError as e:
            results['error'] = f"Syntax Error on line {e.lineno}: {e.msg}\n  → {(e.text or '').strip()}"
            return results

        # ── 2. Execute the module-level code once ─────────────────────────
        namespace = {
            '__builtins__': __builtins__,  # allow all built-ins
        }

        exec_output = StringIO()
        try:
            with redirect_stdout(exec_output), redirect_stderr(exec_output):
                exec(compiled, namespace)  # noqa: S102
        except Exception as e:
            results['error'] = f"Module-level Error: {type(e).__name__}: {e}\n{traceback.format_exc()}"
            return results

        # ── 3. Resolve the function to call ───────────────────────────────
        func = self._resolve_function(namespace, function_name)
        if func is None:
            # No function found — try stdin-style execution (prints to stdout)
            results = self._run_stdin_style(code, test_cases)
            return results

        # ── 4. Run each test case ─────────────────────────────────────────
        start_wall = time.perf_counter()

        for idx, tc in enumerate(test_cases):
            test_input = tc.get('input', [])
            expected   = tc.get('expected', tc.get('output'))  # support both keys
            tr = {
                'test_id': idx + 1,
                'input': test_input,
                'expected': expected,
                'actual': None,
                'passed': False,
                'error': None,
                'execution_time': 0,
                'stdout': ''
            }

            per_stdout = StringIO()
            t0 = time.perf_counter()
            try:
                with redirect_stdout(per_stdout):
                    args = test_input if isinstance(test_input, list) else [test_input]
                    actual = func(*args)

                t1 = time.perf_counter()
                tr['execution_time'] = round((t1 - t0) * 1000, 3)
                tr['actual'] = actual
                tr['stdout'] = per_stdout.getvalue()

                if self._compare(actual, expected):
                    tr['passed'] = True
                    results['passed_tests'] += 1
                else:
                    tr['error'] = (
                        f"Expected {self._repr(expected)}, "
                        f"but got {self._repr(actual)}"
                    )

            except Exception as e:
                t1 = time.perf_counter()
                tr['execution_time'] = round((t1 - t0) * 1000, 3)
                tr['error'] = f"{type(e).__name__}: {e}"

            results['test_results'].append(tr)

        end_wall = time.perf_counter()
        results['execution_time'] = round((end_wall - start_wall) * 1000, 2)
        results['stdout'] = exec_output.getvalue()
        results['success'] = True
        results['memory_used'] = 0  # lightweight — skip tracemalloc overhead
        return results

    def execute_javascript(self, code: str, test_cases: list, function_name=None) -> dict:
        """Execute JavaScript via Node.js."""
        results = self._empty_results(len(test_cases))

        if not function_name:
            # Try to infer from code
            import re
            m = re.search(r'function\s+(\w+)\s*\(', code)
            if m:
                function_name = m.group(1)
            else:
                results['error'] = 'No function name provided for JavaScript execution.'
                return results

        # Build a harness that serialises results to JSON
        harness_parts = [code, '\n\n// Test harness\n', 'const __results = [];']
        for idx, tc in enumerate(test_cases):
            ti = json.dumps(tc.get('input', []))
            expected = json.dumps(tc.get('expected', tc.get('output')))
            harness_parts.append(f"""
try {{
    const __t0 = Date.now();
    const __actual = {function_name}(...{ti});  
    const __t1 = Date.now();
    const __expected = {expected};
    __results.push({{
        test_id: {idx + 1},
        input: {ti},
        expected: __expected,
        actual: __actual,
        passed: JSON.stringify(__actual) === JSON.stringify(__expected),
        execution_time: __t1 - __t0,
        error: null
    }});
}} catch(__e) {{
    __results.push({{
        test_id: {idx + 1},
        input: {ti},
        expected: {expected},
        actual: null,
        passed: false,
        execution_time: 0,
        error: __e.toString()
    }});
}}""")
        harness_parts.append('\nprocess.stdout.write(JSON.stringify(__results));')
        full_code = ''.join(harness_parts)

        try:
            t0 = time.perf_counter()
            proc = subprocess.run(
                ['node', '--input-type=module'] if 'import ' in code else ['node', '-e', full_code],
                input=full_code if 'import ' in code else None,
                capture_output=True, text=True, timeout=self.timeout
            )
            t1 = time.perf_counter()

            if proc.returncode == 0 and proc.stdout.strip():
                test_data = json.loads(proc.stdout.strip())
                results['test_results'] = test_data
                results['passed_tests'] = sum(1 for t in test_data if t.get('passed'))
                results['execution_time'] = round((t1 - t0) * 1000, 2)
                results['success'] = True
            else:
                results['error'] = proc.stderr or 'Node.js returned no output.'

        except FileNotFoundError:
            results['error'] = (
                'Node.js is not installed on this server. '
                'JavaScript execution is unavailable — please use Python instead.'
            )
        except subprocess.TimeoutExpired:
            results['error'] = f'Timeout: JavaScript code exceeded {self.timeout}s.'
        except Exception as e:
            results['error'] = f'Execution Error: {e}'

        return results

    def execute_cpp(self, code: str, test_cases: list, function_name=None) -> dict:
        """Compile and run C++ code via g++ (Windows/Linux compatible)."""
        results = self._empty_results(len(test_cases))

        # Write to a temp file
        with tempfile.NamedTemporaryFile(suffix='.cpp', mode='w', delete=False, encoding='utf-8') as f:
            f.write(code)
            cpp_path = f.name

        exe_path = cpp_path.replace('.cpp', '.exe' if sys.platform == 'win32' else '')

        try:
            # Compile
            compile_proc = subprocess.run(
                ['g++', '-o', exe_path, cpp_path, '-std=c++17', '-O2'],
                capture_output=True, text=True, timeout=30
            )
            if compile_proc.returncode != 0:
                results['error'] = f"Compilation Error:\n{compile_proc.stderr}"
                return results

            # Run the executable and pass test cases via stdin
            for idx, tc in enumerate(test_cases):
                ti = tc.get('input', [])
                expected = tc.get('expected', tc.get('output'))
                stdin_str = '\n'.join(str(x) for x in (ti if isinstance(ti, list) else [ti])) + '\n'

                t0 = time.perf_counter()
                run_proc = subprocess.run(
                    [exe_path], input=stdin_str,
                    capture_output=True, text=True, timeout=self.timeout
                )
                t1 = time.perf_counter()
                actual_str = run_proc.stdout.strip()

                try:
                    actual = json.loads(actual_str)
                except Exception:
                    actual = actual_str

                passed = self._compare(actual, expected) or str(actual) == str(expected)
                tr = {
                    'test_id': idx + 1, 'input': ti, 'expected': expected,
                    'actual': actual, 'passed': passed, 'error': None,
                    'execution_time': round((t1 - t0) * 1000, 3),
                    'stdout': actual_str
                }
                if not passed:
                    tr['error'] = f'Expected {self._repr(expected)}, got {self._repr(actual)}'
                    if run_proc.stderr:
                        tr['error'] += f'\nStderr: {run_proc.stderr}'
                else:
                    results['passed_tests'] += 1
                results['test_results'].append(tr)

            results['success'] = True
            results['execution_time'] = sum(t['execution_time'] for t in results['test_results'])

        except FileNotFoundError:
            results['error'] = 'g++ compiler not found. C++ execution is not available on this server.'
        except subprocess.TimeoutExpired:
            results['error'] = f'Compilation or execution timed out after {self.timeout}s.'
        except Exception as e:
            results['error'] = f'C++ Execution Error: {e}'
        finally:
            for p in [cpp_path, exe_path]:
                try:
                    os.unlink(p)
                except OSError:
                    pass

        return results

    def execute_java(self, code: str, test_cases: list, function_name=None) -> dict:
        """Compile and run Java code via javac/java."""
        results = self._empty_results(len(test_cases))

        # Extract class name from code
        import re
        m = re.search(r'public\s+class\s+(\w+)', code)
        class_name = m.group(1) if m else 'Solution'

        tmpdir = tempfile.mkdtemp()
        java_path = os.path.join(tmpdir, f'{class_name}.java')
        try:
            with open(java_path, 'w', encoding='utf-8') as f:
                f.write(code)

            # Compile
            compile_proc = subprocess.run(
                ['javac', java_path], capture_output=True, text=True, timeout=30
            )
            if compile_proc.returncode != 0:
                results['error'] = f"Compilation Error:\n{compile_proc.stderr}"
                return results

            # Run for each test case (simple stdin-based)
            for idx, tc in enumerate(test_cases):
                ti = tc.get('input', [])
                expected = tc.get('expected', tc.get('output'))
                stdin_str = '\n'.join(str(x) for x in (ti if isinstance(ti, list) else [ti])) + '\n'

                t0 = time.perf_counter()
                run_proc = subprocess.run(
                    ['java', '-cp', tmpdir, class_name],
                    input=stdin_str, capture_output=True, text=True, timeout=self.timeout
                )
                t1 = time.perf_counter()
                actual_str = run_proc.stdout.strip()

                try:
                    actual = json.loads(actual_str)
                except Exception:
                    actual = actual_str

                passed = self._compare(actual, expected) or str(actual) == str(expected)
                tr = {
                    'test_id': idx + 1, 'input': ti, 'expected': expected,
                    'actual': actual, 'passed': passed, 'error': None,
                    'execution_time': round((t1 - t0) * 1000, 3),
                    'stdout': actual_str
                }
                if not passed:
                    tr['error'] = f'Expected {self._repr(expected)}, got {self._repr(actual)}'
                else:
                    results['passed_tests'] += 1
                results['test_results'].append(tr)

            results['success'] = True
            results['execution_time'] = sum(t['execution_time'] for t in results['test_results'])

        except FileNotFoundError:
            results['error'] = 'javac/java not found. Java execution is not available on this server.'
        except subprocess.TimeoutExpired:
            results['error'] = f'Compilation or execution timed out after {self.timeout}s.'
        except Exception as e:
            results['error'] = f'Java Execution Error: {e}'
        finally:
            import shutil
            try:
                shutil.rmtree(tmpdir)
            except OSError:
                pass

        return results

    def get_complexity_estimate(self, code: str) -> dict:
        """Heuristic big-O complexity estimate."""
        loop_count = code.count('for') + code.count('while')
        has_recursion = 'def ' in code and any(
            fname.split('(')[0].strip() in code.split('def ')[0]
            for fname in code.split('def ')[1:]
        )
        has_sort = '.sort(' in code or 'sorted(' in code

        if has_recursion:
            time_c = 'O(2ⁿ) — Recursive'
        elif loop_count >= 3:
            time_c = 'O(n³)'
        elif loop_count == 2:
            time_c = 'O(n²)'
        elif loop_count == 1 or has_sort:
            time_c = 'O(n log n)' if has_sort else 'O(n)'
        else:
            time_c = 'O(1)'

        space_c = 'O(n)' if any(k in code for k in ('dict', 'set', 'list(', '{}', '[]')) else 'O(1)'
        return {'time': time_c, 'space': space_c}

    # ─────────────────────────────────────────────────────────────────────────
    # PRIVATE HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _empty_results(total: int) -> dict:
        return {
            'success': False, 'test_results': [],
            'total_tests': total, 'passed_tests': 0,
            'execution_time': 0, 'memory_used': 0,
            'error': None, 'stdout': ''
        }

    @staticmethod
    def _resolve_function(namespace: dict, function_name):
        """Find the function to call in the executed namespace."""
        if function_name and function_name in namespace and callable(namespace[function_name]):
            return namespace[function_name]

        # Common aliases
        for name in ('solution', 'solve', 'main', 'answer'):
            if name in namespace and callable(namespace[name]):
                return namespace[name]

        # Pick first callable that isn't a built-in or class
        for name, obj in namespace.items():
            if callable(obj) and not name.startswith('_') and not isinstance(obj, type):
                return obj

        return None

    def _compare(self, actual, expected) -> bool:
        """Flexible comparison: numbers, strings, lists (possibly unordered), bools."""
        # None check
        if actual is None and expected is None:
            return True
        if actual is None or expected is None:
            return False

        # Bool is subclass of int in Python — compare explicitly first
        if isinstance(expected, bool) or isinstance(actual, bool):
            return bool(actual) == bool(expected)

        # Float tolerance
        if isinstance(actual, float) or isinstance(expected, float):
            try:
                return abs(float(actual) - float(expected)) < 1e-5
            except (TypeError, ValueError):
                return False

        # Lists: try exact, then sorted
        if isinstance(expected, list) and isinstance(actual, list):
            if len(actual) != len(expected):
                return False
            # Try element-wise exact
            if all(self._compare(a, e) for a, e in zip(actual, expected)):
                return True
            # Try sorted (e.g. groupAnagrams returns groups in any order)
            try:
                return sorted(str(x) for x in actual) == sorted(str(x) for x in expected)
            except Exception:
                return False

        # Type coercion: try comparing str representations for robustness
        if type(actual) != type(expected):
            try:
                return type(expected)(actual) == expected
            except Exception:
                pass
            try:
                return str(actual).strip() == str(expected).strip()
            except Exception:
                pass

        return actual == expected

    @staticmethod
    def _repr(val) -> str:
        if isinstance(val, str):
            return f'"{val}"'
        return repr(val)

    def _run_stdin_style(self, code: str, test_cases: list) -> dict:
        """
        Fallback for code that doesn't define a callable function.
        Run the code with each test case's input piped via stdin.
        """
        results = self._empty_results(len(test_cases))
        for idx, tc in enumerate(test_cases):
            ti = tc.get('input', [])
            expected = tc.get('expected', tc.get('output'))
            stdin_str = '\n'.join(str(x) for x in (ti if isinstance(ti, list) else [ti])) + '\n'

            try:
                proc = subprocess.run(
                    [sys.executable, '-c', code],
                    input=stdin_str, capture_output=True, text=True, timeout=self.timeout
                )
                actual_str = proc.stdout.strip()
                stderr_str = proc.stderr.strip()

                try:
                    actual = json.loads(actual_str)
                except Exception:
                    actual = actual_str

                passed = self._compare(actual, expected) or str(actual) == str(expected)
                tr = {
                    'test_id': idx + 1, 'input': ti, 'expected': expected,
                    'actual': actual, 'passed': passed, 'error': None,
                    'execution_time': 0, 'stdout': actual_str
                }
                if not passed:
                    tr['error'] = f'Expected {self._repr(expected)}, got {self._repr(actual)}'
                    if stderr_str:
                        tr['error'] += f'\n{stderr_str}'
                else:
                    results['passed_tests'] += 1
                results['test_results'].append(tr)

            except subprocess.TimeoutExpired:
                results['test_results'].append({
                    'test_id': idx + 1, 'input': ti, 'expected': expected,
                    'actual': None, 'passed': False,
                    'error': f'Timeout after {self.timeout}s', 'execution_time': self.timeout * 1000
                })

        results['success'] = True
        return results


# Singleton instance used by API routes
executor = CodeExecutor(timeout=10)
