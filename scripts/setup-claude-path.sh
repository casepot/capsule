#!/usr/bin/env bash
# Helper script to set up Claude Code PATH properly

set -euo pipefail

grn() { printf "\033[32m%s\033[0m\n" "$*"; }
ylw() { printf "\033[33m%s\033[0m\n" "$*"; }
red() { printf "\033[31m%s\033[0m\n" "$*" >&2; }

echo "Claude Code PATH Setup Helper"
echo "=============================="

# Check if Claude is installed at the expected location
CLAUDE_PATH="$HOME/.claude/local/claude"

if [ ! -f "$CLAUDE_PATH" ]; then
  red "Claude Code not found at $CLAUDE_PATH"
  echo "Please install Claude Code first:"
  echo "  Visit: https://docs.anthropic.com/en/docs/claude-code/setup"
  exit 1
fi

if [ ! -x "$CLAUDE_PATH" ]; then
  ylw "Making Claude executable..."
  chmod +x "$CLAUDE_PATH"
fi

grn "✓ Claude Code found at: $CLAUDE_PATH"

# Detect shell
SHELL_NAME=$(basename "$SHELL")
echo "Detected shell: $SHELL_NAME"

# Determine shell config file
case "$SHELL_NAME" in
  bash)
    RC_FILE="$HOME/.bashrc"
    PROFILE_FILE="$HOME/.bash_profile"
    ;;
  zsh)
    RC_FILE="$HOME/.zshrc"
    PROFILE_FILE="$HOME/.zprofile"
    ;;
  *)
    RC_FILE="$HOME/.profile"
    PROFILE_FILE="$HOME/.profile"
    ;;
esac

# Function to add Claude to a config file
add_claude_to_file() {
  local file="$1"
  
  if [ ! -f "$file" ]; then
    touch "$file"
  fi
  
  # Check if Claude is already configured
  if grep -q "claude" "$file" 2>/dev/null; then
    ylw "Claude configuration already exists in $file"
    return 0
  fi
  
  echo "" >> "$file"
  echo "# Claude Code CLI" >> "$file"
  echo "export PATH=\"\$HOME/.claude/local:\$PATH\"" >> "$file"
  echo "alias claude=\"\$HOME/.claude/local/claude\"" >> "$file"
  
  grn "✓ Added Claude Code to $file"
}

# Add to appropriate config files
echo ""
echo "Adding Claude to shell configuration..."

add_claude_to_file "$RC_FILE"
if [ "$RC_FILE" != "$PROFILE_FILE" ] && [ -f "$PROFILE_FILE" ]; then
  add_claude_to_file "$PROFILE_FILE"
fi

# Test if Claude works now
echo ""
echo "Testing Claude installation..."
if "$CLAUDE_PATH" --version >/dev/null 2>&1; then
  grn "✓ Claude Code is working!"
else
  red "⚠ Claude Code found but not working properly"
  echo "Please try running: $CLAUDE_PATH --version"
  exit 1
fi

echo ""
grn "Setup complete!"
echo ""
echo "To apply changes to your current shell, run:"
ylw "  source $RC_FILE"
echo ""
echo "Or open a new terminal window."
echo ""
echo "Then verify with:"
ylw "  claude --version"