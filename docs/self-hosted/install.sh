#!/bin/bash

# Byaan Self-Hosted Installer
# Usage: curl -fsSL https://get.byaan.ai/install | bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

BASE_URL="https://downloads.byaan.ai/docker"

echo ""
echo -e "${BOLD}${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${BLUE}║       Byaan Self-Hosted Installer      ║${NC}"
echo -e "${BOLD}${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""

# Create directory
INSTALL_DIR="${1:-byaan}"
echo -e "${BLUE}Creating directory: ${INSTALL_DIR}${NC}"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Download files
echo -e "${BLUE}Downloading files...${NC}"

curl -fsSL "$BASE_URL/start.sh" -o start.sh
echo -e "  ${GREEN}✓${NC} start.sh"

if [ -f .env ]; then
    echo -e "  ${YELLOW}⚠${NC} .env (already exists, skipping)"
else
    curl -fsSL "$BASE_URL/env.example" -o .env
    echo -e "  ${GREEN}✓${NC} .env"

    # Generate APP_SECRET
    APP_SECRET=$(openssl rand -hex 32 2>/dev/null || head -c 64 /dev/urandom | od -An -tx1 | tr -d ' \n' | head -c 64)

    # Update .env with generated secret
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/^APP_SECRET=$/APP_SECRET=$APP_SECRET/" .env
    else
        sed -i "s/^APP_SECRET=$/APP_SECRET=$APP_SECRET/" .env
    fi
fi

curl -fsSL "$BASE_URL/README.md" -o README.md
echo -e "  ${GREEN}✓${NC} README.md"

chmod +x start.sh

echo ""
echo -e "${GREEN}${BOLD}Installation complete!${NC}"
echo ""
echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}Next steps:${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BOLD}1.${NC} Edit the configuration file:"
echo ""
echo -e "   ${BLUE}cd $INSTALL_DIR${NC}"
echo -e "   ${BLUE}nano .env${NC}"
echo ""
echo -e "   Update these required values:"
echo -e "   • ${BOLD}MASTER_USER_EMAIL${NC}    - Your admin email"
echo -e "   • ${BOLD}MASTER_USER_PASSWORD${NC} - Your admin password (min 8 chars)"
echo -e "   • ${BOLD}ORG_NAME${NC}             - Your organization name"
echo ""
echo -e "   Optional (for HTTPS with your domain):"
echo -e "   • ${BOLD}DOMAIN${NC}               - e.g., app.yourcompany.com"
echo -e "   • ${BOLD}ACME_EMAIL${NC}           - For SSL certificate notifications"
echo ""
echo -e "${BOLD}2.${NC} Start Byaan (also enables auto-updates at 12 AM daily):"
echo ""
echo -e "   ${BLUE}./start.sh${NC}"
echo ""
echo -e "   This will:"
echo -e "   • Start Byaan on ${BOLD}http://localhost:8080${NC}"
echo -e "   • Set up automatic updates (runs daily at 12 AM)"
echo -e "   • Enable zero-downtime updates with blue-green deployment"
echo ""
echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "See ${BOLD}README.md${NC} for full documentation."
echo ""
