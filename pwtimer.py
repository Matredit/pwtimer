#!/usr/bin/env python3
import sys
import os
import tty
import termios
import time
import json
import argparse

# Default Argon2 settings
DEFAULT_ARGON2_TIME = 3
DEFAULT_ARGON2_MEMORY = 1 << 16 # 64 MB
DEFAULT_ARGON2_PARALLELISM = 4
DEFAULT_ARGON2_TYPE = 'd'

def parse_args():
    parser = argparse.ArgumentParser(description="Password Typing Trainer", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    parser.add_argument("-c", "--no-gui", action="store_true", help="Skip GUI for password setup and use CLI")
    
    # Storage arguments
    parser.add_argument("-s", "--save", nargs='?', const="default_pwtimer.json", metavar="FILE", help="Save the setup password to the specified JSON file")
    parser.add_argument("-r", "--read", nargs='?', const="default_pwtimer.json", metavar="FILE", help="Read target password from the specified JSON file instead of asking")
    parser.add_argument("-n", "--entry-name", default="default", help="Name of the password entry in the JSON file")
    
    # Hashing algorithms and parameters
    parser.add_argument("-P", "--plain", action="store_true", help="Store password in plain text")
    parser.add_argument("--i-understand-risks", action="store_true", help="Guardrail flag when using --plain")
    
    # Argon2 specific parameters
    parser.add_argument("-t", "--time-cost", type=int, default=DEFAULT_ARGON2_TIME, help="Argon2 time cost")
    parser.add_argument("-m", "--memory-cost", type=int, default=DEFAULT_ARGON2_MEMORY, help="Argon2 memory cost")
    parser.add_argument("-p", "--parallelism", type=int, default=DEFAULT_ARGON2_PARALLELISM, help="Argon2 parallelism")
    parser.add_argument("-T", "--hash-type", choices=['id', 'i', 'd'], default=DEFAULT_ARGON2_TYPE, help="Argon2 hash type")
    
    args = parser.parse_args()
    
    # Guardrails validation
    if args.plain and not args.i_understand_risks:
        parser.error("--plain can be used only with --i-understand-risks guardrail.")
        
    if args.save and args.read:
        parser.error("You cannot use --save and --read at the same time.")
    
    return args

def save_to_json(filepath, entry_name, algo, value):
    data = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError:
            pass # File exists but is empty or corrupt; we will overwrite/append

    data[entry_name] = {
        "algo": algo,
        "value": value
    }
    
    # Ensure secure file permissions (600)
    # create file if not exists with 600, then write
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    mode = 0o600
    with os.fdopen(os.open(filepath, flags, mode), 'w') as f:
        json.dump(data, f, indent=4)
    print(f"[+] Saved entry '{entry_name}' to {filepath}")

def load_from_json(filepath, requested_entry_name):
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' does not exist.")
        sys.exit(1)
        
    with open(filepath, 'r') as f:
        data = json.load(f)
        
    if not data:
        print(f"Error: File '{filepath}' is empty.")
        sys.exit(1)
        
    # Auto-select if there is exactly 1 entry and user didn't explicitly change the default
    if len(data) == 1 and requested_entry_name == "default" and "default" not in data:
        entry_name = list(data.keys())[0]
        print(f"[*] Auto-selected single entry: '{entry_name}'")
    else:
        entry_name = requested_entry_name
        
    if entry_name not in data:
        print(f"Error: Entry '{entry_name}' not found in {filepath}.")
        sys.exit(1)
        
    entry = data[entry_name]
    return entry.get("algo"), entry.get("value")

# MARK: Argon2
# to lazy import argon2 module
_argon2_module = None
def get_argon2():
    """Lazily imports and returns the argon2 PasswordHasher. 
    Exits cleanly if missing and plaintext mode wasn't requested.
    """
    global _argon2_module
    if _argon2_module is not None:
        return _argon2_module
    try:
        import argon2
        _argon2_module = argon2
        return _argon2_module
    except ImportError:
        print("\nError: The Argon2 library is not installed.", file=sys.stderr)
        print("Install either python-argon2-cffi via pacman, python3-argon2 via apt/dnf, argon2-cffi via pip.", file=sys.stderr)
        print("Or use -P/--plain to store without hashing.", file=sys.stderr)
        sys.exit(1)

def hash_password(plain_pw, args):
    """Hashes the password based on selected algorithm (or returns plaintext)."""
    if args.plain:
        return "plain", plain_pw

    argon2 = get_argon2()

    type_map = {'id': argon2.Type.ID, 'i': argon2.Type.I, 'd': argon2.Type.D}
    
    ph = argon2.PasswordHasher(
        time_cost=args.time_cost,
        memory_cost=args.memory_cost,
        parallelism=args.parallelism,
        type=type_map[args.hash_type]
    )
    print("[*] Hashing password with Argon2... please wait.")
    return "argon2", ph.hash(plain_pw)

def verify_password(attempt, stored_algo, stored_value):
    """Verifies a password attempt against the stored value."""
    if stored_algo == "plain":
        return attempt == stored_value
        
    elif stored_algo == "argon2":
        argon2 = get_argon2()
            
        ph = argon2.PasswordHasher()
        try:
            ph.verify(stored_value, attempt)
            return True
        except argon2.exceptions.VerifyMismatchError:
            return False
            
    else:
        print(f"Error: Unknown algorithm '{stored_algo}' in save file.")
        sys.exit(1)

# MARK: Input
# --- CLI and GUI Input Functions ---

def read_password(prompt="Password: ", track_time=False):
    """
    Reads a password character by character in CLI. 
    Prints asterisks for visual feedback.
    Optionally tracks time starting from the very first keystroke.
    """
    sys.stdout.write(prompt)
    sys.stdout.flush()
    
    fd = sys.stdin.fileno()
    # Save the current terminal settings so we can restore them later
    old_settings = termios.tcgetattr(fd)
    
    chars = []
    start_time = None
    
    try:
        # Put terminal in raw mode to read keystrokes immediately
        tty.setraw(fd)
        while True:
            char = sys.stdin.read(1)
            
            # Handle Ctrl+C (0x03) and Ctrl+D (0x04)
            if char in ('\x03', '\x04'):
                raise KeyboardInterrupt
                
            # Handle Enter/Return
            if char in ('\r', '\n'):
                sys.stdout.write('\r\n')
                break
                
            # Handle Backspace (usually \x7f in raw terminal mode)
            if char in ('\x7f', '\b'):
                if chars:
                    chars.pop()
                    # Visually erase the last asterisk: move back, print space, move back
                    sys.stdout.write('\b \b')
                    sys.stdout.flush()
                continue
                
            # First character typed? Start the stopwatch
            if track_time and start_time is None:
                start_time = time.time()
                
            chars.append(char)
            sys.stdout.write('*')
            sys.stdout.flush()
            
    finally:
        # ALWAYS restore terminal settings, even if it crashes
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        
    end_time = time.time()
    elapsed = (end_time - start_time) if (track_time and start_time) else 0.0
    
    return "".join(chars), elapsed

def read_password_cli():
    """CLI implementation for initial password setup."""
    print("Let's set up the password for this training session.")
    while True:
        target_pw, _ = read_password("Enter target password: ", track_time=False)
        confirm_pw, _ = read_password("Confirm password: ", track_time=False)
        
        if target_pw == confirm_pw and len(target_pw) > 0:
            print("Password stored in memory.\n")
            return target_pw
        else:
            print("Passwords do not match or are empty. Try again.\n")

# MARK: GUI
def read_password_gui():
    """
    GTK3 implementation for initial password setup.
    Imports gi locally so it won't crash systems lacking dependencies.
    """
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk

    # List to store the result so it can be mutated inside callbacks
    result_pwd = []

    win = Gtk.Window(title="Set Password")
    win.set_position(Gtk.WindowPosition.CENTER)
    win.set_border_width(15)
    # Ensure it floats in tiling WMs like Hyprland
    win.set_resizable(False) # window tiles on hyprland without it
    win.set_type_hint(Gdk.WindowTypeHint.DIALOG)

    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    win.add(vbox)

    # Widgets
    lbl_target = Gtk.Label(label="Enter target password:")
    lbl_target.set_halign(Gtk.Align.START)
    entry_target = Gtk.Entry()
    entry_target.set_visibility(False)
    entry_target.set_width_chars(70)

    lbl_confirm = Gtk.Label(label="Confirm password:")
    lbl_confirm.set_halign(Gtk.Align.START)
    entry_confirm = Gtk.Entry()
    entry_confirm.set_visibility(False)

    chk_show = Gtk.CheckButton(label="Show Password")
    
    lbl_error = Gtk.Label(label="")
    lbl_error.set_use_markup(True)

    btn_submit = Gtk.Button(label="Submit")

    # Add widgets to layout
    vbox.pack_start(lbl_target, False, False, 0)
    vbox.pack_start(entry_target, False, False, 0)
    vbox.pack_start(lbl_confirm, False, False, 0)
    vbox.pack_start(entry_confirm, False, False, 0)
    vbox.pack_start(chk_show, False, False, 0)
    vbox.pack_start(lbl_error, False, False, 0)
    vbox.pack_start(btn_submit, False, False, 0)

    # Callbacks
    def on_submit(widget):
        pw1 = entry_target.get_text()
        pw2 = entry_confirm.get_text()
        if pw1 == pw2 and len(pw1) > 0:
            result_pwd.append(pw1)
            win.destroy() # instead of Gtk.main_quit(). It triggers 'destroy' signal below
        else:
            lbl_error.set_markup("<span foreground='red'>Passwords do not match or are empty!</span>")

    def on_show_toggled(widget):
        is_visible = widget.get_active()
        entry_target.set_visibility(is_visible)
        entry_confirm.set_visibility(is_visible)

    def on_destroy(widget):
        Gtk.main_quit()

    # Signals (Return key in entries, button click, and toggle)
    entry_target.connect("activate", on_submit)
    entry_confirm.connect("activate", on_submit)
    btn_submit.connect("clicked", on_submit)
    chk_show.connect("toggled", on_show_toggled)
    win.connect("destroy", on_destroy)

    # Run GUI
    win.show_all()
    Gtk.main()

    # CRITICAL FIX: Flush the GTK event queue so the compositor 
    # fully removes the window before the blocking CLI loop starts.
    while Gtk.events_pending():
        Gtk.main_iteration()

    # If the user closed the window without submitting, result_pwd will be empty
    return result_pwd[0] if result_pwd else None

# MARK: Main Logic

def get_initial_password(no_gui):
    """
    Orchestrator to get the initial password. 
    Attempts GUI, falls back to CLI if args dictate or if dependencies are missing.
    """
    if no_gui:
        return read_password_cli()
    
    try:
        pwd = read_password_gui()
        if pwd is None:
            # User explicitly clicked the [X] or hit Escape without submitting
            print("GUI closed without saving a password. Exiting.")
            sys.exit(0)
        return pwd
    except Exception as e:
        # Catches ModuleNotFoundError for 'gi', display server issues, etc.
        print(f"[GUI Unavailable: {e}]")
        print("Falling back to CLI mode...\n")
        return read_password_cli()

# --- Main Logic ---

def main():
    args = parse_args()
    print("=== Password Typing Trainer ===")
    
    stored_algo = None
    stored_value = None
    cached_plain_pw = None
    
    # 1. Setup / Load Phase
    if args.read:
        print(f"[*] Reading from {args.read}...")
        stored_algo, stored_value = load_from_json(args.read, args.entry_name)
        
        # If it's plaintext, we can cache it immediately to skip checks later
        if stored_algo == "plain":
            cached_plain_pw = stored_value
            
        print("[+] Password loaded successfully.\n")
        
    else:
        # Ask for password (GUI or CLI)
        initial_plain_pw = get_initial_password(args.no_gui)
        
        if args.save:
            algo, hashed_value = hash_password(initial_plain_pw, args)
            save_to_json(args.save, args.entry_name, algo, hashed_value)
            
            # Since we just created it, we already know what it is! No need to hash later.
            stored_algo = algo
            stored_value = hashed_value
            cached_plain_pw = initial_plain_pw 
        else:
            # Ephemeral mode
            cached_plain_pw = initial_plain_pw

    # 2. Training Phase
    print("Let's begin!")
    print("Type your password and hit Enter. The timer starts on the first keystroke.")
    print("Press Ctrl+C at any time to exit.\n")
    
    attempt_count = 0
    
    try:
        while True:
            attempt_count += 1
            attempt_pw, time_taken = read_password(f"[{attempt_count}] Type it: ", track_time=True)
            
            # Edge case: Empty input
            if not attempt_pw:
                print("  -> Skipped.\n")
                continue

            # Performance optimization: if we already verified the password once, 
            # we just compare raw strings instead of running Argon2 every time.
            if cached_plain_pw is not None:
                is_correct = (attempt_pw == cached_plain_pw)
            else:
                is_correct = verify_password(attempt_pw, stored_algo, stored_value)
                if is_correct:
                    # Cache it for all subsequent attempts
                    cached_plain_pw = attempt_pw

            char_count = len(attempt_pw)
            
            # Calculate metrics
            if time_taken > 0:
                cps = char_count / time_taken
                wpm = cps * 60 / 5  # Standard definition: 1 word = 5 characters
            else:
                cps = wpm = 0.0
                
            # Evaluate
            if is_correct:
                status = "\033[92mCORRECT\033[0m" # Green text
            else:
                status = "\033[91mINCORRECT\033[0m" # Red text
                
            print(f"  -> {status} | Time: {time_taken:.3f}s | Chars: {char_count} | CPS: {cps:.0f} | WPM: {wpm:.0f}\n")
            
    except KeyboardInterrupt:
        print("\n\nExiting.")
        sys.exit(0)

if __name__ == "__main__":
    main()
