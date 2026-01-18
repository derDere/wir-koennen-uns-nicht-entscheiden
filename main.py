"""
Wir können uns nicht entscheiden - Group Decision Making App
"""

import flet as ft
import base64
import session as sess
import database as db

# Storage keys
STORAGE_PREFIX = "wkune."
STORAGE_MEMBER_ID = f"{STORAGE_PREFIX}member_id"
STORAGE_SESSION_ID = f"{STORAGE_PREFIX}session_id"


def main(page: ft.Page):
    page.title = "Wir können uns nicht entscheiden"
    page.padding = 20
    page.spacing = 10

    # Responsive width
    def get_content_width():
        if page.width and page.width < 600:
            return page.width - 40
        return 500

    # State variables
    current_session_id = None
    current_member_id = None
    selected_result = None
    accepted_items_set = set()

    # Theme handling
    def get_system_theme():
        return ft.ThemeMode.SYSTEM

    page.theme_mode = get_system_theme()

    def toggle_theme(e):
        if page.theme_mode == ft.ThemeMode.LIGHT:
            page.theme_mode = ft.ThemeMode.DARK
        else:
            page.theme_mode = ft.ThemeMode.LIGHT
        theme_btn.icon = ft.Icons.LIGHT_MODE if page.theme_mode == ft.ThemeMode.DARK else ft.Icons.DARK_MODE
        page.update()

    theme_btn = ft.IconButton(
        icon=ft.Icons.DARK_MODE,
        tooltip="Toggle theme",
        on_click=toggle_theme
    )

    # Session code display
    session_code_text = ft.Text("", size=16, weight=ft.FontWeight.BOLD)
    copy_code_btn = ft.IconButton(
        icon=ft.Icons.COPY,
        tooltip="Copy session code",
        visible=False,
        on_click=lambda e: page.set_clipboard(current_session_id) if current_session_id else None
    )

    session_code_row = ft.Row(
        [session_code_text, copy_code_btn],
        alignment=ft.MainAxisAlignment.END,
        spacing=0
    )

    # Header
    header = ft.Row(
        [
            ft.Text("Wir können uns nicht entscheiden", size=20, weight=ft.FontWeight.BOLD, expand=True),
            session_code_row,
            theme_btn
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
    )

    # Main content container
    content = ft.Column(
        [],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=20,
        expand=True
    )

    # Snackbar for messages
    def show_message(msg: str, is_error: bool = False):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(msg),
            bgcolor=ft.Colors.RED_400 if is_error else ft.Colors.GREEN_400
        )
        page.snack_bar.open = True
        page.update()

    # PubSub message handler
    def on_pubsub_message(msg):
        nonlocal selected_result
        if isinstance(msg, dict):
            action = msg.get("action")
            if action == "refresh":
                refresh_ui()
            elif action == "phase_changed":
                refresh_ui()
            elif action == "result_selected":
                selected_result = msg.get("item")
                refresh_ui()
            elif action == "restart_vote_update":
                refresh_ui()
            elif action == "session_reset":
                selected_result = None
                refresh_ui()

    def subscribe_to_session(session_id: str):
        page.pubsub.subscribe_topic(session_id, on_pubsub_message)

    def unsubscribe_from_session():
        if current_session_id:
            page.pubsub.unsubscribe_topic(current_session_id)

    def broadcast_to_session(msg: dict):
        if current_session_id:
            page.pubsub.send_all_on_topic(current_session_id, msg)

    # Landing page
    def show_landing():
        nonlocal current_session_id, current_member_id

        session_input = ft.TextField(
            label="Session Code",
            hint_text="Enter 6-character code",
            max_length=6,
            capitalization=ft.TextCapitalization.CHARACTERS,
            width=200
        )

        def create_session(e):
            nonlocal current_session_id, current_member_id
            member_id = sess.generate_member_id()
            session_id = sess.create_session(member_id)
            if session_id:
                current_session_id = session_id
                current_member_id = member_id
                page.client_storage.set(STORAGE_MEMBER_ID, member_id)
                page.client_storage.set(STORAGE_SESSION_ID, session_id)
                subscribe_to_session(session_id)
                show_session()
            else:
                show_message("Failed to create session", True)

        def join_session(e):
            nonlocal current_session_id, current_member_id
            code = session_input.value.strip().upper()
            if len(code) != 6:
                show_message("Please enter a valid 6-character code", True)
                return

            member_id = page.client_storage.get(STORAGE_MEMBER_ID)
            if not member_id:
                member_id = sess.generate_member_id()
                page.client_storage.set(STORAGE_MEMBER_ID, member_id)

            result = sess.join_session(code, member_id)
            if result["success"]:
                current_session_id = code
                current_member_id = member_id
                page.client_storage.set(STORAGE_SESSION_ID, code)
                subscribe_to_session(code)
                broadcast_to_session({"action": "refresh"})
                show_session()
            else:
                show_message(result.get("error", "Failed to join session"), True)

        content.controls = [
            ft.Container(height=50),
            ft.Text("Group Decision Maker", size=28, weight=ft.FontWeight.BOLD),
            ft.Text("Create a session or join an existing one", size=14, color=ft.Colors.GREY),
            ft.Container(height=30),
            ft.ElevatedButton(
                "Create New Session",
                icon=ft.Icons.ADD,
                on_click=create_session,
                width=250
            ),
            ft.Container(height=20),
            ft.Text("- or -", color=ft.Colors.GREY),
            ft.Container(height=20),
            session_input,
            ft.ElevatedButton(
                "Join Session",
                icon=ft.Icons.LOGIN,
                on_click=join_session,
                width=250
            )
        ]

        session_code_text.value = ""
        copy_code_btn.visible = False
        page.update()

    # Session view
    def show_session():
        nonlocal selected_result

        if not current_session_id or not current_member_id:
            show_landing()
            return

        state = sess.get_session_state(current_session_id, current_member_id)
        if "error" in state:
            page.client_storage.remove(STORAGE_SESSION_ID)
            show_landing()
            return

        # Update session code display
        session_code_text.value = f"Session: {current_session_id}"
        copy_code_btn.visible = True

        # Update member's last seen
        db.update_member_last_seen(current_session_id, current_member_id)

        phase = state["phase"]

        if state["is_observer"]:
            show_observer_view(state)
        elif phase == sess.PHASE_ADDING:
            show_adding_phase(state)
        elif phase == sess.PHASE_ACCEPTING:
            show_accepting_phase(state)
        elif phase == sess.PHASE_RESULT:
            show_result_phase(state)

        page.update()

    def refresh_ui():
        show_session()

    # Observer view
    def show_observer_view(state):
        content.controls = [
            ft.Container(height=30),
            ft.Icon(ft.Icons.VISIBILITY, size=50, color=ft.Colors.GREY),
            ft.Text("Observer Mode", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("You joined while a session was in progress.", size=14),
            ft.Text("You will be able to participate in the next round.", size=14, color=ft.Colors.GREY),
            ft.Container(height=20),
            ft.Text(f"Current phase: {state['phase'].title()}", size=14),
            ft.Container(height=30),
            leave_session_button()
        ]

    # Adding phase
    def show_adding_phase(state):
        nonlocal accepted_items_set
        accepted_items_set = set()  # Reset for new round

        items_list = ft.ListView(spacing=5, height=200, auto_scroll=True)

        def update_items_list():
            items_list.controls = []
            for i, item in enumerate(state["my_items"]):
                items_list.controls.append(
                    ft.Row([
                        ft.Text(item, expand=True),
                        ft.IconButton(
                            icon=ft.Icons.DELETE,
                            icon_color=ft.Colors.RED_400,
                            tooltip="Remove",
                            on_click=lambda e, idx=i: remove_item(idx),
                            disabled=state["is_ready"]
                        )
                    ])
                )
            page.update()

        def remove_item(idx):
            result = sess.remove_item(current_session_id, current_member_id, idx)
            if result["success"]:
                state["my_items"] = result["items"]
                update_items_list()
                broadcast_to_session({"action": "refresh"})
            else:
                show_message(result.get("error", "Failed to remove item"), True)

        item_input = ft.TextField(
            label="Add an option",
            hint_text="Type something and press Enter",
            on_submit=lambda e: add_item(),
            expand=True,
            disabled=state["is_ready"]
        )

        def add_item():
            if not item_input.value.strip():
                return
            result = sess.add_item(current_session_id, current_member_id, item_input.value)
            if result["success"]:
                state["my_items"] = result["items"]
                item_input.value = ""
                update_items_list()
                broadcast_to_session({"action": "refresh"})
            else:
                show_message(result.get("error", "Failed to add item"), True)
            page.update()

        add_btn = ft.IconButton(
            icon=ft.Icons.ADD,
            on_click=lambda e: add_item(),
            disabled=state["is_ready"]
        )

        def toggle_ready(e):
            new_ready = not state["is_ready"]
            result = sess.set_ready(current_session_id, current_member_id, new_ready)
            if result["success"]:
                state["is_ready"] = new_ready
                # Check if phase should advance
                new_phase = sess.check_and_advance_phase(current_session_id)
                if new_phase:
                    broadcast_to_session({"action": "phase_changed", "phase": new_phase})
                else:
                    broadcast_to_session({"action": "refresh"})
                refresh_ui()
            else:
                show_message(result.get("error", "Failed to update ready status"), True)

        ready_btn = ft.ElevatedButton(
            "Ready" if not state["is_ready"] else "Cancel Ready",
            icon=ft.Icons.CHECK if not state["is_ready"] else ft.Icons.CLOSE,
            on_click=toggle_ready,
            bgcolor=ft.Colors.GREEN_400 if not state["is_ready"] else ft.Colors.ORANGE_400
        )

        ready_status = ft.Text(
            f"{state['ready_count']} of {state['total_members']} ready",
            size=14,
            color=ft.Colors.GREY
        )

        update_items_list()

        content.controls = [
            ft.Text("Add Your Options", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("Enter items you'd like to suggest", size=14, color=ft.Colors.GREY),
            ft.Container(height=10),
            ft.Row([item_input, add_btn]),
            ft.Container(
                content=items_list,
                border=ft.border.all(1, ft.Colors.GREY_400),
                border_radius=8,
                padding=10,
                width=get_content_width()
            ),
            ft.Container(height=10),
            ft.Row(
                [ready_btn, ready_status],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                width=get_content_width()
            ),
            ft.Container(height=20),
            leave_session_button()
        ]

    # Accepting phase
    def show_accepting_phase(state):
        nonlocal accepted_items_set

        items_for_acceptance = sess.get_items_for_acceptance(current_session_id, current_member_id)

        # Initialize accepted items from state
        accepted_items_set = set(state["my_accepted_items"])

        checkboxes = []
        checkbox_list = ft.ListView(spacing=5, height=250)

        def on_checkbox_change(e, item):
            if e.control.value:
                accepted_items_set.add(item)
            else:
                accepted_items_set.discard(item)
            save_accepted_items()

        def save_accepted_items():
            sess.set_accepted_items(current_session_id, current_member_id, list(accepted_items_set))

        def select_all(e):
            for cb in checkboxes:
                cb.value = True
            accepted_items_set.clear()
            accepted_items_set.update(items_for_acceptance)
            save_accepted_items()
            page.update()

        def clear_all(e):
            for cb in checkboxes:
                cb.value = False
            accepted_items_set.clear()
            save_accepted_items()
            page.update()

        def toggle_all(e):
            for cb in checkboxes:
                cb.value = not cb.value
            new_set = set(items_for_acceptance) - accepted_items_set
            accepted_items_set.clear()
            accepted_items_set.update(new_set)
            save_accepted_items()
            page.update()

        for item in items_for_acceptance:
            cb = ft.Checkbox(
                label=item,
                value=item in accepted_items_set,
                on_change=lambda e, i=item: on_checkbox_change(e, i),
                disabled=state["is_ready"]
            )
            checkboxes.append(cb)
            checkbox_list.controls.append(cb)

        bulk_buttons = ft.Row([
            ft.TextButton("Select All", on_click=select_all, disabled=state["is_ready"]),
            ft.TextButton("Clear All", on_click=clear_all, disabled=state["is_ready"]),
            ft.TextButton("Toggle All", on_click=toggle_all, disabled=state["is_ready"])
        ], alignment=ft.MainAxisAlignment.CENTER)

        def toggle_ready(e):
            new_ready = not state["is_ready"]
            result = sess.set_ready(current_session_id, current_member_id, new_ready)
            if result["success"]:
                state["is_ready"] = new_ready
                # Check if phase should advance
                new_phase = sess.check_and_advance_phase(current_session_id)
                if new_phase:
                    # Select the result
                    result_item = sess.select_item(current_session_id)
                    broadcast_to_session({"action": "result_selected", "item": result_item})
                else:
                    broadcast_to_session({"action": "refresh"})
                refresh_ui()
            else:
                show_message(result.get("error", "Failed to update ready status"), True)

        ready_btn = ft.ElevatedButton(
            "Ready" if not state["is_ready"] else "Cancel Ready",
            icon=ft.Icons.CHECK if not state["is_ready"] else ft.Icons.CLOSE,
            on_click=toggle_ready,
            bgcolor=ft.Colors.GREEN_400 if not state["is_ready"] else ft.Colors.ORANGE_400
        )

        ready_status = ft.Text(
            f"{state['ready_count']} of {state['total_members']} ready",
            size=14,
            color=ft.Colors.GREY
        )

        no_items_text = ft.Text(
            "No items from other members to accept.",
            color=ft.Colors.GREY,
            visible=len(items_for_acceptance) == 0
        )

        content.controls = [
            ft.Text("Accept Options", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("Select which options you would accept", size=14, color=ft.Colors.GREY),
            ft.Text("(Your own items are automatically accepted)", size=12, color=ft.Colors.GREY),
            ft.Container(height=10),
            bulk_buttons if items_for_acceptance else ft.Container(),
            ft.Container(
                content=checkbox_list if items_for_acceptance else no_items_text,
                border=ft.border.all(1, ft.Colors.GREY_400),
                border_radius=8,
                padding=10,
                width=get_content_width(),
                height=250 if items_for_acceptance else 50
            ),
            ft.Container(height=10),
            ft.Row(
                [ready_btn, ready_status],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                width=get_content_width()
            ),
            ft.Container(height=20),
            leave_session_button()
        ]

    # Result phase
    def show_result_phase(state):
        nonlocal selected_result

        if not selected_result:
            selected_result = sess.select_item(current_session_id)

        result_display = ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.CELEBRATION, size=40, color=ft.Colors.AMBER),
                ft.Text("The result is:", size=16, color=ft.Colors.GREY),
                ft.Text(
                    selected_result or "No items available",
                    size=28,
                    weight=ft.FontWeight.BOLD,
                    text_align=ft.TextAlign.CENTER
                )
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            padding=30,
            border=ft.border.all(2, ft.Colors.AMBER),
            border_radius=16,
            width=get_content_width()
        )

        def do_reroll(e):
            nonlocal selected_result
            selected_result = sess.reroll(current_session_id)
            broadcast_to_session({"action": "result_selected", "item": selected_result})
            refresh_ui()

        def do_roll_next(e):
            nonlocal selected_result
            if selected_result:
                selected_result = sess.roll_next(current_session_id, selected_result)
                broadcast_to_session({"action": "result_selected", "item": selected_result})
                refresh_ui()

        def do_start_fresh(e):
            result = sess.vote_restart(current_session_id, current_member_id)
            if result["all_voted"]:
                nonlocal selected_result
                selected_result = None
                sess.start_fresh(current_session_id)
                broadcast_to_session({"action": "session_reset"})
            else:
                broadcast_to_session({"action": "restart_vote_update"})
            refresh_ui()

        def do_export(e):
            all_items = sess.get_all_items(current_session_id)
            export_content = "\n".join(all_items)
            # Create download using data URL
            b64_content = base64.b64encode(export_content.encode()).decode()
            page.launch_url(f"data:text/plain;base64,{b64_content}")

        # Creator controls
        creator_controls = []
        if state["is_creator"] and state["creator_connected"]:
            creator_controls = [
                ft.Container(height=20),
                ft.Row([
                    ft.ElevatedButton("Re-roll", icon=ft.Icons.REFRESH, on_click=do_reroll),
                    ft.ElevatedButton("Roll Next", icon=ft.Icons.SKIP_NEXT, on_click=do_roll_next),
                ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
                ft.Container(height=10),
                ft.ElevatedButton(
                    "Start Fresh",
                    icon=ft.Icons.RESTART_ALT,
                    on_click=do_start_fresh,
                    bgcolor=ft.Colors.ORANGE_400
                )
            ]

        # Restart vote status
        restart_status = []
        if state["restart_votes"] > 0:
            restart_status = [
                ft.Container(height=10),
                ft.Text(
                    f"Restart votes: {state['restart_votes']} of {state['total_members']}",
                    size=12,
                    color=ft.Colors.ORANGE_400
                )
            ]

        content.controls = [
            ft.Container(height=20),
            result_display,
            *creator_controls,
            *restart_status,
            ft.Container(height=20),
            ft.ElevatedButton(
                "Export All Items",
                icon=ft.Icons.DOWNLOAD,
                on_click=do_export
            ),
            ft.Container(height=20),
            leave_session_button()
        ]

    def leave_session_button():
        def leave(e):
            nonlocal current_session_id, current_member_id, selected_result
            unsubscribe_from_session()
            page.client_storage.remove(STORAGE_SESSION_ID)
            current_session_id = None
            selected_result = None
            show_landing()

        return ft.TextButton(
            "Leave Session",
            icon=ft.Icons.EXIT_TO_APP,
            on_click=leave
        )

    # Check for existing session on load
    def check_existing_session():
        nonlocal current_session_id, current_member_id

        member_id = page.client_storage.get(STORAGE_MEMBER_ID)
        session_id = page.client_storage.get(STORAGE_SESSION_ID)

        if member_id and session_id:
            result = sess.join_session(session_id, member_id)
            if result["success"]:
                current_session_id = session_id
                current_member_id = member_id
                subscribe_to_session(session_id)
                show_session()
                return

        if not member_id:
            member_id = sess.generate_member_id()
            page.client_storage.set(STORAGE_MEMBER_ID, member_id)
            current_member_id = member_id

        show_landing()

    # Cleanup expired sessions periodically
    db.cleanup_expired_sessions()

    # Handle page close
    def on_close(e):
        unsubscribe_from_session()

    page.on_close = on_close

    # Handle window resize
    def on_resize(e):
        page.update()

    page.on_resized = on_resize

    # Build page
    page.add(
        header,
        ft.Divider(),
        content
    )

    # Initialize
    check_existing_session()


# For ASGI deployment
app = ft.app(main, export_asgi_app=True)

if __name__ == "__main__":
    ft.app(main)
