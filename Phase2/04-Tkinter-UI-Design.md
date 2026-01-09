# Tkinter UI Design

## UI Layout Wireframe

```
┌────────────────────────────────────────────────────────────────┐
│ File  Tools  Help                                              │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─────────────────────────┬──────────────────────────────┐   │
│  │ Image Prompts (Pending) │ Song Prompts (Pending)       │   │
│  ├─────────────────────────┼──────────────────────────────┤   │
│  │ ID | Created   | Preview│ ID | Created   | Title      │   │
│  │ 200| 2026-01-06| Mount...│ 198| 2026-01-06| Steam...   │   │
│  │ 199| 2026-01-06| Cyber...│                             │   │
│  │ 197| 2026-01-06| Rice ...│                             │   │
│  │                         │                             │   │
│  │   [3 pending]           │   [1 pending]               │   │
│  └─────────────────────────┴──────────────────────────────┘   │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ Prompt Details                                          │  │
│  ├─────────────────────────────────────────────────────────┤  │
│  │ Prompt ID: 200                                          │  │
│  │ Type: image_prompt                                      │  │
│  │ Created: 2026-01-06 21:51:07                           │  │
│  │                                                         │  │
│  │ JSON Prompt:                                            │  │
│  │ {                                                       │  │
│  │   "prompt": "A serene mountain lake at dawn...",       │  │
│  │   "negative_prompt": "Crowds, bright sunlight...",     │  │
│  │   ...                                                   │  │
│  │ }                                                       │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ [Generate Selected] [Generate All] [Refresh] [View Out]│  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
│  Status: Ready | Pending: 4 prompts                           │
└────────────────────────────────────────────────────────────────┘
```

## Component Hierarchy

```
MediaGeneratorApp
├── MenuBar
│   ├── File
│   │   ├── Refresh
│   │   ├── View Output Folder
│   │   └── Exit
│   ├── Tools
│   │   ├── Generate All Pending
│   │   └── Clear Error Messages
│   └── Help
│       └── About
│
├── MainContent (PanedWindow - vertical)
│   ├── TopPanel (Frame - horizontal split)
│   │   ├── ImagePromptsPanel (LabelFrame)
│   │   │   ├── Treeview (id, created, preview)
│   │   │   └── Scrollbar
│   │   │
│   │   └── LyricsPromptsPanel (LabelFrame)
│   │       ├── Treeview (id, created, title)
│   │       └── Scrollbar
│   │
│   └── DetailsPanel (LabelFrame)
│       └── ScrolledText (JSON display)
│
├── ControlPanel (Frame)
│   ├── GenerateButton
│   ├── GenerateAllButton
│   ├── RefreshButton
│   └── ViewOutputButton
│
└── StatusBar (Label)
    └── Status text with counts
```

## Key UI Components

### 1. Image Prompts Treeview

```python
self.image_tree = ttk.Treeview(
    image_frame,
    columns=('id', 'created', 'preview'),
    show='headings',
    selectmode='browse'
)
self.image_tree.heading('id', text='ID')
self.image_tree.heading('created', text='Created')
self.image_tree.heading('preview', text='Preview')
self.image_tree.column('id', width=50)
self.image_tree.column('created', width=150)
self.image_tree.column('preview', width=300)
```

### 2. Lyrics Prompts Treeview

```python
self.lyrics_tree = ttk.Treeview(
    lyrics_frame,
    columns=('id', 'created', 'title'),
    show='headings',
    selectmode='browse'
)
self.lyrics_tree.heading('id', text='ID')
self.lyrics_tree.heading('created', text='Created')
self.lyrics_tree.heading('title', text='Title')
```

### 3. Details Panel

```python
self.details_text = scrolledtext.ScrolledText(
    details_frame,
    wrap=tk.WORD,
    height=10,
    font=('Courier', 10)
)
```

## Event Handlers

### Selection Events

```python
def on_image_select(self, event):
    """Handle image prompt selection"""
    selection = self.image_tree.selection()
    if not selection:
        return

    prompt_id = int(selection[0])
    prompts = self.prompt_repo.get_pending_image_prompts(limit=100)
    selected = next((p for p in prompts if p.id == prompt_id), None)

    if selected:
        self.selected_image_prompt = selected
        self.selected_lyrics_prompt = None  # Clear other selection
        self.lyrics_tree.selection_remove(*self.lyrics_tree.selection())
        self.display_prompt_details(selected)

def on_lyrics_select(self, event):
    """Handle lyrics prompt selection"""
    # Similar implementation for lyrics
```

### Button Actions

```python
def generate_selected(self):
    """Generate media for selected prompt"""
    if self.selected_image_prompt:
        self.generate_image_prompt(self.selected_image_prompt)
    elif self.selected_lyrics_prompt:
        self.generate_lyrics_prompt(self.selected_lyrics_prompt)
    else:
        messagebox.showwarning("No Selection", "Please select a prompt to generate")

def refresh_all_lists(self):
    """Reload both prompt lists from database"""
    self.refresh_image_list()
    self.refresh_lyrics_list()
    self.update_status_bar()

def open_output_folder(self):
    """Open output directory in file explorer"""
    import subprocess
    output_path = self.config['comfyui']['output_directory']
    subprocess.run(['open', output_path])
```

## State Management

```python
class MediaGeneratorApp:
    def __init__(self):
        # Selection state
        self.selected_image_prompt: Optional[PromptRecord] = None
        self.selected_lyrics_prompt: Optional[PromptRecord] = None

        # Generation state
        self.is_generating: bool = False
        self.current_progress: int = 0
        self.total_prompts: int = 0
```

## UI Update Methods

### Populating Lists

```python
def refresh_image_list(self):
    """Load pending image prompts"""
    # Clear existing items
    for item in self.image_tree.get_children():
        self.image_tree.delete(item)

    # Query database
    prompts = self.prompt_repo.get_pending_image_prompts(limit=100)

    # Populate treeview
    for prompt in prompts:
        json_data = prompt.get_json_prompt()
        preview = json_data.get('prompt', '')[:60] + '...' if json_data else '(invalid JSON)'

        self.image_tree.insert(
            '',
            'end',
            iid=str(prompt.id),
            values=(
                prompt.id,
                prompt.created_at.strftime('%Y-%m-%d %H:%M'),
                preview
            )
        )
```

### Displaying Details

```python
def display_prompt_details(self, prompt: PromptRecord):
    """Show formatted JSON prompt in details panel"""
    self.details_text.delete('1.0', tk.END)

    # Header
    self.details_text.insert('end', f"Prompt ID: {prompt.id}\n")
    self.details_text.insert('end', f"Type: {prompt.prompt_type}\n")
    self.details_text.insert('end', f"Created: {prompt.created_at}\n")
    self.details_text.insert('end', f"Original Request: {prompt.prompt_text}\n\n")

    # JSON content
    self.details_text.insert('end', "JSON Prompt:\n")
    self.details_text.insert('end', "─" * 80 + "\n")

    import json
    try:
        json_obj = json.loads(prompt.json_content)
        formatted = json.dumps(json_obj, indent=2)
        self.details_text.insert('end', formatted)
    except:
        self.details_text.insert('end', prompt.json_content or '(no content)')
```

## Styling and Themes

### ttk Styling

```python
style = ttk.Style()
style.theme_use('clam')  # Modern look

# Configure treeview
style.configure('Treeview', rowheight=25)
style.configure('Treeview.Heading', font=('Arial', 10, 'bold'))

# Configure buttons
style.configure('TButton', padding=6)
```

## Next Steps

See [05-ComfyUI-Integration.md](05-ComfyUI-Integration.md) for workflow execution design.
