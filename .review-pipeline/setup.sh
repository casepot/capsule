#!/usr/bin/env bash
#
# Setup script for the multi-model review pipeline
# This script installs dependencies and prepares the environment

set -euo pipefail

echo "🚀 Setting up Multi-Model Review Pipeline"
echo "========================================="

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check for Node.js
echo "✓ Checking Node.js..."
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 20+ first."
    exit 1
fi

NODE_VERSION=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 20 ]; then
    echo "❌ Node.js version 20+ required (found v$NODE_VERSION)"
    exit 1
fi
echo "  Found Node.js $(node --version)"

# Install NPM dependencies
echo "✓ Installing NPM dependencies..."
npm install --no-audit --no-fund

# Create workspace directories if they don't exist
echo "✓ Creating workspace directories..."
mkdir -p workspace/context workspace/reports

# Check for required CLI tools
echo "✓ Checking CLI tools..."
bash scripts/auth-check.sh || {
    echo ""
    echo "⚠️  Some CLI tools are not properly configured."
    echo "   Please follow the setup instructions in ../RUNNER_SETUP.md"
    echo ""
}

# Create default config if it doesn't exist
if [ ! -f "config/defaults.json" ]; then
    echo "✓ Creating default configuration..."
    cat > config/defaults.json << 'EOF'
{
  "timeout": 120,
  "models": {
    "claude": "sonnet",
    "codex": "gpt-5",
    "gemini": "gemini-2.5-pro"
  },
  "test_command": "pytest tests/"
}
EOF
fi

# Make scripts executable
echo "✓ Making scripts executable..."
chmod +x scripts/*.sh scripts/*.mjs

# Setup complete message
echo ""
echo "✅ Setup complete!"
echo ""
echo "To run a local review:"
echo "  cd $SCRIPT_DIR"
echo "  bash scripts/review-local.sh"
echo ""
echo "To use in GitHub Actions:"
echo "  1. Copy the workflow template to .github/workflows/"
echo "  2. Ensure your runner has the CLI tools installed"
echo "  3. The workflow will automatically use this package"
echo ""
echo "For more information, see README.md"