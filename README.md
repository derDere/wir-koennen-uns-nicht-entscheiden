# Wir können uns nicht entscheiden

This project helps groups of people decide what to do by fairly picking an option from a list created by the group in a way that is fair for every member.

## Technology

- Python with venv and pip
- Flet (flet.dev) for web UI with built-in PubSub for real-time session synchronization
- Dependencies managed via requirements.txt

## Usage Flow

### 1. Create or Join a Session
- Create a new session to get a 6-character alphanumeric session code
- Share the code with group members
- Or join an existing session via code
- The session code is always visible at the top right of the page
- Members are anonymous (no usernames)

### 2. Add Items Phase
- Each member creates their own list of options (strings)
- Adding a duplicate item to your own list is prevented (so members can't add the same item multiple times to increase their chances)
- Items can be removed from your list using the remove button (so members can change their mind)
- Press the "Ready" button when done (can be undone before everyone is ready)
- A waiting screen shows "X of Y members ready"

### 3. Acceptance Phase
- Once all members are ready, view a combined list of items from OTHER members only (your own items are not shown because they are automatically counted as accepted by you)
- Check items you would accept as an option - you can check all, some, or none (selecting none is valid since you already have your own options in the pool)

### 4. Grouping and Selection
Items are grouped by which combination of members accept them. For example with members Otto, Max, and Steve:
- Items accepted only by Otto
- Items accepted only by Max
- Items accepted only by Steve
- Items accepted by Otto and Max
- Items accepted by Otto and Steve
- Items accepted by Max and Steve
- Items accepted by all

Empty groups are removed. Duplicate items within groups are merged (comparison: stripped of whitespace and special characters, lowercased).

### 5. Fair Random Selection
The selection algorithm ensures fairness by:
1. First picking a random **group** (this prevents members with more items from dominating)
2. Then picking a random **item** within that group

**Random calculation:** `rnd = random(length * 10000, length * 90000)`, then `index = rnd % length`
This spread helps ensure better randomness distribution.

### 6. After the Result
Three options are available:
- **Re-roll**: Pick again from the same items/acceptances
- **Roll next**: Pick again but exclude previously picked items (allows cycling through all options)
- **Start fresh**: Begin a new session

## Technical Details

### Session Management
- Sessions use Flet's built-in PubSub for real-time synchronization between members
- Member ID and session ID are stored in browser local storage (so disconnected members can rejoin their session automatically)
- If disconnected, reopening the page reconnects to the same session (if still available)
- Explicit "Leave session" button available (so members can reorganize into a new session if needed)
- Same member ID rejoining gets the same list (prevents gaming the system by rejoining to create a second list for higher chances)
- Sessions expire after 7 days of inactivity (timer resets on any activity, so active sessions can stay open indefinitely)
- No minimum member count (can be used by a single person for personal decisions)

### Item Comparison
To check if two items are the same (so minor formatting differences don't create false duplicates):
1. Strip all whitespace
2. Strip all special characters
3. Convert to lowercase
4. Compare
