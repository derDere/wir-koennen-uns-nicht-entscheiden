# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A group decision-making web application where members anonymously submit options, accept others' options, and a fair random selection picks the result. The "fairness" comes from grouping items by acceptance patterns and picking a random group first, then a random item within it.

## Technology Stack

- Python with venv and pip
- Flet (flet.dev) for web UI
- Flet PubSub for real-time session synchronization between members
- Browser local storage for member ID and session ID persistence
- Dependencies in requirements.txt

## Development Commands

```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Unix/macOS)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the Flet application
flet run main.py

# Run as web app
flet run --web main.py
```

## Application Flow

1. **Session creation/joining**: 6-char alphanumeric codes, anonymous members
2. **Add items phase**: Each member creates their own list (duplicates prevented at input, remove button available). Ready button (undoable). Shows "X of Y ready"
3. **Acceptance phase**: Members see only OTHER members' items, check which they'd accept. Own items auto-accepted
4. **Grouping**: Items grouped by member acceptance combinations (e.g., "accepted by A and B", "accepted by all")
5. **Selection**: Random group picked, then random item from that group
6. **Result options**: Re-roll, roll-next (exclude picked), or start fresh

## Key Implementation Details

### Item Comparison/Deduplication
Items are considered equal if they match after:
1. Stripping all whitespace
2. Stripping all special characters
3. Converting to lowercase

Deduplication happens:
- Within a member's own list: **prevented at input** (show error/warning, don't allow adding)
- Within groups (after acceptance grouping): merged automatically

### Fair Selection Algorithm
```python
rnd = random.randint(length * 10000, length * 90000)
index = rnd % length
```
This is intentional to spread randomness. First pick a random group, then a random item within it. This ensures members who submit many items don't dominate.

### Session Management
- Use Flet PubSub for real-time sync (see https://flet.dev/docs/cookbook/pub-sub/)
- Store member_id and session_id in browser local storage (`page.client_storage`)
- On reconnect, restore session if still available
- Same member_id rejoining same session gets their previous list (anti-gaming)
- Sessions expire after 7 days of inactivity (reset on any activity)
- No minimum member count required

### UI States
- Landing: Create or join session
- Add items: Text input + list display with remove buttons + ready button (duplicate input prevented)
- Waiting: "X of Y members ready" with cancel option
- Acceptance: Checkboxes for other members' items
- Result: Selected item + three action buttons (re-roll, roll-next, start fresh)
