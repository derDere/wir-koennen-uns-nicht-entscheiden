# Flet Web App Development Guide

This document provides comprehensive guidance for building Flet web applications based on official documentation and best practices.

## Installation

```bash
pip install flet
```

Requires Python 3.9 or above.

## Basic App Structure

```python
import flet as ft

def main(page: ft.Page):
    # Configure page properties
    page.title = "My App"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER

    # Create UI controls
    text = ft.Text("Hello, World!")
    button = ft.ElevatedButton("Click me", on_click=lambda e: print("Clicked!"))

    # Add controls to page
    page.add(
        ft.Column([text, button])
    )

# Launch the application
ft.app(main)
```

## Running Applications

```bash
# Desktop/Native mode
flet run main.py

# Web browser mode (development)
flet run --web main.py

# Specify port
flet run --web --port 8000 main.py
```

## Web Deployment Options

### Static Website (Client-Side)

Python code runs in the browser using Pyodide (CPython compiled to WebAssembly).

**Pros:**
- Zero latency for user interactions
- Cheap/free hosting (GitHub Pages, Cloudflare, Vercel)
- No server required

**Cons:**
- Slower initial load (runtime must download)
- Limited Python package compatibility (pure Python or Emscripten wheels only)
- No threading support
- Code visible to browser inspection

**Build commands:**
```bash
# Recommended (requires Flutter SDK)
flet build web
# Output: ./build/web

# Alternative (no Flutter SDK needed)
flet publish main.py
# Output: ./dist
```

**Important options:**
- `--base-url /subdir/` - for hosting in subdirectories
- `--route-url-strategy hash` - required for GitHub Pages
- `--web-renderer canvaskit` or `html`

### Dynamic Website (Server-Side)

Python code runs on the server with WebSocket communication to clients.

**Pros:**
- Faster initial loading
- Full Python package compatibility
- Better code protection
- Server-side processing capability

**Cons:**
- Non-zero latency for UI updates
- Requires server hosting (paid)

**Production deployment:**
```python
# In main.py
import flet as ft

def main(page: ft.Page):
    # Your app code
    pass

# For ASGI server export
app = ft.app(main, export_asgi_app=True)
```

Run with ASGI servers:
```bash
# Uvicorn (default)
uvicorn main:app --host 0.0.0.0 --port 8000

# Hypercorn
hypercorn main:app --bind 0.0.0.0:8000

# Gunicorn with Uvicorn workers
gunicorn --bind 0.0.0.0:8000 -k uvicorn.workers.UvicornWorker main:app
```

**Environment variables:**
- `FLET_SERVER_PORT` - Server port
- `FLET_SERVER_IP` - Bind address
- `FLET_SESSION_TIMEOUT` - Session timeout
- `FLET_FORCE_WEB_SERVER=true` - Force web server mode

## Common Controls

### Layout Controls
- `ft.Column` - Vertical layout
- `ft.Row` - Horizontal layout
- `ft.Container` - Single child with styling (borders, padding, etc.)
- `ft.ListView` - Scrollable list of controls

### Input Controls
- `ft.TextField` - Text input
- `ft.Checkbox` - Boolean checkbox
- `ft.ElevatedButton` - Primary button
- `ft.IconButton` - Icon-only button
- `ft.FloatingActionButton` - FAB

### Display Controls
- `ft.Text` - Text display
- `ft.Icon` - Icon display
- `ft.AlertDialog` - Modal dialog

## Event Handling

```python
def button_clicked(e):
    print("Button clicked!")
    e.control.text = "Clicked"
    e.control.update()

button = ft.ElevatedButton("Click me", on_click=button_clicked)
```

Common events: `on_click`, `on_change`, `on_submit`

## Storage APIs

### Client Storage (Persistent - Browser LocalStorage)

Persists across sessions. On web, uses browser LocalStorage.

```python
# Write
page.client_storage.set("my_app.user_id", "abc123")
page.client_storage.set("my_app.settings", {"theme": "dark"})

# Read
user_id = page.client_storage.get("my_app.user_id")

# Check existence
if page.client_storage.contains_key("my_app.user_id"):
    # key exists

# Get all keys with prefix
keys = page.client_storage.get_keys("my_app.")

# Remove
page.client_storage.remove("my_app.user_id")

# Clear ALL (dangerous - affects all Flet apps!)
page.client_storage.clear()
```

**Important:** Use unique prefixes like `{company}.{product}.` to avoid conflicts with other Flet apps.

### Session Storage (Server-Side, Transient)

Only available in dynamic (server-side) apps. Data lost on server restart.

