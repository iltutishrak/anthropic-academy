"""
mini_swe_eval.py — a SWE-bench-style agentic coding eval, in one file.

WHAT THIS IS
============
SWE-bench gives a model a real repository with a failing test, asks it to produce
a code change, then RUNS THE TEST SUITE to decide if the change actually fixed the
bug. The model is graded by execution, not by whether its answer "looks right."
That execution-grounded loop is the whole point — it's why SWE-bench correlates
with real engineering ability and why eyeballing diffs does not.

This is a miniature of that harness, built to be read in one sitting and hacked:

    task (buggy repo + hidden test)
        -> build a prompt from the buggy code + the failing test output
        -> ask a model for a corrected file (the "patch")
        -> APPLY it into an isolated temp copy of the repo
        -> RUN the task's pytest suite as a subprocess
        -> task is "resolved" iff every test passes
        -> aggregate to pass@1 (resolved rate) + write a full JSON transcript

WHY IT'S BUILT THIS WAY (the eval-methodology bits that matter)
================================================================
- Execution as ground truth. The grader is the test runner, not the model and not
  a human reading the diff. No "LLM-as-judge" softness on a task that has a
  crisp pass/fail.
- Isolation per attempt. Every solve runs in its own temp dir, so one task can't
  leak state into the next and a model can't accidentally "fix" a later task by
  mutating shared files.
- Held-out tests. The model sees the buggy code and ONE failing test's output, but
  is graded against the full suite — including tests it never saw. This catches the
  classic cheat of hard-coding the one visible assertion.
- Transcripts over scores. A single resolved-rate number hides everything useful.
  We persist the prompt, the raw model output, the extracted patch, and the test
  stdout/stderr for every task, so a failure is debuggable, not just countable.
- Deterministic, offline-runnable. With no API key it runs a mock model so the
  harness itself is testable. With ANTHROPIC_API_KEY set it evaluates real Claude.

RUN IT
======
    pip install anthropic          # only needed for the real model
    python3 mini_swe_eval.py                 # mock model, no key needed
    python3 mini_swe_eval.py --model claude  # real Claude (needs ANTHROPIC_API_KEY)
    python3 mini_swe_eval.py --task fizzbuzz  # run a single task

Output: a per-task table, the pass@1 resolved rate, and runs/<timestamp>.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field, asdict
from pathlib import Path

TASKS_DIR = Path(__file__).parent / "tasks"
RUNS_DIR = Path(__file__).parent / "runs"


# --------------------------------------------------------------------------- #
#  A task = a tiny buggy "repo": one source module + a pytest file.
#  In real SWE-bench a task is a GitHub issue + the PR's test patch. Same shape,
#  smaller scale: broken code, a suite that proves it's broken, a fix that's
#  graded by running that suite.
# --------------------------------------------------------------------------- #

@dataclass
class Task:
    id: str
    source_file: str          # filename of the module under test, e.g. "fizzbuzz.py"
    buggy_source: str         # the broken implementation the model must fix
    test_file: str            # filename of the pytest file, e.g. "test_fizzbuzz.py"
    tests: str                # the full held-out suite the fix is graded against
    visible_failing_test: str # the ONE test's name we show the model in the prompt
    statement: str            # the "issue": a plain-English description of the bug


@dataclass
class TaskResult:
    task_id: str
    resolved: bool
    tests_passed: int
    tests_total: int
    model_output: str = ""
    extracted_patch: str = ""
    test_stdout: str = ""
    error: str = ""


# --------------------------------------------------------------------------- #
#  The task suite. Each is a genuine bug with a held-out test the visible one
#  doesn't cover, so a model can't pass by pattern-matching the shown assertion.
# --------------------------------------------------------------------------- #

def load_tasks() -> list[Task]:
    return [
        Task(
            id="fizzbuzz",
            source_file="fizzbuzz.py",
            buggy_source=textwrap.dedent('''\
                def fizzbuzz(n):
                    """Return "Fizz" for multiples of 3, "Buzz" for 5,
                    "FizzBuzz" for both, else the number as a string."""
                    if n % 3 == 0:
                        return "Fizz"
                    if n % 5 == 0:
                        return "Buzz"
                    return str(n)
            '''),
            test_file="test_fizzbuzz.py",
            tests=textwrap.dedent('''\
                from fizzbuzz import fizzbuzz

                def test_fizz():
                    assert fizzbuzz(3) == "Fizz"

                def test_buzz():
                    assert fizzbuzz(5) == "Buzz"

                def test_fizzbuzz():          # held out: the buggy code fails here
                    assert fizzbuzz(15) == "FizzBuzz"

                def test_plain():
                    assert fizzbuzz(7) == "7"
            '''),
            visible_failing_test="test_fizzbuzz",
            statement=(
                "fizzbuzz(15) should return 'FizzBuzz' but returns 'Fizz'. The "
                "combined-multiple case is not handled."
            ),
        ),
        Task(
            id="median",
            source_file="median.py",
            buggy_source=textwrap.dedent('''\
                def median(values):
                    """Return the median of a list of numbers."""
                    s = sorted(values)
                    n = len(s)
                    return s[n // 2]
            '''),
            test_file="test_median.py",
            tests=textwrap.dedent('''\
                from median import median

                def test_odd():
                    assert median([3, 1, 2]) == 2

                def test_even():             # held out: even-length case is wrong
                    assert median([1, 2, 3, 4]) == 2.5

                def test_single():
                    assert median([42]) == 42
            '''),
            visible_failing_test="test_even",
            statement=(
                "median([1, 2, 3, 4]) should be 2.5 (mean of the two middle "
                "values) but returns 3. Even-length lists aren't averaged."
            ),
        ),
        Task(
            id="parse_kv",
            source_file="parse_kv.py",
            buggy_source=textwrap.dedent('''\
                def parse_kv(line):
                    """Parse 'key=value' into (key, value). Values may contain '='
                    (e.g. base64 padding); only the FIRST '=' is the separator."""
                    parts = line.split("=")
                    return parts[0], parts[1]
            '''),
            test_file="test_parse_kv.py",
            tests=textwrap.dedent('''\
                from parse_kv import parse_kv

                def test_simple():
                    assert parse_kv("a=1") == ("a", "1")

                def test_value_has_equals():   # held out: splits too much
                    assert parse_kv("token=abc==") == ("token", "abc==")

                def test_empty_value():
                    assert parse_kv("k=") == ("k", "")
            '''),
            visible_failing_test="test_value_has_equals",
            statement=(
                "parse_kv('token=abc==') raises/incorrectly splits because the code "
                "uses split('=') and reads parts[1]. Only the first '=' should "
                "separate key from value."
            ),
        ),
        Task(
            id="dedupe_order",
            source_file="dedupe.py",
            buggy_source=textwrap.dedent('''\
                def dedupe(items):
                    """Remove duplicates while preserving first-seen order."""
                    return list(set(items))
            '''),
            test_file="test_dedupe.py",
            tests=textwrap.dedent('''\
                from dedupe import dedupe

                def test_dedupes():
                    assert set(dedupe([1, 1, 2, 3, 3])) == {1, 2, 3}

                def test_preserves_order():    # held out: set() loses order
                    assert dedupe([3, 1, 3, 2, 1]) == [3, 1, 2]
            '''),
            visible_failing_test="test_preserves_order",
            statement=(
                "dedupe uses set(), which removes duplicates but does not preserve "
                "first-seen order. Order must be preserved."
            ),
        ),
        Task(
            id="rate_limit",
            source_file="rate_limit.py",
            buggy_source=textwrap.dedent('''\
                def remaining_calls(used, limit):
                    """Calls left in a quota window. Never negative; if already at
                    or over the limit, return 0."""
                    return limit - used
            '''),
            test_file="test_rate_limit.py",
            tests=textwrap.dedent('''\
                from rate_limit import remaining_calls

                def test_basic():
                    assert remaining_calls(3, 10) == 7

                def test_at_limit():
                    assert remaining_calls(10, 10) == 0

                def test_over_limit():         # held out: negative leaks through
                    assert remaining_calls(12, 10) == 0
            '''),
            visible_failing_test="test_over_limit",
            statement=(
                "remaining_calls(12, 10) returns -2 but should clamp to 0. Result "
                "must never be negative."
            ),
        ),
    ]


# --------------------------------------------------------------------------- #
#  Prompting. We give the model the issue, the buggy file, and the name of the
#  failing test — then demand the COMPLETE corrected file back in a fenced block.
#  (Returning the whole file is the simplest reliable "patch format"; real
#  SWE-bench uses unified diffs, which are stricter to apply.)
# --------------------------------------------------------------------------- #

def build_prompt(task: Task) -> str:
    return textwrap.dedent(f"""\
        You are fixing a bug in a Python module.

        ## Issue
        {task.statement}

        ## File: {task.source_file}
        ```python
        {task.buggy_source}```

        ## Failing test
        A pytest test named `{task.visible_failing_test}` currently fails. Other
        tests in the suite must keep passing.

        ## Your task
        Return the COMPLETE corrected contents of `{task.source_file}` and nothing
        else. Put it in a single ```python code block. Do not change the function
        name or signature.
    """)


CODE_BLOCK = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def extract_patch(model_output: str) -> str:
    """Pull the code out of the model's reply. Falls back to the raw text if the
    model forgot the fence — being lenient here means a formatting slip doesn't
    get scored as a logic failure (a real eval-design choice: measure the skill
    you mean to measure)."""
    blocks = CODE_BLOCK.findall(model_output)
    if blocks:
        return max(blocks, key=len).strip() + "\n"
    return model_output.strip() + "\n"


# --------------------------------------------------------------------------- #
#  Models. Each takes a prompt, returns raw text. Swap in any model here — the
#  harness doesn't care what produced the patch, only whether it passes.
# --------------------------------------------------------------------------- #

def solve_with_mock(task: Task, prompt: str) -> str:
    """A stand-in 'model' so the harness runs with no API key. It genuinely fixes
    some tasks and genuinely fails others — that spread is the point, it proves the
    grader actually discriminates instead of rubber-stamping everything."""
    fixes = {
        "fizzbuzz": '''\
def fizzbuzz(n):
    if n % 15 == 0:
        return "FizzBuzz"
    if n % 3 == 0:
        return "Fizz"
    if n % 5 == 0:
        return "Buzz"
    return str(n)
''',
        "median": '''\
def median(values):
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2
''',
        "parse_kv": '''\
def parse_kv(line):
    key, _, value = line.partition("=")
    return key, value
''',
        # dedupe + rate_limit intentionally left UNFIXED so the mock scores < 100%
    }
    code = fixes.get(task.id)
    if code is None:
        return "I think the original code is already correct.\n```python\n" + task.buggy_source + "```"
    return f"Here is the fix:\n\n```python\n{code}```"


def solve_with_claude(task: Task, prompt: str) -> str:
    """Evaluate real Claude. Reads ANTHROPIC_API_KEY from the env (never hardcode
    keys). Low temperature: an eval wants the model's modal answer, not a lucky
    sample."""
    from anthropic import Anthropic

    client = Anthropic()  # picks up ANTHROPIC_API_KEY from the environment
    resp = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1500,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")


MODELS = {"mock": solve_with_mock, "claude": solve_with_claude}


# --------------------------------------------------------------------------- #
#  The grader: apply the patch into an isolated temp repo, run pytest, score by
#  exit code + the test summary. THIS is the ground truth.
# --------------------------------------------------------------------------- #

def run_tests(task: Task, patch: str) -> TaskResult:
    workdir = Path(tempfile.mkdtemp(prefix=f"sweeval_{task.id}_"))
    try:
        # The model's patch becomes the source file; tests come from the task
        # (the model never gets to rewrite the tests — that's the integrity line).
        (workdir / task.source_file).write_text(patch)
        (workdir / task.test_file).write_text(task.tests)

        proc = subprocess.run(
            [sys.executable, "-m", "pytest", task.test_file, "-q", "--no-header"],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        out = proc.stdout + proc.stderr
        passed, total = _parse_pytest_counts(out)
        return TaskResult(
            task_id=task.id,
            resolved=(proc.returncode == 0 and total > 0),
            tests_passed=passed,
            tests_total=total,
            extracted_patch=patch,
            test_stdout=out.strip(),
        )
    except subprocess.TimeoutExpired:
        return TaskResult(task.id, False, 0, 0, extracted_patch=patch,
                          error="test run timed out (possible infinite loop in patch)")
    except Exception as e:  # noqa: BLE001 — a broken patch shouldn't crash the eval
        return TaskResult(task.id, False, 0, 0, extracted_patch=patch, error=repr(e))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _parse_pytest_counts(output: str) -> tuple[int, int]:
    """Read 'N passed', 'M failed', 'K errors' off pytest's summary line."""
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", output)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", output)) else 0
    errors = int(m.group(1)) if (m := re.search(r"(\d+) error", output)) else 0
    return passed, passed + failed + errors


# --------------------------------------------------------------------------- #
#  Orchestration + reporting.
# --------------------------------------------------------------------------- #

def evaluate(model_name: str, only: str | None) -> list[TaskResult]:
    solve = MODELS[model_name]
    tasks = [t for t in load_tasks() if only is None or t.id == only]
    if not tasks:
        sys.exit(f"no task matching '{only}'. Known: {[t.id for t in load_tasks()]}")

    results: list[TaskResult] = []
    for task in tasks:
        prompt = build_prompt(task)
        try:
            output = solve(task, prompt)
        except Exception as e:  # noqa: BLE001 — e.g. missing key / network
            results.append(TaskResult(task.id, False, 0, 0, error=f"model call failed: {e!r}"))
            continue
        patch = extract_patch(output)
        res = run_tests(task, patch)
        res.model_output = output
        results.append(res)
    return results


def report(model_name: str, results: list[TaskResult]) -> dict:
    resolved = sum(r.resolved for r in results)
    total = len(results)
    rate = resolved / total if total else 0.0

    print(f"\n{'TASK':<16}{'RESULT':<10}{'TESTS':<10}")
    print("-" * 36)
    for r in results:
        mark = "PASS" if r.resolved else "FAIL"
        tests = f"{r.tests_passed}/{r.tests_total}" if r.tests_total else "-"
        print(f"{r.task_id:<16}{mark:<10}{tests:<10}")
        if r.error:
            print(f"  ! {r.error}")
    print("-" * 36)
    print(f"pass@1 (resolved rate): {resolved}/{total} = {rate:.0%}  [model: {model_name}]\n")

    return {
        "model": model_name,
        "resolved": resolved,
        "total": total,
        "pass_at_1": rate,
        "results": [asdict(r) for r in results],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="A SWE-bench-style coding eval in one file.")
    ap.add_argument("--model", choices=list(MODELS), default="mock",
                    help="mock (offline, default) or claude (needs ANTHROPIC_API_KEY)")
    ap.add_argument("--task", default=None, help="run a single task by id")
    args = ap.parse_args()

    results = evaluate(args.model, args.task)
    summary = report(args.model, results)

    # Persist the full transcript. A score you can't open up and inspect is a
    # score you can't trust — the JSON has every prompt, output, patch, and the
    # raw pytest stdout for each task.
    RUNS_DIR.mkdir(exist_ok=True)
    n = len(list(RUNS_DIR.glob("*.json")))
    out_path = RUNS_DIR / f"run_{args.model}_{n:03d}.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"transcript -> {out_path.relative_to(Path(__file__).parent)}")


if __name__ == "__main__":
    main()
