#!/usr/bin/env python3
"""XO (tic-tac-toe) bot for a GitHub profile README.

Reads a move from an issue title, applies it, replies with a minimax move,
rewrites the board block in README.md and saves state to xo/state.json.

Issue title formats:
    xo|move|<0-8>
    xo|reset
"""

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "xo" / "state.json"
README_PATH = ROOT / "README.md"
MESSAGE_PATH = ROOT / "xo" / "last_message.txt"

START = "<!-- XO:START -->"
END = "<!-- XO:END -->"

EMPTY = " "
HUMAN = "X"
BOT = "O"

CELL_EMPTY = "⬜"
CELL_HUMAN = "❌"
CELL_BOT = "⭕"

LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),   # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),   # columns
    (0, 4, 8), (2, 4, 6),              # diagonals
]

REPO = os.environ.get("GITHUB_REPOSITORY", "Arnoldaditya17/Arnoldaditya17")
NEW_ISSUE = f"https://github.com/{REPO}/issues/new"


# ---------------------------------------------------------------- game logic

def winner(board):
    """Return 'X', 'O', or None."""
    for a, b, c in LINES:
        if board[a] != EMPTY and board[a] == board[b] == board[c]:
            return board[a]
    return None


def winning_line(board):
    for line in LINES:
        a, b, c = line
        if board[a] != EMPTY and board[a] == board[b] == board[c]:
            return line
    return None


def is_full(board):
    return EMPTY not in board


def place(board, index, mark):
    return board[:index] + mark + board[index + 1:]


def minimax(board, player, depth=0):
    """Return (score, best_index) from BOT's perspective.

    Depth is subtracted from winning scores so the bot prefers the fastest
    win, and added to losing scores so it prefers the slowest loss.
    """
    won = winner(board)
    if won == BOT:
        return 10 - depth, None
    if won == HUMAN:
        return depth - 10, None
    if is_full(board):
        return 0, None

    maximizing = player == BOT
    best_score = -999 if maximizing else 999
    best_index = None

    for i in range(9):
        if board[i] != EMPTY:
            continue
        score, _ = minimax(place(board, i, player),
                           HUMAN if maximizing else BOT,
                           depth + 1)
        if maximizing and score > best_score:
            best_score, best_index = score, i
        elif not maximizing and score < best_score:
            best_score, best_index = score, i

    return best_score, best_index


def best_bot_move(board):
    return minimax(board, BOT)[1]


# ------------------------------------------------------------------- state

def fresh_state(previous=None):
    scores = {"human": 0, "bot": 0, "draws": 0}
    if previous:
        scores = previous.get("scores", scores)
    return {"board": EMPTY * 9, "status": "playing", "scores": scores,
            "last_player": previous.get("last_player") if previous else None}


def load_state():
    if STATE_PATH.exists():
        try:
            data = json.loads(STATE_PATH.read_text())
            if len(data.get("board", "")) == 9:
                data.setdefault("status", "playing")
                data.setdefault("scores", {"human": 0, "bot": 0, "draws": 0})
                data.setdefault("last_player", None)
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return fresh_state()


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")


# ------------------------------------------------------------------ render

def cell_markup(state, index):
    mark = state["board"][index]
    if mark == HUMAN:
        return CELL_HUMAN
    if mark == BOT:
        return CELL_BOT
    title = f"xo%7Cmove%7C{index}"
    body = ("Just+click+**Create**+below+-+no+need+to+type+anything."
            "+The+bot+replies+in+about+20+seconds.")
    url = f"{NEW_ISSUE}?title={title}&body={body}"
    return f'<a href="{url}" title="Play square {index + 1}">{CELL_EMPTY}</a>'


