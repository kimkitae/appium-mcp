#!/bin/bash

# TypeScript 파일들을 백업 디렉토리로 이동
mkdir -p typescript_backup/src

# TypeScript 소스 파일들 백업
mv src/*.ts typescript_backup/src/ 2>/dev/null || true

# TypeScript 설정 파일들 백업
mv tsconfig.json typescript_backup/ 2>/dev/null || true
mv eslint.config.mjs typescript_backup/ 2>/dev/null || true
mv .mocharc.yml typescript_backup/ 2>/dev/null || true

# Node.js 관련 파일들 백업
mv package.json typescript_backup/ 2>/dev/null || true
mv package-lock.json typescript_backup/ 2>/dev/null || true

echo "TypeScript 파일들이 typescript_backup/ 디렉토리로 백업되었습니다."
echo "Python 버전이 준비되었습니다." 
