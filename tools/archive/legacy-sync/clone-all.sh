#!/bin/bash

# 设置工作目录
WORKSPACE=".data/repos"
ORG="WeFi-HLB"

# 创建目录
mkdir -p "$WORKSPACE/$ORG"

# 克隆仓库列表
git clone --mirror git@github.com:$ORG/ai-ocr.git "$WORKSPACE/$ORG/ai-ocr"
git clone --mirror git@github.com:$ORG/repo2.git "$WORKSPACE/$ORG/repo2"
git clone --mirror git@github.com:$ORG/repo3.git "$WORKSPACE/$ORG/repo3"

# 添加更多仓库，按照上面的格式即可
