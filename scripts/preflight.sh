#!/bin/sh
# 风起簿 · 提交 / 发布前机械校验
# 对应 CHANGE-PROCESS.md 的 C1（卫生）、C4（迁移）、C6（交付物一致性）、C7（指纹）关卡。
#
# 用法：
#   sh scripts/preflight.sh staged    # pre-commit 钩子用：暂存区卫生 + 版本号与包名一致性
#   sh scripts/preflight.sh quick     # 本地快检：卫生 + 版本/台账/schema 自洽（不跑 Gradle）
#   sh scripts/preflight.sh release   # 发布关卡：quick + 交付物漂移 + tag + sha256 + 单测
#   sh scripts/preflight.sh release --no-tests
#
# 退出码：0 通过 ｜ 1 存在违规（不得提交 / 不得发布）｜ 2 环境异常

set -u

GRADLE_FILE="android/app/build.gradle.kts"
DB_FILE="android/app/src/main/java/com/windveil/journal/data/local/db/WindveilDatabase.kt"
SCHEMA_DIR="android/app/schemas"
RELEASE_DIR="release"
README_FILE="README.md"
MAIN_SRC="android/app/src/main"

MODE="quick"
RUN_TESTS=1
for arg in "$@"; do
    case "$arg" in
        staged | quick | release) MODE="$arg" ;;
        --no-tests) RUN_TESTS=0 ;;
        *)
            echo "未知参数：$arg"
            exit 2
            ;;
    esac
done

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "[不通过] 当前目录不在 git 仓库内"
    exit 2
}
cd "$ROOT" || exit 2

# 非 ASCII 路径（release/风起簿-*.apk）默认会被八进制转义，必须关掉才能匹配
GIT="git -c core.quotepath=false"

fail=0
pass() { printf '  [通过] %s\n' "$1"; }
bad() { printf '  [不通过] %s\n' "$1"; fail=$((fail + 1)); }
hint() { printf '  [提示] %s\n' "$1"; }
section() { printf '\n== %s ==\n' "$1"; }

# 指向构建产物 / 本地配置的路径（入库即违规）
BAD_PATH_RE='(^|/)(build|\.gradle|\.idea|\.claude|__pycache__)/|(^|/)local\.properties$|(^|/)\.env$'

# ---------------------------------------------------------------- C1 卫生检查
section "C1 入库卫生（$MODE）"

if [ "$MODE" = "staged" ]; then
    # 只看新增/修改/改名：删除构建产物是清理动作，不该被判违规（--diff-filter=ACMR）
    SCOPE=$($GIT diff --cached --name-only --diff-filter=ACMR)
    SCOPE_DESC="暂存区"
else
    SCOPE=$($GIT ls-files)
    SCOPE_DESC="已跟踪文件"
fi

hit=$(printf '%s\n' "$SCOPE" | grep -E "$BAD_PATH_RE" || true)
if [ -n "$hit" ]; then
    bad "$SCOPE_DESC 含构建产物或本地配置："
    printf '%s\n' "$hit" | sed 's/^/        /'
else
    pass "$SCOPE_DESC 无构建产物 / 本地配置"
fi

hit=$(printf '%s\n' "$SCOPE" | grep -E '\.(apk|aab)$' | grep -vE "^${RELEASE_DIR}/.*\.apk$" || true)
if [ -n "$hit" ]; then
    bad "只有 $RELEASE_DIR/*.apk 允许入库，以下包路径不合规："
    printf '%s\n' "$hit" | sed 's/^/        /'
else
    pass "发布包路径合规（仅 $RELEASE_DIR/*.apk）"
fi

# staged 模式到此为止：版本一致性只在改动涉及版本号或发布包时才校验
if [ "$MODE" = "staged" ]; then
    touched=$($GIT diff --cached --name-only --diff-filter=ACMR | grep -E "^${GRADLE_FILE}$|^${RELEASE_DIR}/.*\.apk$" || true)
    if [ -z "$touched" ]; then
        hint "本次未触及版本号 / 发布包，跳过版本一致性检查"
    fi
