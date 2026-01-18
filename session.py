"""
Session management module with business logic.
"""

import random
import re
import string
import time
import uuid
from typing import Optional
from collections import defaultdict

import database as db

# Characters for session codes (excluding confusing ones: 0, O, 1, I, L)
SESSION_CODE_CHARS = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
SESSION_CODE_LENGTH = 6

# Timeout for auto-ready (2 minutes)
AUTO_READY_TIMEOUT = 2 * 60

# Session phases
PHASE_ADDING = "adding"
PHASE_ACCEPTING = "accepting"
PHASE_RESULT = "result"


def generate_session_code() -> str:
    """Generate a unique 6-character session code."""
    while True:
        code = "".join(random.choices(SESSION_CODE_CHARS, k=SESSION_CODE_LENGTH))
        if not db.session_exists(code):
            return code


def generate_member_id() -> str:
    """Generate a unique member ID."""
    return str(uuid.uuid4())


def normalize_item(item: str) -> str:
    """
    Normalize an item for comparison.
    Strips whitespace, special characters, and converts to lowercase.
    """
    # Remove all whitespace
    normalized = re.sub(r"\s+", "", item)
    # Remove all special characters (keep only alphanumeric)
    normalized = re.sub(r"[^a-zA-Z0-9]", "", normalized)
    # Convert to lowercase
    return normalized.lower()


def items_equal(item1: str, item2: str) -> bool:
    """Check if two items are equal after normalization."""
    return normalize_item(item1) == normalize_item(item2)


def is_duplicate_item(new_item: str, existing_items: list) -> bool:
    """Check if a new item is a duplicate of any existing item."""
    new_normalized = normalize_item(new_item)
    if not new_normalized:
        return True  # Empty items are considered duplicates
    for item in existing_items:
        if normalize_item(item) == new_normalized:
            return True
    return False


def create_session(creator_id: str) -> Optional[str]:
    """Create a new session and return the session code."""
    session_code = generate_session_code()
    if db.create_session(session_code, creator_id):
        return session_code
    return None


def join_session(session_code: str, member_id: str) -> dict:
    """
    Join an existing session.
    Returns a dict with status and info.
    """
    session_code = session_code.upper()
    session = db.get_session(session_code)

    if not session:
        return {"success": False, "error": "Session not found"}

    # Check if member already exists in this session
    existing_member = db.get_member(session_code, member_id)
    if existing_member:
        db.update_member_last_seen(session_code, member_id)
        return {
            "success": True,
            "rejoined": True,
            "is_observer": existing_member["is_observer"],
            "phase": session["phase"]
        }

    # New member joining
    is_observer = session["phase"] != PHASE_ADDING
    if db.add_member(session_code, member_id, is_observer):
        return {
            "success": True,
            "rejoined": False,
            "is_observer": is_observer,
            "phase": session["phase"]
        }

    return {"success": False, "error": "Could not join session"}


def add_item(session_id: str, member_id: str, item: str) -> dict:
    """Add an item to a member's list."""
    item = item.strip()
    if not item:
        return {"success": False, "error": "Item cannot be empty"}

    member = db.get_member(session_id, member_id)
    if not member:
        return {"success": False, "error": "Member not found"}

    if member["is_observer"]:
        return {"success": False, "error": "Observers cannot add items"}

    if member["is_ready"]:
        return {"success": False, "error": "Cannot add items after marking ready"}

    if is_duplicate_item(item, member["items"]):
        return {"success": False, "error": "Duplicate item"}

    items = member["items"] + [item]
    db.update_member_items(session_id, member_id, items)
    return {"success": True, "items": items}


def remove_item(session_id: str, member_id: str, item_index: int) -> dict:
    """Remove an item from a member's list."""
    member = db.get_member(session_id, member_id)
    if not member:
        return {"success": False, "error": "Member not found"}

    if member["is_ready"]:
        return {"success": False, "error": "Cannot remove items after marking ready"}

    if item_index < 0 or item_index >= len(member["items"]):
        return {"success": False, "error": "Invalid item index"}

    items = member["items"].copy()
    items.pop(item_index)
    db.update_member_items(session_id, member_id, items)
    return {"success": True, "items": items}


