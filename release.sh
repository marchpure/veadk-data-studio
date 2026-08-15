#!/bin/bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Docker Hub organization
DOCKER_ORG="byaan"

# Target platforms for multi-arch builds
PLATFORMS="linux/amd64,linux/arm64"

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_FILE="$SCRIPT_DIR/VERSION"

# Print colored message
print_info() { echo -e "${BLUE}$1${NC}"; }
print_success() { echo -e "${GREEN}$1${NC}"; }
print_warning() { echo -e "${YELLOW}$1${NC}"; }
print_error() { echo -e "${RED}$1${NC}"; }

# Check if Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        print_error "Error: Docker is not running"
        exit 1
    fi
}

# Check if logged into Docker Hub
check_docker_login() {
    if ! docker info 2>/dev/null | grep -q "Username"; then
        print_warning "Warning: You may not be logged into Docker Hub"
        print_info "Run 'docker login' if push fails"
    fi
}

# Setup Docker Buildx for multi-architecture builds
setup_buildx() {
    print_info "Setting up Docker Buildx for multi-architecture builds..."

    # Check if buildx is available
    if ! docker buildx version > /dev/null 2>&1; then
        print_error "Error: Docker Buildx is not available. Please update Docker."
        exit 1
    fi

    # Create or use existing builder
    BUILDER_NAME="byaan-multiarch"
    if ! docker buildx inspect "$BUILDER_NAME" > /dev/null 2>&1; then
        print_info "Creating new buildx builder: $BUILDER_NAME"
        docker buildx create --name "$BUILDER_NAME" --driver docker-container --bootstrap
    fi

    docker buildx use "$BUILDER_NAME"
    print_success "Buildx ready with builder: $BUILDER_NAME"
}

# Read current version
read_version() {
    if [[ ! -f "$VERSION_FILE" ]]; then
        print_error "Error: VERSION file not found"
        exit 1
    fi
    cat "$VERSION_FILE" | tr -d '[:space:]'
}

# Bump version based on type
bump_version() {
    local version=$1
    local bump_type=$2

    local major minor patch
    IFS='.' read -r major minor patch <<< "$version"

    case $bump_type in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch)
            patch=$((patch + 1))
            ;;
        *)
            print_error "Error: Invalid bump type '$bump_type'. Use: major, minor, or patch"
            exit 1
            ;;
    esac

    echo "$major.$minor.$patch"
}

# Build and push multi-arch Docker image using buildx
build_and_push_image() {
    local name=$1
    local version=$2
    local dockerfile=$3

    echo ""
    print_info "Building and pushing $DOCKER_ORG/$name:v$version for platforms: $PLATFORMS"
    echo ""

    if docker buildx build \
        --platform "$PLATFORMS" \
        --tag "$DOCKER_ORG/$name:v$version" \
        --tag "$DOCKER_ORG/$name:latest" \
        --file "$dockerfile" \
        --push \
        "$SCRIPT_DIR"; then
        echo ""
        print_success "Built and pushed $DOCKER_ORG/$name:v$version (multi-arch)"
    else
        echo ""
        print_error "Error: Failed to build $name"
        exit 1
    fi
}

# Build only (no push) for local testing
build_local_image() {
    local name=$1
    local version=$2
    local dockerfile=$3

    echo ""
    print_info "Building $DOCKER_ORG/$name:v$version locally..."
    echo ""

    if docker build \
        --tag "$DOCKER_ORG/$name:v$version" \
        --tag "$DOCKER_ORG/$name:latest" \
        --file "$dockerfile" \
        "$SCRIPT_DIR"; then
        echo ""
        print_success "Built $DOCKER_ORG/$name:v$version locally"
    else
        echo ""
        print_error "Error: Failed to build $name"
        exit 1
    fi
}

# Update VERSION file
update_version() {
    local new_version=$1
    echo "$new_version" > "$VERSION_FILE"
}

# Release: bump version, build, and push
do_release() {
    local bump_type="${1:-patch}"

    # Pre-flight checks
    check_docker
    check_docker_login
    setup_buildx

    # Get versions
    local current_version
    current_version=$(read_version)
    local new_version
    new_version=$(bump_version "$current_version" "$bump_type")

    # Show what will happen
    echo ""
    print_info "Current version: $current_version"
    print_warning "New version:     $new_version"
    echo ""
    echo "This will build and push multi-arch images:"
    echo "  - $DOCKER_ORG/server:v$new_version (linux/amd64, linux/arm64)"
    echo "  - $DOCKER_ORG/server:latest"
    echo "  - $DOCKER_ORG/client:v$new_version (linux/amd64, linux/arm64)"
    echo "  - $DOCKER_ORG/client:latest"
    echo ""

    # Confirm
    read -p "Continue? [y/N] " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_warning "Aborted"
        exit 0
    fi

    # Build and push images (buildx does both in one step for multi-arch)
    build_and_push_image "server" "$new_version" "$SCRIPT_DIR/server/Dockerfile"
    build_and_push_image "client" "$new_version" "$SCRIPT_DIR/client/Dockerfile"
    echo ""

    # Update VERSION file
    update_version "$new_version"

    # Success message
    print_success "Release v$new_version complete!"
    echo ""
    print_info "Multi-arch images are now available for:"
    echo "  - linux/amd64 (x86_64 servers, Intel Macs)"
    echo "  - linux/arm64 (AWS Graviton, M-series Macs, Raspberry Pi)"
    echo ""
    print_info "Next steps:"
    echo "  git add VERSION"
    echo "  git commit -m \"Release v$new_version\""
    echo "  git push"
    echo ""
}

