"""
Hermes Life OS - Daily Prompts
==================================
A small, curated set of reflection/journaling prompts, rotated
deterministically by calendar date - the same day always returns the
same prompt (no randomness, no state to persist), and it changes every
day. Meant to nudge richer qualitative journaling (via `remember`)
alongside the numeric trackers, the same way a physical journal's
"prompt of the day" page does.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import List, Optional

DAILY_PROMPTS: List[str] = [
    "What's one thing that went better than expected today?",
    "What's weighing on you right now, even a little?",
    "Who or what are you grateful for today?",
    "What did you avoid today, and why?",
    "What's something you're proud of this week?",
    "If today had a headline, what would it say?",
    "What's one small thing you could do tomorrow to make it easier than today?",
    "What drained your energy today? What gave you energy?",
    "What's a decision you made today that you feel good about?",
    "What would you tell a friend who had the day you just had?",
    "What's something you learned about yourself recently?",
    "What are you looking forward to?",
    "What's a habit you'd like to strengthen this week?",
    "When did you feel most like yourself today?",
    "What's something you've been putting off?",
    "What made you laugh recently?",
    "What's a small win you almost didn't notice?",
    "What's one thing you'd change about today if you could?",
    "Who did you connect with today, and how did it feel?",
    "What does 'enough' look like for you today?",
    "What's a pattern you've noticed in yourself lately?",
    "What are you curious about right now?",
    "What's something you did today purely because you wanted to?",
    "What boundary did you hold (or wish you'd held) today?",
    "What's a worry you can set down, at least for tonight?",
    "What surprised you today?",
    "What's something kind you did for yourself recently?",
    "What would 'a good day' look like tomorrow?",
    "What's a question you're sitting with these days?",
    "What are you ready to let go of?",
]


def get_daily_prompt(date: Optional[str] = None) -> str:
    """Returns the prompt for `date` (YYYY-MM-DD string, default today,
    UTC). Deterministic: hashing the date string means the same date
    always maps to the same prompt, without needing to persist any
    "which prompt did we show" state, and the sequence isn't a simple
    day-of-year cycle either (so it doesn't repeat on a predictable
    yearly schedule)."""
    date = date or datetime.utcnow().strftime("%Y-%m-%d")
    digest = hashlib.sha256(date.encode("utf-8")).hexdigest()
    index = int(digest, 16) % len(DAILY_PROMPTS)
    return DAILY_PROMPTS[index]
