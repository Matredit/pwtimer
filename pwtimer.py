#!/usr/bin/env python3
import sys
import tty
import termios
import time

def read_password(prompt="Password: ", track_time=False):
    """
    Reads a password character by character. 
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

def main():
    print("=== Password Typing Trainer ===")
    print("Let's set up the password for this training session.")
    
    # 1. Setup Phase
    while True:
        target_pw, _ = read_password("Enter target password: ", track_time=False)
        confirm_pw, _ = read_password("Confirm password: ", track_time=False)
        
        if target_pw == confirm_pw and len(target_pw) > 0:
            print("Password stored in memory. Let's begin!\n")
            break
        else:
            print("Passwords do not match or are empty. Try again.\n")

    # 2. Training Phase
    print("Type your password and hit Enter. The timer starts on the first keystroke.")
    print("Press Ctrl+C at any time to exit.\n")
    
    attempt_count = 0
    
    try:
        while True:
            attempt_count += 1
            attempt_pw, time_taken = read_password(f"[{attempt_count}] Type it: ", track_time=True)
            
            # Edge case: If user just hits Enter immediately without typing anything
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
