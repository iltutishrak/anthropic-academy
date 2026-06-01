# Building with the Claude API — track project

A set of small, runnable demos for the AWS EC2 Mac instance family, each making one
part of the Claude API concrete. I built these for the Anthropic Academy "Building
with the Claude API" track to learn by building, not just watching.

## The files

| File | What it teaches |
| --- | --- |
| [`ec2_mac_forecaster.py`](ec2_mac_forecaster.py) | The core: messages, system prompt, multi-turn history, streaming, tool use, prompt caching, adaptive thinking — all in one conversation loop |
| [`structured_forecast.py`](structured_forecast.py) | Structured outputs — a Pydantic schema makes Claude return typed, validated data instead of prose |
| [`batch_forecast.py`](batch_forecast.py) | Batches — re-forecast the whole fleet in one async job at 50% cost |
| [`files_demo.py`](files_demo.py) | Files API — upload a capacity report once, ask many questions about it |
| [`vision_demo.py`](vision_demo.py) | Vision — Claude reads a generated utilization chart and assesses risk |

Each file is self-contained (generates its own inputs where needed) and reads the
API key from `ANTHROPIC_API_KEY` — never hardcoded.

## The flagship: `ec2_mac_forecaster.py`

## What it demonstrates

| Concept | Where, in the file |
| --- | --- |
| Messages API | the `client.messages.stream(...)` call in `converse()` |
| System prompt | the `SYSTEM` list (role block + handbook block) |
| Multi-turn history | the `messages` list grown by hand each turn (the API is stateless) |
| Streaming | the `for event in stream` loop printing thinking + text live |
| Tool use | `get_demand_forecast` / `get_capacity` + the run-and-feed-back loop |
| Prompt caching | `cache_control` on the static capacity handbook |
| Extended thinking | `thinking={"type": "adaptive", "display": "summarized"}` |

## Run it

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...     # read from env, never hardcoded
python3 ec2_mac_forecaster.py
```

It runs a scripted three-turn conversation: forecast + capacity for a pool in
us-east-1, the same for the thinner eu-west-1 pool, then a recommendation ahead of
an iOS GA. Watch the `[usage]` line each turn — on later turns `cache_read` should
be non-zero, showing the handbook being reused from cache instead of reprocessed.

## The lesson behind the design

The model has no memory across calls, can't fetch live data on its own, and is
expensive to re-feed. Every feature here answers one of those limits: history we
resend ourselves, tools for live numbers, caching so the static handbook isn't
re-billed each turn. That mapping — features as answers to model limits — is the
whole mental model of the course.

## Notes

- Built to current best practices: `claude-opus-4-8`, adaptive thinking, env-var
  key. Swap `MODEL` to Sonnet or Haiku for cheaper runs while learning.
- The tool data is mocked but deterministic; in production these would hit a real
  forecasting service and capacity database.
- Caching only engages above the model's minimum cacheable prefix (~4096 tokens
  for Opus). If `cache_write` shows 0, the handbook is below that threshold — a
  real lesson in itself.
