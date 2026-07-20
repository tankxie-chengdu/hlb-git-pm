#!/bin/bash

# Clone repositories from GitHub to local workspace
# Usage: ./clone-repos.sh [config-file] [workspace-path]

set -e

# Default values
CONFIG_FILE="${1:-config.toml}"
WORKSPACE="${2:-.data/repos}"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    local missing=0

    if ! command -v git &> /dev/null; then
        log_error "git 未安装"
        missing=1
    fi

    if ! command -v python3 &> /dev/null; then
        log_error "python3 未安装"
        missing=1
    fi

    if [ ! -f "$CONFIG_FILE" ]; then
        log_error "配置文件不存在: $CONFIG_FILE"
        missing=1
    fi

    if [ $missing -eq 1 ]; then
        exit 1
    fi
}

# Extract GitHub config from TOML
extract_github_config() {
    python3 << 'PYTHON_SCRIPT'
import sys
try:
    import tomllib
except ImportError:
    import tomli as tomllib

config_file = sys.argv[1]
with open(config_file, "rb") as f:
    config = tomllib.load(f)

github_cfg = config.get("github")
if not github_cfg:
    print("ERROR: No github config found")
    sys.exit(1)

print(f"ORG:{github_cfg.get('organization', '')}")
print(f"APP_ID:{github_cfg.get('app_id', '')}")
print(f"INSTALL_ID:{github_cfg.get('installation_id', '')}")
print(f"KEY_FILE:{github_cfg.get('private_key_file', '')}")
PYTHON_SCRIPT
}

# Get repositories from GitHub API using Python
get_repositories() {
    local org=$1
    python3 << 'PYTHON_SCRIPT'
import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app.config import load_config
    from app.github_app import list_repositories_with_meta

    config = load_config(sys.argv[1])

    if not config.github:
        print("ERROR: GitHub config not found")
        sys.exit(1)

    repos = list_repositories_with_meta(config.github)
    for repo in repos:
        # Convert HTTPS to SSH
        ssh_url = repo.clone_url
        if ssh_url.startswith("https://github.com/"):
            path = ssh_url[len("https://github.com/"):]
            ssh_url = f"git@github.com:{path}"
        print(f"{repo.full_name}|{ssh_url}")
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
PYTHON_SCRIPT
}

# Clone or fetch a repository
sync_repository() {
    local full_name=$1
    local ssh_url=$2
    local workspace=$3

    # Extract org and repo name
    local org=$(echo "$full_name" | cut -d'/' -f1)
    local repo=$(echo "$full_name" | cut -d'/' -f2)
    local target_dir="$workspace/$org/$repo"

    # Create parent directory
    mkdir -p "$(dirname "$target_dir")"

    if [ -d "$target_dir" ] && [ -f "$target_dir/HEAD" ]; then
        # Repository already exists, fetch updates
        log_info "更新仓库: $full_name"
        if git -C "$target_dir" fetch --all --prune > /dev/null 2>&1; then
            log_success "已更新: $full_name"
        else
            log_error "更新失败: $full_name"
            return 1
        fi
    else
        # Clone new repository
        log_info "克隆仓库: $full_name -> $target_dir"
        if git clone --mirror "$ssh_url" "$target_dir" > /dev/null 2>&1; then
            log_success "已克隆: $full_name"
        else
            log_error "克隆失败: $full_name"
            return 1
        fi
    fi
}

# Main
main() {
    log_info "克隆脚本启动"
    log_info "配置文件: $CONFIG_FILE"
    log_info "目标目录: $WORKSPACE"

    # Check prerequisites
    check_prerequisites

    # Extract GitHub config
    log_info "读取 GitHub 配置..."
    github_config=$(extract_github_config "$CONFIG_FILE" 2>&1)
    if echo "$github_config" | grep -q "ERROR"; then
        log_error "$(echo "$github_config" | grep ERROR)"
        exit 1
    fi

    # Parse config
    eval "$github_config"
    log_success "GitHub 组织: $ORG"

    # Get repositories
    log_info "获取仓库列表..."
    repos=$(get_repositories "$CONFIG_FILE" 2>&1)

    if echo "$repos" | grep -q "ERROR"; then
        log_error "$(echo "$repos" | grep ERROR)"
        exit 1
    fi

    # Count repositories
    repo_count=$(echo "$repos" | wc -l)
    log_success "找到 $repo_count 个仓库"
    echo ""

    # Clone/fetch each repository
    success_count=0
    fail_count=0

    while IFS='|' read -r full_name ssh_url; do
        if [ -z "$full_name" ] || [ -z "$ssh_url" ]; then
            continue
        fi

        if sync_repository "$full_name" "$ssh_url" "$WORKSPACE"; then
            ((success_count++))
        else
            ((fail_count++))
        fi
    done <<< "$repos"

    echo ""
    log_info "克隆完成"
    log_success "成功: $success_count"
    if [ $fail_count -gt 0 ]; then
        log_error "失败: $fail_count"
    fi
}

main "$@"