def set_ready(session_id: str, member_id: str, is_ready: bool) -> dict:
    """Set a member's ready status."""
    member = db.get_member(session_id, member_id)
    if not member:
        return {"success": False, "error": "Member not found"}

    if member["is_observer"]:
        return {"success": False, "error": "Observers cannot set ready status"}

    db.set_member_ready(session_id, member_id, is_ready)
    return {"success": True}


def get_ready_status(session_id: str) -> dict:
    """Get the ready status for all members."""
    members = db.get_active_members(session_id)
    now = time.time()

    ready_count = 0
    total_count = len(members)

    for member in members:
        # Check if member is ready or has timed out
        if member["is_ready"]:
            ready_count += 1
        elif now - member["last_seen"] > AUTO_READY_TIMEOUT:
            # Auto-ready disconnected members
            db.set_member_ready(session_id, member["member_id"], True)
            ready_count += 1

    return {
        "ready": ready_count,
        "total": total_count,
        "all_ready": ready_count == total_count and total_count > 0
    }


def check_and_advance_phase(session_id: str) -> Optional[str]:
    """
    Check if all members are ready and advance to next phase.
    Returns the new phase if advanced, None otherwise.
    """
    session = db.get_session(session_id)
    if not session:
        return None

    status = get_ready_status(session_id)
    if not status["all_ready"]:
        return None

    current_phase = session["phase"]

    if current_phase == PHASE_ADDING:
        # Advance to acceptance phase
        db.reset_all_ready_status(session_id)
        db.set_session_phase(session_id, PHASE_ACCEPTING)
        return PHASE_ACCEPTING

    elif current_phase == PHASE_ACCEPTING:
        # Advance to result phase
        db.set_session_phase(session_id, PHASE_RESULT)
        return PHASE_RESULT

    return None


def get_items_for_acceptance(session_id: str, member_id: str) -> list:
    """Get all items except the member's own items for acceptance."""
    members = db.get_active_members(session_id)
    items = []

    for member in members:
        if member["member_id"] != member_id:
            for item in member["items"]:
                # Avoid duplicates in the display list
                if not any(items_equal(item, existing) for existing in items):
                    items.append(item)

    return items


def get_all_items(session_id: str) -> list:
    """Get all items from all members."""
    members = db.get_active_members(session_id)
    items = []

    for member in members:
        for item in member["items"]:
            if not any(items_equal(item, existing) for existing in items):
                items.append(item)

    return items


def set_accepted_items(session_id: str, member_id: str, accepted_items: list) -> dict:
    """Set a member's accepted items."""
    member = db.get_member(session_id, member_id)
    if not member:
        return {"success": False, "error": "Member not found"}

    if member["is_observer"]:
        return {"success": False, "error": "Observers cannot accept items"}

    db.update_member_accepted_items(session_id, member_id, accepted_items)
    return {"success": True}


def fair_random_select(length: int) -> int:
    """
    Fair random selection using the specified algorithm.
    rnd = random.randint(length * 10000, length * 90000)
    index = rnd % length
    """
    if length <= 0:
        return 0
    rnd = random.randint(length * 10000, length * 90000)
    return rnd % length


def group_items_by_acceptance(session_id: str) -> dict:
    """
    Group items by their acceptance patterns.
    Returns a dict where keys are frozensets of member IDs who accepted,
    and values are lists of items.
    """
    members = db.get_active_members(session_id)
    excluded = db.get_excluded_items(session_id)

    # Build a mapping of normalized item -> original item
    # and track which members accept each item
    item_acceptances = defaultdict(set)
    normalized_to_original = {}

    for member in members:
        member_id = member["member_id"]

        # Member's own items are auto-accepted
        for item in member["items"]:
            norm = normalize_item(item)
            if norm not in normalized_to_original:
                normalized_to_original[norm] = item
            item_acceptances[norm].add(member_id)

        # Explicitly accepted items
        for item in member["accepted_items"]:
            norm = normalize_item(item)
            if norm in normalized_to_original:
                item_acceptances[norm].add(member_id)

    # Group by acceptance pattern
    groups = defaultdict(list)
    for norm, original in normalized_to_original.items():
        # Skip excluded items
        if any(items_equal(original, ex) for ex in excluded):
            continue

        acceptors = frozenset(item_acceptances[norm])
        if acceptors:  # Only include items that have at least one acceptor
            groups[acceptors].append(original)

    return dict(groups)