def status_line(state):
    scores = state["scores"]
    tally = (f"You <b>{scores['human']}</b> &nbsp;·&nbsp; "
             f"Bot <b>{scores['bot']}</b> &nbsp;·&nbsp; "
             f"Draws <b>{scores['draws']}</b>")

    if state["status"] == "human_win":
        headline = "🎉 <b>You win!</b> Click any ⬜ to start a new game."
    elif state["status"] == "bot_win":
        headline = "🤖 <b>Bot wins.</b> Click any ⬜ to start a new game."
    elif state["status"] == "draw":
        headline = "🤝 <b>Draw.</b> Click any ⬜ to start a new game."
    else:
        headline = "Your turn — you are ❌, click any ⬜ to move."

    return headline, tally


def render_block(state):
    reset_url = f"{NEW_ISSUE}?title=xo%7Creset&body=Just+click+Create+below."
    headline, tally = status_line(state)

    rows = []
    for r in range(3):
        cells = "".join(
            f'<td align="center" width="60" height="60">'
            f'{cell_markup(state, r * 3 + c)}</td>'
            for c in range(3)
        )
        rows.append(f"<tr>{cells}</tr>")

    return "\n".join([
        START,
        "",
        '<div align="center">',
        "",
        f"{headline}",
        "",
        "<table>",
        *rows,
        "</table>",
        "",
        tally,
        "",
        f'<a href="{reset_url}"><img '
        'src="https://img.shields.io/badge/%F0%9F%94%84_Reset_Board-64748B?style=for-the-badge" '
        'alt="Reset board" /></a>',
        "",
        "<sub>Clicking a square opens a pre-filled issue — just press "
        "<b>Create</b>. The board updates automatically.</sub>",
        "",
        "</div>",
        "",
        END,
    ])


def update_readme(state):
    text = README_PATH.read_text()
    if START not in text or END not in text:
        raise SystemExit(f"README.md is missing the {START} / {END} markers")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    README_PATH.write_text(head + render_block(state) + tail)


# -------------------------------------------------------------------- moves

def apply_turn(state, index, player_login):
    """Mutate and return (state, message_for_issue_comment)."""
    # Auto-reset: a finished game clears itself on the next click.
    if state["status"] != "playing":
        state = fresh_state(state)

    if not 0 <= index <= 8:
        return state, "That square doesn't exist — squares are numbered 0-8."

    if state["board"][index] != EMPTY:
        return state, "That square is already taken. Pick an empty ⬜."

    state["board"] = place(state["board"], index, HUMAN)
    state["last_player"] = player_login

    if winner(state["board"]) == HUMAN:
        state["status"] = "human_win"
        state["scores"]["human"] += 1
        return state, f"🎉 @{player_login} wins! The board resets on the next click."

    if is_full(state["board"]):
        state["status"] = "draw"
        state["scores"]["draws"] += 1
        return state, "🤝 Draw! The board resets on the next click."

    bot_index = best_bot_move(state["board"])
    state["board"] = place(state["board"], bot_index, BOT)

    if winner(state["board"]) == BOT:
        state["status"] = "bot_win"
        state["scores"]["bot"] += 1
        return state, f"🤖 Bot takes square {bot_index + 1} and wins. Board resets on the next click."

    if is_full(state["board"]):
        state["status"] = "draw"
        state["scores"]["draws"] += 1
        return state, "🤝 Draw! The board resets on the next click."

    return state, f"Bot played square {bot_index + 1}. Your turn — back to the README."


def main():
    title = os.environ.get("MOVE_TITLE", "").strip()
    player = os.environ.get("PLAYER", "player")

    parts = [p.strip() for p in title.split("|")]
    if not parts or parts[0].lower() != "xo":
        print("Not an XO issue; nothing to do.")
        return 0

    state = load_state()

    if len(parts) >= 2 and parts[1].lower() == "reset":
        state = fresh_state(state)
        message = "Board reset. Your move!"
    elif len(parts) >= 3 and parts[1].lower() == "move":
        try:
            index = int(parts[2])
        except ValueError:
            print("Unparseable square number.")
            return 0
        state, message = apply_turn(state, index, player)
    else:
        print("Unrecognised XO command.")
        return 0

    save_state(state)
    update_readme(state)
    MESSAGE_PATH.write_text(message + "\n")
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
