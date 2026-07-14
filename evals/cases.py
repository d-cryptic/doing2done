"""Golden extraction cases. Each guards a real behavior; run via `d2d eval`."""

CASES = [
    {
        # Regression guard for the handwriting bug: transcription must drive extraction,
        # and the classifier must NOT invent unrelated "hackathon/meeting" todos.
        "name": "handwritten-todos",
        "text": (
            "Todos\n"
            "wash clothes, take clothes\n"
            "Go to gym\n"
            "GST call and confirm Aadhar KYC\n"
            "CKAD prep, CKAD exam date\n"
            "RS: compliance (doing)\n"
            "RS: Azure\n"
            "IGT: Report\n"
            "Grocery\n"
            "Drink protein, take supplements\n"
            "SBI KYC"
        ),
        "expect_todos": ["ckad", "gst", "grocery", "sbi"],
        "forbid_todos": ["hackathon", "sarah", "presentation deck", "dummy db", "demo script"],
    },
    {
        "name": "time-parsing",
        "text": "Call the dentist tomorrow at 5pm",
        "expect_todos": ["dentist"],
        "expect_time": True,
    },
    {
        "name": "meeting-actions",
        "text": "Team sync. Action items: ship the API by Friday, and review the open PRs.",
        "expect_todos": ["ship", "review"],
    },
    {
        "name": "prose-no-todos",
        "text": (
            "Idea: the handwriting-to-text flow feels like a palimpsest — old marks "
            "rewritten clean. Worth exploring the aesthetic for the site header."
        ),
        "expect_todos": [],
        "max_todos": 1,
    },
    {
        "name": "subtasks",
        "text": "Prepare for launch:\n  - write the docs\n  - set up monitoring\n  - dry-run the deploy",
        "expect_todos": ["prepare"],
        "expect_subtasks": True,
    },
]