def select_item(session_id: str) -> Optional[str]:
    """
    Select an item using the fair selection algorithm.
    First picks a random group, then a random item within that group.
    """
    groups = group_items_by_acceptance(session_id)

    if not groups:
        # If all items are excluded, reset the pool
        db.clear_excluded_items(session_id)
        groups = group_items_by_acceptance(session_id)
        if not groups:
            return None

    # Pick a random group
    group_list = list(groups.values())
    group_index = fair_random_select(len(group_list))
    selected_group = group_list[group_index]

    # Pick a random item from the group
    item_index = fair_random_select(len(selected_group))
    return selected_group[item_index]


def reroll(session_id: str) -> Optional[str]:
    """Re-roll: pick from the same pool."""
    return select_item(session_id)


def roll_next(session_id: str, current_item: str) -> Optional[str]:
    """Roll next: exclude current item and pick again."""
    excluded = db.get_excluded_items(session_id)
    if not any(items_equal(current_item, ex) for ex in excluded):
        excluded.append(current_item)
        db.set_excluded_items(session_id, excluded)

    return select_item(session_id)


def vote_restart(session_id: str, member_id: str) -> dict:
    """Add a restart vote."""
    db.add_restart_vote(session_id, member_id)
    votes = db.get_restart_votes(session_id)
    members = db.get_active_members(session_id)

    # Check if all members voted
    all_voted = all(m["member_id"] in votes for m in members)

    return {
        "votes": len(votes),
        "total": len(members),
        "all_voted": all_voted
    }


def start_fresh(session_id: str):
    """Reset the session for a fresh start."""
    db.clear_all_items(session_id)
    db.reset_all_ready_status(session_id)
    db.reset_all_accepted_items(session_id)
    db.clear_excluded_items(session_id)
    db.clear_restart_votes(session_id)
    db.promote_observers(session_id)
    db.set_session_phase(session_id, PHASE_ADDING)


def leave_session(session_id: str, member_id: str):
    """Handle a member leaving the session (their items stay)."""
    # We don't delete the member, just mark them as disconnected
    # Their items and acceptances remain
    pass


def is_creator(session_id: str, member_id: str) -> bool:
    """Check if a member is the session creator."""
    creator = db.get_session_creator(session_id)
    return creator == member_id


def is_creator_connected(session_id: str) -> bool:
    """Check if the session creator is currently connected (seen recently)."""
    session = db.get_session(session_id)
    if not session:
        return False

    member = db.get_member(session_id, session["creator_id"])
    if not member:
        return False

    # Consider connected if seen in the last 30 seconds
    return time.time() - member["last_seen"] < 30


def get_session_state(session_id: str, member_id: str) -> dict:
    """Get the full session state for a member."""
    session = db.get_session(session_id)
    if not session:
        return {"error": "Session not found"}

    member = db.get_member(session_id, member_id)
    if not member:
        return {"error": "Member not found"}

    members = db.get_active_members(session_id)
    ready_status = get_ready_status(session_id)

    return {
        "session_id": session_id,
        "phase": session["phase"],
        "is_creator": is_creator(session_id, member_id),
        "creator_connected": is_creator_connected(session_id),
        "is_observer": member["is_observer"],
        "my_items": member["items"],
        "my_accepted_items": member["accepted_items"],
        "is_ready": member["is_ready"],
        "ready_count": ready_status["ready"],
        "total_members": ready_status["total"],
        "all_ready": ready_status["all_ready"],
        "restart_votes": len(db.get_restart_votes(session_id)),
        "all_items": get_all_items(session_id) if session["phase"] == PHASE_RESULT else []
    }