# Build: rebuild current version and push (no version bump)
do_build() {
    # Pre-flight checks
    check_docker
    check_docker_login
    setup_buildx

    local version
    version=$(read_version)

    # Show what will happen
    echo ""
    print_info "Current version: $version"
    echo ""
    echo "This will rebuild and push multi-arch images (no version bump):"
    echo "  - $DOCKER_ORG/server:v$version (linux/amd64, linux/arm64)"
    echo "  - $DOCKER_ORG/server:latest"
    echo "  - $DOCKER_ORG/client:v$version (linux/amd64, linux/arm64)"
    echo "  - $DOCKER_ORG/client:latest"
    echo ""

    # Confirm
    read -p "Continue? [y/N] " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_warning "Aborted"
        exit 0
    fi

    # Build and push images
    build_and_push_image "server" "$version" "$SCRIPT_DIR/server/Dockerfile"
    build_and_push_image "client" "$version" "$SCRIPT_DIR/client/Dockerfile"
    echo ""

    print_success "Rebuild of v$version complete!"
    echo ""
}

# Push a specific version
do_push() {
    local version="$1"

    if [[ -z "$version" ]]; then
        print_error "Error: Version required. Usage: $0 push <version>"
        print_info "Example: $0 push 1.0.2"
        exit 1
    fi

    # Remove 'v' prefix if provided
    version="${version#v}"

    # Pre-flight checks
    check_docker
    check_docker_login
    setup_buildx

    # Show what will happen
    echo ""
    print_info "Version to push: $version"
    echo ""
    echo "This will build and push multi-arch images:"
    echo "  - $DOCKER_ORG/server:v$version (linux/amd64, linux/arm64)"
    echo "  - $DOCKER_ORG/server:latest"
    echo "  - $DOCKER_ORG/client:v$version (linux/amd64, linux/arm64)"
    echo "  - $DOCKER_ORG/client:latest"
    echo ""

    # Confirm
    read -p "Continue? [y/N] " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_warning "Aborted"
        exit 0
    fi

    # Build and push images
    build_and_push_image "server" "$version" "$SCRIPT_DIR/server/Dockerfile"
    build_and_push_image "client" "$version" "$SCRIPT_DIR/client/Dockerfile"
    echo ""

    # Update VERSION file
    update_version "$version"

    print_success "Push of v$version complete!"
    echo ""
    print_info "VERSION file updated to $version"
    echo ""
}

# Build locally (no push) for testing
do_local() {
    check_docker

    local version
    version=$(read_version)

    # Show what will happen
    echo ""
    print_info "Building locally for testing (no push)..."
    print_info "Version: $version"
    echo ""

    # Build images locally
    build_local_image "server" "$version" "$SCRIPT_DIR/server/Dockerfile"
    build_local_image "client" "$version" "$SCRIPT_DIR/client/Dockerfile"
    echo ""

    print_success "Local build complete!"
    echo ""
    print_info "Images available locally:"
    echo "  - $DOCKER_ORG/server:v$version"
    echo "  - $DOCKER_ORG/server:latest"
    echo "  - $DOCKER_ORG/client:v$version"
    echo "  - $DOCKER_ORG/client:latest"
    echo ""
}

# Show usage
show_help() {
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  patch         Bump patch version and push (1.0.0 -> 1.0.1)"
    echo "  minor         Bump minor version and push (1.0.0 -> 1.1.0)"
    echo "  major         Bump major version and push (1.0.0 -> 2.0.0)"
    echo "  build         Rebuild current version and push (no version bump)"
    echo "  push <ver>    Build and push a specific version (e.g., push 1.0.2)"
    echo "  local         Build locally for testing (no push)"
    echo ""
    echo "Examples:"
    echo "  $0 patch              # Bump 1.0.1 -> 1.0.2 and push"
    echo "  $0 build              # Rebuild and push current version"
    echo "  $0 push 1.0.2         # Build and push v1.0.2"
    echo "  $0 local              # Build locally for testing"
    echo ""
    echo "Multi-arch Support:"
    echo "  All builds target both linux/amd64 and linux/arm64 platforms."
    echo "  This supports x86_64 servers, Intel Macs, M-series Macs, and ARM servers."
    echo ""
    echo "Prerequisites:"
    echo "  - Docker with Buildx support (Docker Desktop or Docker 19.03+)"
    echo "  - Logged into Docker Hub (docker login)"
    exit 0
}

# Main entry point
case "${1:-}" in
    -h|--help|help)
        show_help
        ;;
    patch|minor|major)
        do_release "$1"
        ;;
    build)
        do_build
        ;;
    push)
        do_push "$2"
        ;;
    local)
        do_local
        ;;
    "")
        # Default to patch release
        do_release "patch"
        ;;
    *)
        print_error "Unknown command: $1"
        echo ""
        show_help
        ;;
esac