fi

# ------------------------------------------------- 版本号、台账、schema 自洽
if [ "$MODE" != "staged" ] || [ -n "${touched:-}" ]; then

    section "C6 版本与交付物一致性"

    if [ ! -f "$GRADLE_FILE" ]; then
        bad "找不到 $GRADLE_FILE"
        version_name=""
    else
        version_name=$(sed -n 's/^[[:space:]]*versionName[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$GRADLE_FILE" | head -1)
        version_code=$(sed -n 's/^[[:space:]]*versionCode[[:space:]]*=[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$GRADLE_FILE" | head -1)
        if [ -z "$version_name" ]; then
            bad "无法从 $GRADLE_FILE 解析 versionName"
        else
            pass "源码版本：versionName=$version_name versionCode=${version_code:-?}"
        fi
    fi

    # 取版本号最大的发布包
    apk_version=""
    apk_file=""
    if [ -d "$RELEASE_DIR" ]; then
        newest=$(for f in "$RELEASE_DIR"/*.apk; do
            [ -f "$f" ] || continue
            b=$(basename "$f")
            v=$(printf '%s' "$b" | sed -n 's/.*-v\([0-9][0-9.]*\)\.apk$/\1/p')
            [ -n "$v" ] && printf '%s %s\n' "$v" "$b"
        done | sort -V | tail -1)
        if [ -n "$newest" ]; then
            apk_version=$(printf '%s' "$newest" | awk '{print $1}')
            apk_file=$(printf '%s' "$newest" | cut -d' ' -f2-)
        fi
    fi

    if [ -z "$apk_file" ]; then
        if [ "$MODE" = "release" ]; then
            bad "$RELEASE_DIR/ 下没有符合“风起簿-vX.Y.Z.apk”命名的发布包"
        else
            hint "$RELEASE_DIR/ 下暂无可识别的发布包"
        fi
    else
        if [ -n "$version_name" ] && [ "$apk_version" != "$version_name" ]; then
            bad "交付物与源码版本不一致：包是 v$apk_version，源码 versionName=$version_name"
            printf '        处理：要么把包换成 v%s，要么把 versionName 改成 %s\n' "$version_name" "$apk_version"
        else
            pass "发布包与源码版本一致：$apk_file"
        fi

        if [ -f "$README_FILE" ] && ! grep -qF "$apk_file" "$README_FILE"; then
            bad "$README_FILE 的「发布记录」台账里没有 $apk_file（台账未更新）"
        elif [ -f "$README_FILE" ]; then
            pass "$README_FILE 台账已登记 $apk_file"
        fi

        if [ "$MODE" = "staged" ]; then
            hint "tag 与交付物漂移检查在提交后执行：sh scripts/preflight.sh release"
        fi
    fi

    # 台账里不得出现比源码更新的版本（只认台账表格第一列的版本号）
    if [ -f "$README_FILE" ] && [ -n "$version_name" ]; then
        ledger=$(sed -n '/^## 发布记录/,/^## /p' "$README_FILE")
        ledger_max=$(printf '%s\n' "$ledger" | grep -oE '^\| *v[0-9]+\.[0-9]+\.[0-9]+' |
            grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | sort -V | tail -1)
        if [ -n "$ledger_max" ] && [ "$ledger_max" != "$version_name" ]; then
            hint "台账最新版本为 v$ledger_max，源码为 v$version_name（仅当二者都不是待发布态时才需对齐）"
        fi
    fi

    # ---------------------------------------------------- C4 数据库与迁移
    section "C4 数据库 schema 与迁移"

    if [ -f "$DB_FILE" ]; then
        db_version=$(sed -n 's/^[[:space:]]*version[[:space:]]*=[[:space:]]*\([0-9][0-9]*\),.*/\1/p' "$DB_FILE" | head -1)
        schema_max=""
        if [ -d "$SCHEMA_DIR" ]; then
            schema_max=$(find "$SCHEMA_DIR" -name '*.json' | sed 's#.*/##; s#\.json$##' | grep -E '^[0-9]+$' | sort -n | tail -1)
        fi
        if [ -z "$db_version" ]; then
            hint "无法解析 @Database(version =)"
        elif [ -z "$schema_max" ]; then
            bad "$SCHEMA_DIR 下找不到导出的 schema JSON"
        elif [ "$db_version" != "$schema_max" ]; then
            bad "DB 版本不匹配：@Database(version = $db_version) vs 最新 schema $schema_max.json"
        else
            pass "DB 版本与 schema 一致：v$db_version"
        fi

        # 迁移链完整性：从 1 一路到 db_version 都应有 MIGRATION_x_y
        if [ -n "$db_version" ] && [ "$db_version" -gt 1 ] 2>/dev/null; then
            i=1
            missing=""
            while [ "$i" -lt "$db_version" ]; do
                next=$((i + 1))
                grep -q "MIGRATION_${i}_${next}" "$DB_FILE" || missing="$missing ${i}->${next}"
                i=$next
            done
            if [ -n "$missing" ]; then
                bad "缺少迁移定义：$missing"
            else
                pass "迁移链完整：1 → $db_version"
            fi
        fi
    else
        bad "找不到 $DB_FILE"
    fi
fi

# ------------------------------------------------------- 发布关卡专有检查
if [ "$MODE" = "release" ]; then
    if [ -n "${apk_file:-}" ]; then
        section "C6 交付物漂移与 tag"

        apk_commit=$(git log -1 --format=%H -- "$RELEASE_DIR/$apk_file")
        if [ -z "$apk_commit" ]; then
            bad "$RELEASE_DIR/$apk_file 尚未提交（发布必须落盘）"
        else
            drift=$(git log --oneline "$apk_commit..HEAD" -- "$MAIN_SRC" || true)
            if [ -n "$drift" ]; then
                bad "交付物漂移：$apk_file 入库后，主源码又有改动（包比代码旧）"
                printf '%s\n' "$drift" | sed 's/^/        /'
            else
                pass "$apk_file 之后主源码无改动"
            fi

            tag_name="v${apk_version:-$version_name}"
            if ! git rev-parse -q --verify "refs/tags/$tag_name" >/dev/null; then
                bad "缺少 tag $tag_name"
            else
                in_tree=$($GIT ls-tree -r --name-only "$tag_name" -- "$RELEASE_DIR/" 2>/dev/null | grep -F "$apk_file" || true)
                if [ -z "$in_tree" ]; then
                    bad "tag $tag_name 的树里取不到 $apk_file（tag 打在入库之前）"
                else
                    pass "tag $tag_name 可取回 $apk_file"
                fi
            fi
        fi

        section "C7 交付物指纹"
        sha256sum "$RELEASE_DIR/$apk_file" 2>/dev/null || hint "本机无 sha256sum，请手工记录包指纹"
    fi

    if [ "$RUN_TESTS" -eq 1 ]; then
        section "C2 单元测试"
        if [ -x "android/gradlew" ] || [ -f "android/gradlew" ]; then
            if (cd android && sh ./gradlew --quiet :app:testDebugUnitTest); then
                pass "单元测试全绿"
            else
                bad "单元测试未通过"
            fi
        else
            hint "未找到 android/gradlew，跳过单测"
        fi
    else
        section "C2 单元测试"
        hint "已按 --no-tests 跳过（发布前必须补跑）"
    fi
fi

# ------------------------------------------------------------------ 结论
printf '\n'
if [ "$fail" -gt 0 ]; then
    printf '结果：不通过（%d 项违规）—— 不得提交 / 不得发布。规范见 CHANGE-PROCESS.md\n' "$fail"
    exit 1
fi
printf '结果：通过（模式 %s）\n' "$MODE"
exit 0
