"""
files_demo.py

Getting a whole document into the prompt with the Files API.

The master key from Claude 101: Claude is strong when the info is IN the prompt.
For a big document you ask many questions about, you don't want to paste it every
time. The Files API lets you upload it ONCE, get a file_id, and reference it in any
request. Here we upload a capacity report and ask questions about it.

This script generates its own sample report so it runs with no setup.

    pip install anthropic
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 files_demo.py
"""

from __future__ import annotations

import os

import anthropic


MODEL = "claude-opus-4-8"

# A sample capacity report. In real life this is a file you already have (a PDF,
# a CSV export, a runbook). We write it to disk so the demo is self-contained.
REPORT_TEXT = """\
EC2 Mac Fleet - Weekly Capacity Report (Week 37)

us-east-1
  mac2-m2.metal:    allocated 260, peak in use 248, utilization 0.95  [AT RISK]
  mac2-m2pro.metal: allocated 110, peak in use 71,  utilization 0.65
  mac2.metal:       allocated 200, peak in use 96,  utilization 0.48
  mac1.metal:       allocated 120, peak in use 22,  utilization 0.18  [OVER-PROVISIONED]

eu-west-1
  mac2-m2.metal:    allocated 80,  peak in use 76,  utilization 0.95  [AT RISK]

Notes:
- iOS GA is in 9 days; the two AT RISK pools sit above the 85% pre-event threshold.
- mac1.metal in us-east-1 has been below 25% for 3 straight weeks.
- No same-day large drawdowns permitted (24-hour host allocation floor).
"""

REPORT_PATH = "weekly_capacity_report.txt"


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY first:  export ANTHROPIC_API_KEY=sk-ant-...")

    client = anthropic.Anthropic()

    # Write the sample report so we have a real file to upload.
    with open(REPORT_PATH, "w") as f:
        f.write(REPORT_TEXT)

    # 1. Upload ONCE -> get a file_id you can reference in many requests.
    uploaded = client.beta.files.upload(
        file=(REPORT_PATH, open(REPORT_PATH, "rb"), "text/plain"),
        betas=["files-api-2025-04-14"],
    )
    print(f"Uploaded {REPORT_PATH} -> file_id {uploaded.id}\n")

    # 2. Ask several questions, each referencing the file by id (no re-upload).
    questions = [
        "Which pools are flagged AT RISK, and why does that matter given the timeline?",
        "Which pool is wasting money, and what's the constraint on fixing it today?",
    ]

    for q in questions:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=512,
            betas=["files-api-2025-04-14"],
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": q},
                    {"type": "document", "source": {"type": "file", "file_id": uploaded.id}},
                ],
            }],
        )
        answer = next((b.text for b in response.content if b.type == "text"), "")
        print(f"Q: {q}\nA: {answer.strip()}\n")

    # 3. Clean up the uploaded file when done (good hygiene; storage is limited).
    client.beta.files.delete(uploaded.id, betas=["files-api-2025-04-14"])
    print(f"Deleted uploaded file {uploaded.id}.")


if __name__ == "__main__":
    main()