```python
# Write
page.session.set("user_name", "John")

# Read
name = page.session.get("user_name")
```

## PubSub (Real-Time Communication)

Enables messaging between multiple app sessions (users).

### Basic Usage - Broadcast to All

```python
def main(page: ft.Page):
    messages = ft.ListView()

    def on_message(msg):
        messages.controls.append(ft.Text(msg))
        page.update()

    # Subscribe when page loads
    page.pubsub.subscribe(on_message)

    def send_click(e):
        page.pubsub.send_all(f"User says: {message.value}")
        message.value = ""
        page.update()

    message = ft.TextField(hint_text="Type a message")
    send_btn = ft.ElevatedButton("Send", on_click=send_click)

    page.add(messages, ft.Row([message, send_btn]))

ft.app(main)
```

### Topic-Based Subscriptions

```python
# Subscribe to specific topic (e.g., a session/room)
page.pubsub.subscribe_topic("session_ABC123", on_session_message)

# Send to topic only
page.pubsub.send_all_on_topic("session_ABC123", message_data)

# Unsubscribe from topic
page.pubsub.unsubscribe_topic("session_ABC123")

# Unsubscribe from all
page.pubsub.unsubscribe_all()
```

### Cleanup on Page Close

```python
def main(page: ft.Page):
    def on_close(e):
        page.pubsub.unsubscribe_all()

    page.on_close = on_close
    page.pubsub.subscribe(on_message)
```

## Reusable Components Pattern

Create custom controls by inheriting from Flet controls:

```python
class TaskItem(ft.Row):
    def __init__(self, task_name, on_delete):
        super().__init__()
        self.task_name = task_name
        self.on_delete = on_delete

        self.controls = [
            ft.Checkbox(label=task_name),
            ft.IconButton(
                icon=ft.Icons.DELETE,
                on_click=self.delete_clicked
            )
        ]

    def delete_clicked(self, e):
        self.on_delete(self)
```

Override `before_update()` to sync UI state:

```python
class MyControl(ft.Column):
    def before_update(self):
        # Called before every update
        self.some_control.visible = self.some_condition
```

## Dialogs

```python
def main(page: ft.Page):
    def close_dialog(e):
        dialog.open = False
        page.update()

    def open_dialog(e):
        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    dialog = ft.AlertDialog(
        title=ft.Text("Confirm"),
        content=ft.Text("Are you sure?"),
        actions=[
            ft.TextButton("Cancel", on_click=close_dialog),
            ft.TextButton("OK", on_click=close_dialog),
        ],
    )

    page.add(ft.ElevatedButton("Show Dialog", on_click=open_dialog))
```

## Page Configuration

```python
def main(page: ft.Page):
    page.title = "My App"
    page.theme_mode = ft.ThemeMode.LIGHT  # or DARK, SYSTEM
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.padding = 20
    page.spacing = 10
    page.scroll = ft.ScrollMode.AUTO  # Enable page scrolling
```

## Async Support

For web apps, async handlers are recommended:

```python
import flet as ft
import asyncio

async def main(page: ft.Page):
    async def button_clicked(e):
        await asyncio.sleep(1)  # Async operation
        text.value = "Done!"
        await page.update_async()

    text = ft.Text("Click the button")
    button = ft.ElevatedButton("Click", on_click=button_clicked)

    await page.add_async(text, button)

ft.app(main)
```

## Recommended Hosting Providers

For dynamic Flet apps (server-side):
- **Fly.io** - Good WebSocket support, multiple data centers, generous free tier
- **Replit** - Online IDE + hosting, free tier available
- **Self-hosted** - Behind nginx/Apache reverse proxy

For static Flet apps:
- **GitHub Pages** - Free, use `--route-url-strategy hash`
- **Cloudflare Pages** - Free, SPA support
- **Vercel** - Free tier available

## Sources

- [Flet Official Documentation](https://flet.dev/docs/)
- [Flet Tutorials](https://flet.dev/docs/tutorials/)
- [PubSub Guide](https://flet.dev/docs/cookbook/pub-sub/)
- [Client Storage](https://flet.dev/docs/cookbook/client-storage/)
- [Session Storage](https://flet.dev/docs/cookbook/session-storage/)
- [Publishing to Web](https://flet.dev/docs/publish/web/)
- [Dynamic Website Hosting](https://flet.dev/docs/publish/web/dynamic-website/)
- [Static Website Publishing](https://flet.dev/docs/publish/web/static-website/)
- [Chat Tutorial](https://flet.dev/docs/tutorials/python-chat/)
- [To-Do Tutorial](https://flet.dev/docs/tutorials/python-todo/)
