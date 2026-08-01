#!/usr/bin/env python3
import sys
import tty
import termios
import time

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
    entry_target.set_width_chars(30)

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
            Gtk.main_quit()
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

    # If the user closed the window without submitting, result_pwd will be empty
    return result_pwd[0] if result_pwd else None

def get_initial_password():
    """
    Orchestrator to get the initial password. 
    Attempts GUI, falls back to CLI if args dictate or if dependencies are missing.
    """
    if "-c" in sys.argv or "--no-gui" in sys.argv:
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

def main():
    print("=== Password Typing Trainer ===")
    
    # 1. Setup Phase
    target_pw = get_initial_password()

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

            char_count = len(attempt_pw)
            
            # Calculate metrics
            if time_taken > 0:
                cps = char_count / time_taken
                wpm = cps * 60 / 5  # Standard definition: 1 word = 5 characters
            else:
                cps = wpm = 0.0
                
            # Evaluate
            if attempt_pw == target_pw:
                status = "\033[92mCORRECT\033[0m" # Green text
            else:
                status = "\033[91mINCORRECT\033[0m" # Red text
                
            print(f"  -> {status} | Time: {time_taken:.3f}s | Chars: {char_count} | CPS: {cps:.0f} | WPM: {wpm:.0f}\n")
            
    except KeyboardInterrupt:
        print("\n\nExiting. Target password wiped from memory.")
        sys.exit(0)

if __name__ == "__main__":
    main()
