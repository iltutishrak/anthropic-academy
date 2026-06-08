# swe-eval: a SWE-bench-style agentic coding eval, in one file

SWE-bench gives a model a real repo with a failing test, asks for a code change,
then **runs the test suite** to decide if the change actually fixed the bug. The
model is graded by execution, not by whether its answer looks right. That
execution-grounded loop is the whole point: it's why SWE-bench tracks real
engineering ability and why eyeballing diffs does not.

[`mini_swe_eval.py`](mini_swe_eval.py) is a readable miniature of that harness:

```
task (buggy module + held-out pytest suite)
  -> build a prompt from the buggy code + the failing test
  -> ask a model for the corrected file (the "patch")
  -> apply it into an isolated temp copy of the repo
  -> run the pytest suite as a subprocess
  -> resolved iff every test passes
  -> aggregate to pass@1 + write a full JSON transcript
```

## The eval-methodology choices that matter

- **Execution is the grader.** The test runner decides pass/fail, not the model
  and not a human reading the diff. No LLM-as-judge softness on a task with a
  crisp answer.
- **Held-out tests.** The model sees the buggy code and one failing test, but is
  graded against the full suite including tests it never saw. This catches the
  classic cheat of hard-coding the one visible assertion.
- **Isolation per attempt.** Every solve runs in its own temp dir, so one task
  can't leak state into the next.
- **Transcripts over scores.** A single resolved-rate number hides everything
  useful. Every run persists the prompt, raw model output, extracted patch, and
  pytest stdout per task, so a failure is debuggable, not just countable.
- **Offline-runnable.** With no key it runs a mock model that genuinely fixes
  some tasks and fails others, which proves the grader discriminates instead of
  rubber-stamping. With `ANTHROPIC_API_KEY` set it evaluates real Claude.

## Run it

```bash
pip install anthropic            # only needed for the real model
python3 mini_swe_eval.py                 # mock model, no key needed
python3 mini_swe_eval.py --model claude  # real Claude (needs ANTHROPIC_API_KEY)
python3 mini_swe_eval.py --task median   # run a single task
```

Mock run, showing the grader actually discriminates:

```
TASK            RESULT    TESTS
------------------------------------
fizzbuzz        PASS      4/4
median          PASS      3/3
parse_kv        PASS      3/3
dedupe_order    FAIL      1/2
rate_limit      FAIL      2/3
------------------------------------
pass@1 (resolved rate): 3/5 = 60%  [model: mock]
```

Built for the Anthropic Academy track. The point isn't the five toy tasks, it's
the harness shape: swap in real repos and the same loop scores them.
